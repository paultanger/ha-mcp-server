#!/usr/bin/env bash
# Smoke-test runner: tier 0 (import/config) then tier 1 (MCP protocol liveness).
# Stops on first failure and exits non-zero. No side effects — safe to run after
# every code change.
#
# NOTE: a passing smoke test validates the code in a fresh interpreter but does
# NOT redeploy the running container. Restart after smoke tests to pick up changes:
#   docker compose up -d --force-recreate ha-mcp
set -euo pipefail

SERVICE="ha-mcp"
EXEC="docker compose exec -T ${SERVICE}"

echo "== Tier 0: import/config smoke =="
${EXEC} python scripts/smoke_imports.py

echo ""
echo "== Tier 1: MCP protocol liveness + policy-gate check =="
python3 scripts/smoke_mcp.py

echo ""
echo "== All smoke tests passed =="
