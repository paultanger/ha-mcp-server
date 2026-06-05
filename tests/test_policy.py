import importlib
import os
from unittest.mock import AsyncMock, MagicMock

import pytest
from mcp.shared.memory import create_connected_server_and_client_session


CONTROL_TOOLS = {"entity_action", "restart_ha", "call_service_tool"}
PROMPTS = {
    "automation_health_check",
    "create_automation",
    "dashboard_layout_generator",
    "debug_automation",
    "entity_naming_consistency",
    "routine_optimizer",
    "troubleshoot_entity",
}


def _reload_policy(monkeypatch, allowlist=None, denylist=None, **flags):
    if allowlist is None:
        monkeypatch.delenv("HASS_MCP_ALLOWLIST", raising=False)
    else:
        monkeypatch.setenv("HASS_MCP_ALLOWLIST", allowlist)
    monkeypatch.delenv("HASS_MCP_ALLOWLIST_FILE", raising=False)

    if denylist is None:
        monkeypatch.delenv("HASS_MCP_CONTROL_DENYLIST", raising=False)
    else:
        monkeypatch.setenv("HASS_MCP_CONTROL_DENYLIST", denylist)
    monkeypatch.delenv("HASS_MCP_CONTROL_DENYLIST_FILE", raising=False)

    for cap in ("READ", "HISTORY", "DIAGNOSTICS", "RESOURCES", "CONTROL", "PROMPTS"):
        name = f"HASS_MCP_ENABLE_{cap}"
        if cap.lower() in flags:
            monkeypatch.setenv(name, "true" if flags[cap.lower()] else "false")
        else:
            monkeypatch.delenv(name, raising=False)

    import app.policy as policy
    return importlib.reload(policy)


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def restore_default_policy():
    yield
    os.environ["HASS_MCP_ALLOWLIST"] = "*"
    os.environ.pop("HASS_MCP_CONTROL_DENYLIST", None)
    for cap in ("READ", "HISTORY", "DIAGNOSTICS", "RESOURCES", "CONTROL", "PROMPTS"):
        os.environ.pop(f"HASS_MCP_ENABLE_{cap}", None)
    import app.policy as policy
    import app.server as server
    importlib.reload(policy)
    importlib.reload(server)


def test_is_allowed_exact_glob_nonmatch_and_empty(monkeypatch):
    policy = _reload_policy(
        monkeypatch,
        "sensor.gpu_temp,sensor.gpu_*,sensor.*_temperature",
    )

    assert policy.is_allowed("sensor.gpu_temp") is True
    assert policy.is_allowed("sensor.gpu_power") is True
    assert policy.is_allowed("sensor.office_temperature") is True
    assert policy.is_allowed("lock.front_door") is False
    assert policy.is_allowed("") is False


def test_empty_allowlist_fails_closed(monkeypatch):
    policy = _reload_policy(monkeypatch, None)

    assert policy.ALLOWLIST == []
    assert policy.is_allowed("sensor.gpu_temp") is False
    assert policy.is_allowed("light.kitchen") is False


def test_filter_entities_filters_and_preserves_error_envelopes(monkeypatch):
    policy = _reload_policy(monkeypatch, "sensor.gpu_*,light.kitchen")
    entities = [
        {"entity_id": "sensor.gpu_temp", "state": "42"},
        {"entity_id": "light.kitchen", "state": "on"},
        {"entity_id": "lock.front_door", "state": "locked"},
    ]

    assert policy.filter_entities(entities) == entities[:2]
    assert policy.filter_entities({"error": "boom"}) == {"error": "boom"}
    assert policy.filter_entities([{"error": "boom"}]) == [{"error": "boom"}]


async def _registered_surface():
    import app.server as server

    async with create_connected_server_and_client_session(
        server.mcp._mcp_server, raise_exceptions=True
    ) as client:
        tools = await client.list_tools()
        prompts = await client.list_prompts()
    return {t.name for t in tools.tools}, {p.name for p in prompts.prompts}


@pytest.mark.anyio
async def test_capability_gating_defaults_hide_control_and_prompts(monkeypatch):
    _reload_policy(monkeypatch, "*")
    import app.server as server
    importlib.reload(server)

    tools, prompts = await _registered_surface()

    assert CONTROL_TOOLS.isdisjoint(tools)
    assert prompts == set()


@pytest.mark.anyio
async def test_capability_gating_can_enable_control_and_prompts(monkeypatch):
    _reload_policy(monkeypatch, "*", control=True, prompts=True)
    import app.server as server
    importlib.reload(server)

    tools, prompts = await _registered_surface()

    assert CONTROL_TOOLS <= tools
    assert PROMPTS <= prompts

    result = server.create_automation("state")
    assert all(msg["role"] in ("user", "assistant") for msg in result)


@pytest.mark.asyncio
async def test_denied_single_entity_calls_do_not_touch_ha(monkeypatch):
    _reload_policy(monkeypatch, "sensor.allowed")
    import app.hass as hass

    get_client = AsyncMock()
    monkeypatch.setattr(hass, "get_client", get_client)

    state = await hass.get_entity_state("lock.front_door")
    history = await hass.get_entity_history("lock.front_door", 24)
    statistics = await hass.get_entity_statistics("lock.front_door", 24)

    assert "not in the MCP allowlist" in state["error"]
    assert "not in the MCP allowlist" in history["error"]
    assert "not in the MCP allowlist" in statistics["error"]
    assert statistics["statistics"] == []
    get_client.assert_not_called()


@pytest.mark.asyncio
async def test_get_system_overview_filters_raw_state_fetch(monkeypatch):
    _reload_policy(monkeypatch, "sensor.allowed")
    import app.hass as hass
    from app.areas import invalidate_cache

    invalidate_cache()

    states_response = MagicMock()
    states_response.raise_for_status = MagicMock()
    states_response.json.return_value = [
        {
            "entity_id": "sensor.allowed",
            "state": "42",
            "attributes": {"friendly_name": "Allowed Sensor"},
        },
        {
            "entity_id": "light.blocked",
            "state": "on",
            "attributes": {"friendly_name": "Blocked Light"},
        },
    ]

    area_response = MagicMock()
    area_response.raise_for_status = MagicMock()
    area_response.text = "sensor.allowed\x1fKitchen\nlight.blocked\x1fKitchen"

    client = MagicMock()
    client.get = AsyncMock(return_value=states_response)
    client.post = AsyncMock(return_value=area_response)
    monkeypatch.setattr(hass, "get_client", AsyncMock(return_value=client))

    overview = await hass.get_system_overview()

    assert overview["total_entities"] == 1
    assert set(overview["domains"]) == {"sensor"}
    assert overview["domain_samples"]["sensor"][0]["entity_id"] == "sensor.allowed"
    assert "light" not in overview["domains"]


def test_denylist_exact_and_glob_matching(monkeypatch):
    policy = _reload_policy(
        monkeypatch,
        allowlist="*",
        denylist="lock.front_door,lock.*,sensor.danger_*",
    )

    assert policy.control_denied("lock.front_door") is True
    assert policy.control_denied("lock.back_door") is True
    assert policy.control_denied("sensor.danger_gas") is True
    assert policy.control_denied("lock.garage") is True
    # Non-matching entities are not denied
    assert policy.control_denied("light.living_room") is False
    assert policy.control_denied("sensor.temperature") is False


def test_empty_denylist_is_fail_open(monkeypatch):
    policy = _reload_policy(monkeypatch, allowlist="*", denylist=None)

    assert policy.DENYLIST == []
    assert policy.control_denied("lock.front_door") is False
    assert policy.control_denied("any.entity") is False


def test_denylist_empty_string_is_fail_open(monkeypatch):
    policy = _reload_policy(monkeypatch, allowlist="*", denylist="")

    assert policy.DENYLIST == []
    assert policy.control_denied("lock.front_door") is False


def test_denylist_does_not_affect_read(monkeypatch):
    policy = _reload_policy(
        monkeypatch,
        allowlist="*",
        denylist="lock.front_door",
    )

    # is_allowed should be unaffected by the denylist
    assert policy.is_allowed("lock.front_door") is True
    assert policy.is_allowed("light.kitchen") is True


def test_control_denied_payload_structure(monkeypatch):
    policy = _reload_policy(monkeypatch, allowlist="*", denylist="lock.front_door")

    payload = policy.control_denied_payload("lock.front_door")
    assert "entity_id" in payload
    assert payload["entity_id"] == "lock.front_door"
    assert "error" in payload
    assert "control denylist" in payload["error"]


def test_denylist_file_loading(monkeypatch, tmp_path):
    denyfile = tmp_path / "denylist.txt"
    denyfile.write_text("lock.front_door\n# comment\nlight.garage\n")

    policy = _reload_policy(
        monkeypatch,
        allowlist="*",
        denylist=None,
    )
    # Set the file env var after reload to test file loading
    monkeypatch.setenv("HASS_MCP_CONTROL_DENYLIST_FILE", str(denyfile))
    policy = importlib.reload(policy)

    assert "lock.front_door" in policy.DENYLIST
    assert "light.garage" in policy.DENYLIST
    assert policy.control_denied("lock.front_door") is True
    assert policy.control_denied("light.garage") is True


@pytest.mark.asyncio
async def test_denylist_blocks_control_but_allows_read(monkeypatch):
    _reload_policy(
        monkeypatch,
        allowlist="*",
        denylist="lock.deny_me",
    )
    import app.hass as hass

    get_client = AsyncMock()
    monkeypatch.setattr(hass, "get_client", get_client)

    # The denylist only affects control paths, not data access
    get_client.assert_not_called()


@pytest.mark.asyncio
async def test_denylist_blocks_entity_action(monkeypatch):
    _reload_policy(
        monkeypatch,
        allowlist="*",
        denylist="lock.deny_action",
    )
    import app.server as server

    result = await server.entity_action("lock.deny_action", "on")
    assert "error" in result
    assert "control denylist" in result["error"]


@pytest.mark.asyncio
async def test_denylist_blocks_call_service_tool(monkeypatch):
    _reload_policy(
        monkeypatch,
        allowlist="*",
        denylist="lock.deny_service",
    )
    import app.server as server

    result = await server.call_service_tool(
        domain="lock",
        service="unlock",
        data={"entity_id": "lock.deny_service"},
    )
    assert result["success"] is False
    assert "error" in result
    assert "control denylist" in result["error"]


@pytest.mark.asyncio
async def test_denylist_allows_non_denied_entities(monkeypatch):
    from unittest.mock import patch

    _reload_policy(
        monkeypatch,
        allowlist="*",
        denylist="lock.deny_me",
    )
    import app.server as server

    # Non-denylisted entity should pass through to HA (mocked)
    with patch("app.server.call_service", return_value=[]):
        result = await server.entity_action("lock.allowed", "on")
        # Should not contain denylist error
        assert "control denylist" not in str(result)


@pytest.mark.asyncio
async def test_denylist_with_glob_pattern(monkeypatch):
    from unittest.mock import patch

    _reload_policy(
        monkeypatch,
        allowlist="*",
        denylist="lock.*_door",
    )
    import app.server as server

    result = await server.entity_action("lock.front_door", "on")
    assert "error" in result
    assert "control denylist" in result["error"]

    # Non-matching entity should pass through
    with patch("app.server.call_service", return_value=[]):
        result = await server.entity_action("lock.keypad", "on")
        assert "control denylist" not in str(result)


@pytest.mark.asyncio
async def test_denylist_empty_entity_id(monkeypatch):
    policy = _reload_policy(
        monkeypatch,
        allowlist="*",
        denylist="lock.*",
    )

    assert policy.control_denied("") is False
