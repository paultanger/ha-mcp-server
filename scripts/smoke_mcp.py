#!/usr/bin/env python3
"""Tier 1 smoke test: MCP protocol liveness and policy-gate check.

Posts JSON-RPC requests to the running HTTP server and validates:
  - Server responds (HTTP transport is up)
  - Expected read-only tools are present (tool registration is working)
  - Control tools are absent (HASS_MCP_ENABLE_CONTROL=false gate is enforced)

No Home Assistant connection is needed — tools/list is answered locally by
FastMCP without touching HA.

Run from the repo root (hits the published port):
    python3 scripts/smoke_mcp.py
"""
import json
import sys
import urllib.error
import urllib.request

MCP_URL = "http://localhost:8000/mcp"

# Tools that must be present with the default capabilities:
#   read=ON, history=ON, resources=ON; diagnostics/control/prompts=OFF
EXPECTED_TOOLS = {
    # read
    "get_version",
    "get_entity",
    "list_entities",
    "search_entities_tool",
    "domain_summary_tool",
    "list_automations",
    "system_overview",
    "get_entities_by_area",
    # history
    "get_history",
    "get_history_range",
    "get_statistics",
    "get_statistics_range",
}

# Control tools — must be absent when HASS_MCP_ENABLE_CONTROL=false (default)
CONTROL_TOOLS = {"entity_action", "call_service_tool", "restart_ha"}


def rpc(method, params=None, req_id=1):
    """POST a single JSON-RPC 2.0 request; return the decoded response dict."""
    payload = json.dumps(
        {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params or {}}
    ).encode()
    req = urllib.request.Request(
        MCP_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


failures = []

# Step 1: MCP initialize
try:
    rpc("initialize", {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "smoke-mcp", "version": "1.0"},
    })
    print("  ok    initialize")
except urllib.error.HTTPError as e:
    body = e.read().decode(errors="replace")[:300]
    failures.append(f"initialize HTTP {e.code}: {body}")
    print(f"  FAIL  initialize HTTP {e.code}: {body}")
except Exception as e:  # noqa: BLE001
    failures.append(f"initialize: {e}")
    print(f"  FAIL  initialize: {e}")

# Step 2: tools/list
tool_names: set[str] = set()
try:
    resp = rpc("tools/list", req_id=2)
    tools = resp.get("result", {}).get("tools", [])
    tool_names = {t["name"] for t in tools}
    print(f"  ok    tools/list → {len(tool_names)} tools")
except urllib.error.HTTPError as e:
    body = e.read().decode(errors="replace")[:300]
    failures.append(f"tools/list HTTP {e.code}: {body}")
    print(f"  FAIL  tools/list HTTP {e.code}: {body}")
except Exception as e:  # noqa: BLE001
    failures.append(f"tools/list: {e}")
    print(f"  FAIL  tools/list: {e}")

# Step 3: expected read-only tools present?
if tool_names:
    missing = EXPECTED_TOOLS - tool_names
    if missing:
        failures.append(f"expected tools missing: {sorted(missing)}")
        print(f"  FAIL  expected tools missing: {sorted(missing)}")
    else:
        print("  ok    expected read-only tools present")

    # Step 4: control tools absent (policy gate)
    leaked = CONTROL_TOOLS & tool_names
    if leaked:
        failures.append(f"control tools leaked past policy gate: {sorted(leaked)}")
        print(f"  FAIL  control tools should be absent: {sorted(leaked)}")
    else:
        print("  ok    control tools absent (policy gate)")

if failures:
    print(f"\nTier 1 FAILED ({len(failures)} problem(s))")
    sys.exit(1)

print("\nTier 1 passed")
