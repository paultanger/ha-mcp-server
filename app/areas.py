"""
Per-entity area enrichment for Home Assistant.

Home Assistant's REST `/api/states` endpoint does not include area data;
area information lives in HA's registries (area / entity / device), exposed
over the WebSocket API. We build the entity→area map from three registry list
calls — `config/area_registry/list`, `config/entity_registry/list`, and
`config/device_registry/list` — and resolve each entity to its area the same
way HA does: the entity's own `area_id` if set, otherwise its device's area.

This deliberately avoids HA's `/api/template` endpoint, which is **admin-only**
and returns 401 for the non-admin read-only token this server is designed to
use (see the HA runbook §3/§6). The registry list calls work with a non-admin
token, so area enrichment functions without granting admin.

The mapping is cached in memory with a short TTL (the registries rarely change;
users tolerate a few minutes of staleness).
"""

import asyncio
import logging
import time
from typing import Dict, Optional

import httpx

from app.ws import call_ws

logger = logging.getLogger(__name__)

# Default cache duration. Registries change very rarely (a user adding/renaming
# a room or moving a device), so this can be aggressive.
_DEFAULT_TTL_SECONDS = 300


class AreaCache:
    """In-memory TTL cache of {entity_id: area_name | None}.

    Single-flight: concurrent get/all calls during a refresh share one
    request rather than stampeding the HA API.
    """

    def __init__(self, ttl_seconds: int = _DEFAULT_TTL_SECONDS):
        self._cache: Dict[str, Optional[str]] = {}
        self._expires_at: float = 0.0
        self._ttl = ttl_seconds
        self._lock = asyncio.Lock()

    async def get_all(self, client: httpx.AsyncClient) -> Dict[str, Optional[str]]:
        """Return the full entity→area map, refreshing if expired."""
        if time.monotonic() < self._expires_at:
            return self._cache
        async with self._lock:
            # Double-check inside the lock — another coroutine may have
            # refreshed while we were waiting.
            if time.monotonic() < self._expires_at:
                return self._cache
            await self._refresh()
        return self._cache

    async def get(self, client: httpx.AsyncClient, entity_id: str) -> Optional[str]:
        """Return the area name for one entity, or None if no area assigned."""
        all_areas = await self.get_all(client)
        return all_areas.get(entity_id)

    def invalidate(self) -> None:
        """Discard the cache. Next get/get_all refreshes from HA. If that
        refresh fails, callers see None rather than stale data."""
        self._cache = {}
        self._expires_at = 0.0

    async def _refresh(self) -> None:
        """Rebuild the entity→area map from HA's WS registries.

        Resolution matches HA's own `area_name()`: an entity's explicit
        `area_id` wins; otherwise it inherits its device's area.
        """
        try:
            areas = await call_ws("config/area_registry/list")
            entities = await call_ws("config/entity_registry/list")
            devices = await call_ws("config/device_registry/list")
        except Exception as e:
            # Don't crash callers; serve stale cache and back off retry for
            # a minute to avoid hammering a flaky HA.
            logger.warning("area cache refresh failed: %s", e)
            self._expires_at = time.monotonic() + 60
            return

        area_names: Dict[str, str] = {
            a["area_id"]: a["name"] for a in areas if a.get("area_id")
        }
        device_area: Dict[str, Optional[str]] = {
            d["id"]: d.get("area_id") for d in devices if d.get("id")
        }

        cache: Dict[str, Optional[str]] = {}
        for ent in entities:
            entity_id = ent.get("entity_id")
            if not entity_id:
                continue
            # Entity's own area wins; else fall back to its device's area.
            area_id = ent.get("area_id") or device_area.get(ent.get("device_id"))
            cache[entity_id] = area_names.get(area_id) if area_id else None

        self._cache = cache
        self._expires_at = time.monotonic() + self._ttl
        logger.debug("area cache refreshed: %d entities, %d with areas",
                     len(cache), sum(1 for a in cache.values() if a))


# Module-level singleton. Tests can reset via .invalidate() / monkeypatch.
_cache = AreaCache()


async def get_area(client: httpx.AsyncClient, entity_id: str) -> Optional[str]:
    return await _cache.get(client, entity_id)


async def get_all_areas(client: httpx.AsyncClient) -> Dict[str, Optional[str]]:
    return await _cache.get_all(client)


def invalidate_cache() -> None:
    _cache.invalidate()
