from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from unipro.bot.admin import build_admin_router
from unipro.bot.user import build_user_router
from unipro.config import get_settings
from unipro.db import Database
from unipro.engine.routes import AlternativeRouteEngine
from unipro.engine.search import SearchOrchestrator
from unipro.engine.watch import WatchRunner
from unipro.health import start_health_server
from unipro.notifications import NotificationService
from unipro.providers.registry import ProviderRegistry


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    settings = get_settings()
    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is empty. Put it in .env or environment variables.")

    db = Database(settings.database_path)
    await db.init()

    registry = ProviderRegistry.from_settings(settings)
    orchestrator = SearchOrchestrator(registry)
    route_engine = AlternativeRouteEngine(orchestrator, settings)

    bot = Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    notifier = NotificationService(bot)
    watch_runner = WatchRunner(
        db=db,
        orchestrator=orchestrator,
        route_engine=route_engine,
        notifier=notifier,
        settings=settings,
    )

    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(
        build_admin_router(
            db=db,
            registry=registry,
            runner=watch_runner,
            settings=settings,
        )
    )
    dp.include_router(build_user_router(db, orchestrator, route_engine, settings))

    health_runner = await start_health_server(
        settings=settings,
        db=db,
        registry=registry,
        runner=watch_runner,
    )
    watch_task = asyncio.create_task(watch_runner.run_forever(), name="watch-runner")

    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await watch_runner.stop()
        watch_task.cancel()
        await asyncio.gather(watch_task, return_exceptions=True)
        await health_runner.cleanup()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
