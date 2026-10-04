from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from datetime import date, timedelta

from unipro.config import Settings
from unipro.db import Database
from unipro.engine.routes import AlternativeRouteEngine
from unipro.engine.search import SearchOrchestrator
from unipro.models import SearchRequest, TravelMode
from unipro.notifications import NotificationService

logger = logging.getLogger(__name__)


class WatchRunner:
    def __init__(
        self,
        *,
        db: Database,
        orchestrator: SearchOrchestrator,
        route_engine: AlternativeRouteEngine,
        notifier: NotificationService,
        settings: Settings,
    ) -> None:
        self.db = db
        self.orchestrator = orchestrator
        self.route_engine = route_engine
        self.notifier = notifier
        self.settings = settings
        self.cycle = 0
        self.last_cycle_at: str | None = None
        self.last_group_count = 0
        self._stop = asyncio.Event()

    async def run_forever(self) -> None:
        while not self._stop.is_set():
            try:
                await self.run_cycle()
            except Exception:
                logger.exception("Unhandled watch cycle error")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.settings.poll_interval_seconds)
            except asyncio.TimeoutError:
                pass

    async def stop(self) -> None:
        self._stop.set()

    async def run_cycle(self) -> None:
        from datetime import datetime, timezone

        self.cycle += 1
        self.last_cycle_at = datetime.now(timezone.utc).isoformat()
        if await self.db.get_flag("polling_enabled", "1") != "1":
            return

        watches = await self.db.list_active_watches()
        groups: dict[str, list[dict]] = defaultdict(list)
        for watch in watches:
            for travel_date in self._dates_for_watch(watch):
                key = self._group_key(watch, travel_date)
                copied = dict(watch)
                copied["effective_date"] = travel_date
                groups[key].append(copied)

        self.last_group_count = len(groups)
        semaphore = asyncio.Semaphore(max(1, self.settings.poll_concurrency))

        async def wrapped(items: list[dict]) -> None:
            async with semaphore:
                await self._process_group(items)

        await asyncio.gather(*(wrapped(items) for items in groups.values()), return_exceptions=True)

    async def _process_group(self, watches: list[dict]) -> None:
        sample = watches[0]
        modes = tuple(TravelMode(mode) for mode in sample["modes"])
        request = SearchRequest(
            origin=sample["origin"],
            destination=sample["destination"],
            travel_date=sample["effective_date"],
            modes=modes,
            passengers=sample["passengers"],
        )
        snapshot = await self.orchestrator.search(request)
        watch_ids = sorted({int(item["id"]) for item in watches})
        await self.db.mark_checked(watch_ids)

        if snapshot.journeys:
            for watch in self._unique_watches(watches):
                filtered = snapshot
                max_price = watch.get("max_price_irr")
                if max_price:
                    journeys = [j for j in snapshot.journeys if j.price_irr <= int(max_price)]
                    if not journeys:
                        continue
                    filtered = type(snapshot)(
                        state=snapshot.state,
                        journeys=journeys,
                        provider_states=snapshot.provider_states,
                        errors=snapshot.errors,
                    )
                watch_id = int(watch["id"])
                if not await self.db.claim_notification(watch_id):
                    continue
                try:
                    await self.notifier.send_ticket_found(int(watch["user_id"]), watch_id, filtered)
                except Exception:
                    await self.db.update_watch_status(watch_id, "active")
                    logger.exception("Failed notifying user for watch %s", watch_id)
            return

        if self.cycle % max(1, self.settings.alt_search_every_n_cycles) != 0:
            return

        alt_candidates = [
            w for w in self._unique_watches(watches)
            if w["allow_alternatives"] and not w["alternative_notified"]
        ]
        if not alt_candidates:
            return
        alternatives = await self.route_engine.search(request)
        if not alternatives:
            return
        for watch in alt_candidates:
            watch_id = int(watch["id"])
            if not await self.db.claim_alternative_notification(watch_id):
                continue
            try:
                await self.notifier.send_alternative(int(watch["user_id"]), watch_id, alternatives)
            except Exception:
                logger.exception("Failed alternative notification for watch %s", watch_id)

    @staticmethod
    def _unique_watches(watches: list[dict]) -> list[dict]:
        by_id = {int(item["id"]): item for item in watches}
        return list(by_id.values())

    @staticmethod
    def _group_key(watch: dict, travel_date: date) -> str:
        modes = ",".join(sorted(watch["modes"]))
        return f"{watch['origin'].strip().lower()}|{watch['destination'].strip().lower()}|{travel_date.isoformat()}|{modes}|{watch['passengers']}"

    @staticmethod
    def _dates_for_watch(watch: dict) -> list[date]:
        center = date.fromisoformat(watch["travel_date"])
        flex = int(watch.get("flexibility_days") or 0)
        return [
            center + timedelta(days=delta)
            for delta in range(-flex, flex + 1)
            if center + timedelta(days=delta) >= date.today()
        ]
