You are working in a fresh git branch off a clone of https://github.com/voska/hass-mcp
(MIT). The DESIGN BELOW IS FINAL — implement it, do not redesign it or swap the base repo.

## Why
This becomes a read-only Home Assistant MCP server for an LLM agent. It must scope which
entities are visible using ITS OWN allowlist, independent of Home Assistant's Assist
exposure list. It must be read-only by default, with control re-enableable later via config.

## Design (frozen)
Two independent, env-driven controls. Nothing is deleted — disabled features stay in the
code and are gated off, so they can be re-enabled by flipping an env var.

1. CAPABILITY FLAGS — gate which tool/resource/prompt groups register at startup:
   - read, history, diagnostics, resources  -> default ON
   - control, prompts                        -> default OFF
   - env vars: HASS_MCP_ENABLE_{READ,HISTORY,DIAGNOSTICS,RESOURCES,CONTROL,PROMPTS}
   - Control tools that MUST be gated under "control": entity_action, restart_ha,
     call_service_tool.

2. ENTITY ALLOWLIST — which entities may be read/acted on:
   - env: HASS_MCP_ALLOWLIST (comma-separated entity_ids and/or fnmatch globs, e.g.
     "sensor.gpu_*,sensor.*_temperature"), plus optional HASS_MCP_ALLOWLIST_FILE
     (one pattern per line, "#" comments).
   - FAIL-CLOSED: empty allowlist denies everything, with a loud startup WARNING.
   - Matching: fnmatch.fnmatchcase (case-sensitive; entity_ids are lowercase).

## Implementation
- New module app/policy.py: holds the flag reads, allowlist load/match, is_allowed(),
  filter_entities() (passes error-envelope dicts/lists through untouched), denied()
  payload, and a startup-summary logger.
- Enforce the allowlist CENTRALLY at the data-access choke points in app/hass.py, NOT in
  each tool:
    * get_entity_state  -> deny if not allowed
    * get_entities      -> filter result to allowlist (this covers list_entities, search,
                           by_area, domain_summary, list_automations, and the hass://
                           resources, which all funnel through it)
    * get_system_overview -> filter too — IMPORTANT: it does its OWN raw /api/states fetch
                           and bypasses get_entities, so it needs its own filter call
    * get_entity_history, get_entity_history_range, get_entity_statistics_range -> deny
                           if not allowed (statistics() delegates to _range, so guarding
                           _range covers it)
- In app/server.py: add gated_tool(cap)/gated_resource(uri,cap)/gated_prompt(cap)
  decorator factories that register with mcp only if policy.enabled(cap), else return the
  function undecorated. Swap every @mcp.tool()/@mcp.resource()/@mcp.prompt() to the gated
  form with the correct capability. Also allowlist-guard entity_action so control, once
  re-enabled, still can't act outside the allowlist. Log the policy summary at startup.
- Update .env.example with all new vars and a short README section documenting them.

## Test contract (this is your oracle — make it pass)
Add pytest tests (respx is already a dev dep for HTTP mocking; use mocked HA, no live calls):
- is_allowed: exact match, glob match (sensor.gpu_* matches sensor.gpu_temp), non-match
  (lock.front_door) is denied, empty string denied.
- empty allowlist -> is_allowed returns False for everything (fail-closed).
- filter_entities: drops non-allowlisted, keeps allowlisted, passes [{"error":...}] and
  {"error":...} through unchanged.
- capability gating at the framework level: import the server with control OFF and assert
  await mcp.list_tools() contains NONE of {entity_action, restart_ha, call_service_tool}
  and list_prompts() is empty; with HASS_MCP_ENABLE_CONTROL=true and
  HASS_MCP_ENABLE_PROMPTS=true, assert all three control tools and the prompts ARE present.
- get_entity_state / history / statistics return the denied() payload for an
  off-allowlist entity without making an HTTP call.
- get_system_overview, fed a mocked /api/states with mixed entities, returns only
  allowlisted ones (regression test for the bypass).

## Constraints
- Work only in the branch. Do NOT add a live HA token, do NOT deploy, do NOT make real
  network calls — tests use mocked HA only.
- Use uv for env/deps. Keep changes minimal and well-commented; mark each fork edit.
- Definition of done: full pytest suite green (including the registration tests) and a
  one-paragraph summary of what changed. Stop there for human review — do not wire up
  deployment or credentials.