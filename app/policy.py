"""
Read-only / capability policy layer for the Hermes fork of hass-mcp.

Two independent controls, both env-driven so nothing is hard-coded and any
capability can be re-enabled later WITHOUT editing code:

1. CAPABILITY FLAGS — which groups of tools/resources/prompts get registered
   at startup. Control is OFF by default; this fork is read-only out of the box.
   Flip a group back on by setting its env var (e.g. HASS_MCP_ENABLE_CONTROL=true).

2. ENTITY ALLOWLIST — which entities the server may read or act on, enforced
   centrally in app/hass.py at the data-access choke points. Independent of
   Home Assistant's Assist exposure list (the whole reason this fork exists).
   FAIL-CLOSED: an empty allowlist denies everything, with a loud startup warning.
"""

from __future__ import annotations

import fnmatch
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


# --- Capability flags --------------------------------------------------------
# Defaults encode the rung-one posture: read + history + diagnostics + resources
# ON; control + prompts OFF.
CAPABILITIES = {
    "read": _env_bool("HASS_MCP_ENABLE_READ", True),
    "history": _env_bool("HASS_MCP_ENABLE_HISTORY", True),
    "diagnostics": _env_bool("HASS_MCP_ENABLE_DIAGNOSTICS", True),
    "resources": _env_bool("HASS_MCP_ENABLE_RESOURCES", True),
    "control": _env_bool("HASS_MCP_ENABLE_CONTROL", False),
    "prompts": _env_bool("HASS_MCP_ENABLE_PROMPTS", False),
}


def enabled(capability: str) -> bool:
    """True if the given capability group should be registered at startup."""
    return CAPABILITIES.get(capability, False)


# --- Entity allowlist --------------------------------------------------------
def _load_patterns() -> list[str]:
    patterns: list[str] = []
    raw = os.environ.get("HASS_MCP_ALLOWLIST", "")
    patterns += [p.strip() for p in raw.split(",") if p.strip()]
    path = os.environ.get("HASS_MCP_ALLOWLIST_FILE", "").strip()
    if path:
        try:
            for line in Path(path).read_text().splitlines():
                line = line.split("#", 1)[0].strip()  # allow inline comments
                if line:
                    patterns.append(line)
        except OSError as e:
            logger.error("Could not read HASS_MCP_ALLOWLIST_FILE %s: %s", path, e)
    return patterns


ALLOWLIST: list[str] = _load_patterns()


def is_allowed(entity_id: str) -> bool:
    """
    True if entity_id matches any allowlist pattern. Patterns are exact ids or
    fnmatch globs (e.g. 'sensor.gpu_*', 'binary_sensor.*_offline').
    Fail-closed: an empty allowlist allows nothing.
    """
    if not entity_id:
        return False
    return any(fnmatch.fnmatchcase(entity_id, pat) for pat in ALLOWLIST)


def filter_entities(entities: Any) -> Any:
    """
    Filter a list of entity dicts (each with 'entity_id') down to the allowlist.
    Error envelopes (a dict, or a single-item [{'error': ...}] list) pass through
    untouched so existing caller error-handling still works.
    """
    if isinstance(entities, dict):  # error envelope
        return entities
    if not isinstance(entities, list):
        return entities
    if len(entities) == 1 and isinstance(entities[0], dict) and "error" in entities[0]:
        return entities
    return [
        e for e in entities
        if isinstance(e, dict) and is_allowed(e.get("entity_id", ""))
    ]


def denied(entity_id: str) -> dict:
    """Standard deny payload for single-entity reads/actions."""
    return {
        "entity_id": entity_id,
        "error": (
            f"Entity '{entity_id}' is not in the MCP allowlist "
            f"(HASS_MCP_ALLOWLIST). Access denied."
        ),
    }


def log_startup_summary() -> None:
    on = sorted(k for k, v in CAPABILITIES.items() if v)
    off = sorted(k for k, v in CAPABILITIES.items() if not v)
    logger.info("hass-mcp policy: capabilities ON=%s OFF=%s", on, off)
    if not ALLOWLIST:
        logger.warning(
            "hass-mcp policy: ALLOWLIST IS EMPTY -> all entity reads will be "
            "DENIED (fail-closed). Set HASS_MCP_ALLOWLIST or HASS_MCP_ALLOWLIST_FILE."
        )
    else:
        logger.info("hass-mcp policy: %d allowlist pattern(s)=%s",
                    len(ALLOWLIST), ALLOWLIST)
