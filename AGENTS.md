# AGENTS.md

## Project
Hass-MCP is a Python 3.13 Model Context Protocol server that exposes Home
Assistant data and actions to MCP clients. This working tree is a fork of
`voska/hass-mcp` with a safety-focused direction: read-only by default,
entity access scoped by an MCP-owned allowlist, and HTTP mode suitable for
gateways only when protected by external auth.

Use `uv` for all Python environment work. Do not use a live Home Assistant
token in tests or examples.

## Layout
- `app/server.py` - FastMCP server definition, tool/resource/prompt
  registration, transport-facing functions, and capability gating.
- `app/run.py` and `app/__main__.py` - CLI entry points. Stdio is default;
  `--http` enables streamable HTTP.
- `app/hass.py` - central REST API access, field filtering, allowlist
  enforcement, history/statistics wrappers, TLS policy, and client lifetime.
- `app/ws.py` - Home Assistant WebSocket helper used for recorder statistics.
- `app/areas.py` - area enrichment via `/api/template` with an in-memory TTL
  cache.
- `app/policy.py` - fork policy layer: capability flags, allowlist loading,
  `is_allowed`, `filter_entities`, deny payloads, and startup logging.
- `app/config.py` - import-time `HA_URL`/`HA_TOKEN` capture and HA headers.
- `tests/` - pytest coverage for helpers, server functions, MCP protocol
  roundtrips, live transports, and Docker image behavior.
- `.env.example` - documented local env vars, including fork policy flags.
- `hass-mcp-fork.patch` and `how-to-use-patch-files.md` - patch/export
  artifacts for the fork; update them only when explicitly asked.

## Commands
- Install dependencies: `uv sync --extra test`
- Run all tests: `uv run pytest`
- Run focused unit tests: `uv run pytest tests/test_hass.py tests/test_server.py`
- Run protocol tests: `uv run pytest tests/test_protocol.py`
- Run transport tests: `uv run pytest tests/test_transports.py`
- Run Docker tests: `uv run pytest tests/test_docker.py` (requires Docker)
- Start stdio server: `uv run python -m app`
- Start HTTP server: `uv run python -m app --http --port 8000`
- Build wheel: `uv build --wheel`
- Build Docker image: `docker build -t hass-mcp-test .`

There is no project-level ruff/format config in `pyproject.toml` right now.
Preserve the existing style unless a lint/format tool is added deliberately.

## Fork Policy
- Keep the fork read-only by default. `read`, `history`, `diagnostics`, and
  `resources` default on; `control` and `prompts` default off.
- Capability flags are env-driven: `HASS_MCP_ENABLE_{READ,HISTORY,DIAGNOSTICS,RESOURCES,CONTROL,PROMPTS}`.
- Entity visibility is controlled only by `HASS_MCP_ALLOWLIST` and
  `HASS_MCP_ALLOWLIST_FILE`. An empty allowlist is fail-closed and denies all
  entity reads/actions.
- Enforce entity policy centrally in `app/hass.py` at data-access choke points:
  single entity reads, list/state collection fetches, system overview, history,
  and statistics. Do not scatter duplicate allowlist filters through every tool.
- Control tools (`entity_action`, `call_service_tool`, `restart_ha`) must stay
  behind the `control` capability. If control is enabled, entity-specific
  actions still need allowlist checks.
- `app/server.py` registers tools/resources/prompts at import time. Tests that
  change policy env vars must reload `app.policy` and `app.server` so FastMCP
  registration reflects the new env.
- Mark fork-specific code with the existing "Hermes fork" comment style when
  it helps future upstream merges.

## Testing Guidance
- Tests must mock Home Assistant. Use `respx`, `AsyncMock`, or the existing
  fixtures; never make live HA calls.
- `tests/conftest.py` sets `HA_URL` and `HA_TOKEN` before app imports because
  `app.config` captures them at import time. Be careful with tests that mutate
  env after imports.
- Protocol tests use `create_connected_server_and_client_session` and catch
  serialization/registration issues that plain function tests miss.
- Transport tests spawn `python -m app`; Docker tests build and run the image.
  Keep these for CLI/packaging changes, but prefer focused tests for small
  logic changes.
- `app/areas.py` has module-level cache state. In tests that mock
  `/api/template`, reset it with `app.areas.invalidate_cache()`.

## Security And Operations
- Never commit `.env`, tokens, long-lived HA credentials, or real local host
  details.
- Do not add `verify=False` or otherwise weaken TLS verification. The intended
  custom CA path is OS trust via `truststore` or explicit `SSL_CERT_FILE`.
- HTTP mode exposes Home Assistant capability over the network. Keep localhost
  as the default bind and document reverse-proxy/VPN/auth requirements for any
  non-local deployment.
- Avoid dependency bumps or published image/version changes unless requested.
  This is a fork; keep changes small and easy to compare with upstream.

## Smoke testing (required after code changes)

After editing anything under `app/`, run the smoke tests and confirm they exit 0
before considering the change done:

    ./run_smoke_tests.sh

This runs Tier 0 (import every `app.*` module + config check, no network) then
Tier 1 (MCP `tools/list` round-trip against the running container — validates
HTTP transport, tool registration, and the `HASS_MCP_ENABLE_CONTROL=false` policy
gate). It does NOT call Home Assistant or cause any side effects.

A passing smoke test does not redeploy the running container. The long-running
process keeps the code it imported at startup. To actually apply the change:

    docker compose up -d --force-recreate ha-mcp

Source is baked into the image (not bind-mounted), so a rebuild is needed to
pick up `app/` changes:

    docker compose up -d --build ha-mcp

There are no Tier 2 (side-effecting) scripts — the service is read-only by default.
If `HASS_MCP_ENABLE_CONTROL=true` is ever enabled, manually verify control paths
against a test HA instance; do not automate real entity actions.

## Coding Conventions
- Prefer typed async helpers and return JSON-serializable `dict`/`list` shapes
  from MCP tools.
- Keep token-efficient responses as the default (`lean=True`) and add fields
  deliberately.
- Preserve MCP tool/resource/prompt names unless the user explicitly asks for a
  breaking change.
- Keep Home Assistant API behavior behind `app/hass.py`/`app/ws.py`; server
  functions should mostly validate arguments, log, and delegate.
- Update README and `.env.example` when adding env vars, transports, tools, or
  security-relevant behavior.
