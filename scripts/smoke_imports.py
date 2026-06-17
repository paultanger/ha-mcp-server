#!/usr/bin/env python3
"""Tier 0 smoke test: import every app module and verify config is loaded.

No network, no side effects. Catches syntax errors, bad imports, and missing
env vars before the service is trusted to run.

Run inside the container:
    docker compose exec -T ha-mcp python scripts/smoke_imports.py
"""
import importlib
import sys

# app is installed as a package (uv pip install --system), so dotted imports
# work directly — no sys.path manipulation needed.
MODULES = [
    "app.config",
    "app.policy",
    "app.ws",
    "app.areas",
    "app.hass",
    "app.server",
    "app.run",
]

failures = []

for name in MODULES:
    try:
        importlib.import_module(name)
        print(f"  ok    import {name}")
    except Exception as e:  # noqa: BLE001
        failures.append((name, repr(e)))
        print(f"  FAIL  import {name}: {e!r}")

# Config sanity: HA_URL must be set (empty means the env file wasn't loaded)
try:
    import app.config as _cfg
    if not _cfg.HA_URL:
        raise ValueError("HA_URL is empty — .env file may not have been loaded")
    print(f"  ok    config HA_URL={_cfg.HA_URL!r}")
except Exception as e:  # noqa: BLE001
    failures.append(("config-check", repr(e)))
    print(f"  FAIL  config check: {e!r}")

if failures:
    print(f"\nTier 0 FAILED ({len(failures)} problem(s))")
    sys.exit(1)

print("\nTier 0 passed")
