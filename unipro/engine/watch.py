from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from unipro.config import Settings
from unipro.db import Database
from unipro.engine.routes import AlternativeRouteEngine
from unipro.engine.search import SearchOrchestrator, group_journeys
from unipro.models import AvailabilityState, SearchRequest, SearchSnapshot, TravelMode
from unipro.notifications import NotificationService

logger = logging.getLogger(__name__)


def merge_snapshots(snapshots: list[SearchSnapshot]) -> SearchSnapshot:
    if not snapshots:
        return SearchSnapshot(AvailabilityState.ERROR, [], {}, {"watch": "no search snapshots"})

    journeys = [journey for snapshot in snapshots for journey in snapshot.journeys]
    states: dict[str, AvailabilityState] = {}
    errors: dict[str, str] = {}
    for index, snapshot in enumerate(snapshots):
        for provider, state in snapshot.provider_states.items():
            states[f"{provider}@{index}"] = state
        for provider, error in snapshot.errors.items():
            errors[f"{provider}@{index}"] = error

    if journeys:
        state = AvailabilityState.AVAILABLE
    elif all(snapshot.state == AvailabilityState.ERROR for snapshot in snapshots):
        state = AvailabilityState.ERROR
    else:
        non_error = [snapshot.state for snapshot in snapshots if snapshot.state != AvailabilityState.ERROR]
        if non_error and all(item == AvailabilityState.NOT_RELEASED for item in non_error):
            state = AvailabilityState.NOT_RELEASED
        else:
            state = AvailabilityState.UNAVAILABLE

    return SearchSnapshot(state=state, journeys=journeys, provider_states=states, errors=errors)


def result_signature(snapshot: SearchSnapshot) -> str | None:
    if not snapshot.journeys:
        return None
    compact = []
    for group in group_journeys(snapshot.journeys):
        compact.append(
            {
                "trip": group.identity_key,
                "best_price_irr": group.cheapest.price_irr,
            }
        )
    payload = json.dumps(compact, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def best_price(snapshot: SearchSnapshot) -> int | None:
    if not snapshot.journeys:
        return None
    return min(journey.price_irr for journey in snapshot.journeys)


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def alert_reason(
    watch: dict,
    snapshot: SearchSnapshot,
    signature: str | None,
    current_best_price: int | None,
    settings: Settings,
    *,
    now: datetime | None = None,
) -> str | None:
    if snapshot.state != AvailabilityState.AVAILABLE or not signature or current_best_price is None:
        return None

    previous_state = str(watch.get("last_state") or "")
    last_alerted_hash = watch.get("last_alerted_hash")
    previous_best = watch.get("last_best_price_irr")

    if previous_state != AvailabilityState.AVAILABLE.value:
        return "reappeared" if int(watch.get("check_count") or 0) > 0 else "found"

    if not last_alerted_hash:
        return "reappeared"

    if previous_best:
        absolute_drop = int(previous_best) - current_best_price
        percent_drop = (absolute_drop / int(previous_best)) * 100 if int(previous_best) > 0 else 0
        if (
            absolute_drop >= settings.watch_price_drop_min_irr
            and percent_drop >= settings.watch_price_drop_min_percent
        ):
            return "price_drop"

    if signature != last_alerted_hash:
        now = now or datetime.now(timezone.utc)
        last_alerted_at = _parse_iso(watch.get("last_alerted_at"))
        if last_alerted_at is None:
            return "new_option"
        elapsed = (now - last_alerted_at).total_seconds()
        if elapsed >= settings.watch_change_alert_cooldown_seconds:
            return "new_option"

    return None


def next_interval_seconds(
    watch: dict,
    state: AvailabilityState,
    settings: Settings,
    *,
    today: date | None = None,
) -> int:
    if state == AvailabilityState.ERROR:
        return settings.watch_error_retry_seconds

    if state == AvailabilityState.AVAILABLE:
        return settings.watch_interval_urgent_seconds

    if str(watch.get("last_state") or "") == AvailabilityState.AVAILABLE.value:
        return settings.watch_interval_urgent_seconds

    today = today or date.today()
    center = date.fromisoformat(watch["travel_date"])
    flex = int(watch.get("flexibility_days") or 0)
    last_possible = center + timedelta(days=flex)
    days = max(0, (last_possible - today).days)

    if days <= 1:
        return settings.watch_interval_urgent_seconds
    if days <= 7:
        return settings.watch_interval_near_seconds
    if days <= 30:
        return settings.watch_interval_mid_seconds
    return settings.watch_interval_far_seconds


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
                await asyncio.wait_for(
                    self._stop.wait(),
                    timeout=self.settings.poll_interval_seconds,
                )
            except asyncio.TimeoutError:
                pass

    async def stop(self) -> None:
        self._stop.set()

    async def run_cycle(self) -> None:
        self.cycle += 1
        now = datetime.now(timezone.utc)
        self.last_cycle_at = now.isoformat()

        if await self.db.get_flag("polling_enabled", "1") != "1":
            return

        due_watches = await self.db.list_due_active_watches(now.isoformat())
        active_watches: list[dict] = []
        request_by_key: dict[str, SearchRequest] = {}
        keys_by_watch: dict[int, list[str]] = defaultdict(list)

        for watch in due_watches:
            dates = self._dates_for_watch(watch)
            if not dates:
                await self.db.expire_watch(int(watch["id"]))
                continue
            active_watches.append(watch)
            modes = tuple(TravelMode(mode) for mode in watch["modes"])
            for travel_date in dates:
                key = self._group_key(watch, travel_date)
                keys_by_watch[int(watch["id"])].append(key)
                request_by_key.setdefault(
                    key,
                    SearchRequest(
                        origin=watch["origin"],
                        destination=watch["destination"],
                        travel_date=travel_date,
                        modes=modes,
                        passengers=watch["passengers"],
                    ),
                )

        self.last_group_count = len(request_by_key)
        if not request_by_key:
            return

        snapshots = await self._search_groups(request_by_key)

        for watch in active_watches:
            try:
                await self._evaluate_watch(
                    watch,
                    [snapshots[key] for key in keys_by_watch[int(watch["id"])]],
                    now=now,
                )
            except Exception:
                logger.exception("Failed evaluating watch %s", watch.get("id"))

    async def _search_groups(
        self,
        requests: dict[str, SearchRequest],
    ) -> dict[str, SearchSnapshot]:
        semaphore = asyncio.Semaphore(max(1, self.settings.poll_concurrency))
        results: dict[str, SearchSnapshot] = {}

        async def run_one(key: str, request: SearchRequest) -> None:
            async with semaphore:
                results[key] = await self.orchestrator.search(request)

        await asyncio.gather(*(run_one(key, request) for key, request in requests.items()))
        return results

    async def _evaluate_watch(
        self,
        watch: dict,
        snapshots: list[SearchSnapshot],
        *,
        now: datetime,
    ) -> None:
        combined = merge_snapshots(snapshots)

        max_price = watch.get("max_price_irr")
        if max_price and combined.journeys:
            filtered = [
                journey
                for journey in combined.journeys
                if journey.price_irr <= int(max_price)
            ]
            combined = SearchSnapshot(
                state=AvailabilityState.AVAILABLE if filtered else AvailabilityState.UNAVAILABLE,
                journeys=filtered,
                provider_states=combined.provider_states,
                errors=combined.errors,
            )

        signature = result_signature(combined)
        current_best = best_price(combined)
        reason = alert_reason(
            watch,
            combined,
            signature,
            current_best,
            self.settings,
            now=now,
        )

        interval = next_interval_seconds(watch, combined.state, self.settings)
        next_check_at = (now + timedelta(seconds=interval)).isoformat()

        await self.db.record_watch_observation(
            int(watch["id"]),
            state=combined.state.value,
            result_hash=signature,
            best_price_irr=current_best,
            provider_errors=combined.errors,
            next_check_at=next_check_at,
        )

        if reason and signature:
            try:
                await self.notifier.send_ticket_found(
                    int(watch["user_id"]),
                    int(watch["id"]),
                    combined,
                    reason=reason,
                )
                await self.db.mark_watch_alerted(int(watch["id"]), signature)
            except Exception:
                logger.exception("Failed notifying user for watch %s", watch["id"])

        if combined.journeys:
            return

        check_number = int(watch.get("check_count") or 0) + 1
        if check_number % max(1, self.settings.alt_search_every_n_cycles) != 0:
            return
        if not watch["allow_alternatives"] or watch["alternative_notified"]:
            return

        center_request = SearchRequest(
            origin=watch["origin"],
            destination=watch["destination"],
            travel_date=date.fromisoformat(watch["travel_date"]),
            modes=tuple(TravelMode(mode) for mode in watch["modes"]),
            passengers=watch["passengers"],
        )
        alternatives = await self.route_engine.search(center_request)
        if not alternatives:
            return

        watch_id = int(watch["id"])
        if not await self.db.claim_alternative_notification(watch_id):
            return
        try:
            await self.notifier.send_alternative(
                int(watch["user_id"]),
                watch_id,
                alternatives,
            )
        except Exception:
            logger.exception("Failed alternative notification for watch %s", watch_id)

    @staticmethod
    def _group_key(watch: dict, travel_date: date) -> str:
        modes = ",".join(sorted(watch["modes"]))
        return (
            f"{watch['origin'].strip().lower()}|"
            f"{watch['destination'].strip().lower()}|"
            f"{travel_date.isoformat()}|{modes}|{watch['passengers']}"
        )

    @staticmethod
    def _dates_for_watch(watch: dict) -> list[date]:
        center = date.fromisoformat(watch["travel_date"])
        flex = int(watch.get("flexibility_days") or 0)
        today = date.today()
        return [
            center + timedelta(days=delta)
            for delta in range(-flex, flex + 1)
            if center + timedelta(days=delta) >= today
        ]
