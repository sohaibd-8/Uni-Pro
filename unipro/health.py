from __future__ import annotations

from aiohttp import web

from unipro.config import Settings
from unipro.db import Database
from unipro.engine.watch import WatchRunner
from unipro.providers.registry import ProviderRegistry


async def start_health_server(
    *,
    settings: Settings,
    db: Database,
    registry: ProviderRegistry,
    runner: WatchRunner,
) -> web.AppRunner:
    app = web.Application()

    async def health(_: web.Request) -> web.Response:
        db_ok = await db.ping()
        polling = await db.get_flag("polling_enabled", "1") == "1"
        payload = {
            "status": "ok" if db_ok else "degraded",
            "database": db_ok,
            "polling_enabled": polling,
            "providers": len(registry.providers),
            "demo_mode": settings.demo_mode,
            "last_cycle_at": runner.last_cycle_at,
            "last_group_count": runner.last_group_count,
        }
        return web.json_response(payload, status=200 if db_ok else 503)

    app.router.add_get("/health", health)
    app_runner = web.AppRunner(app)
    await app_runner.setup()
    site = web.TCPSite(app_runner, "0.0.0.0", settings.health_port)
    await site.start()
    return app_runner
