from __future__ import annotations

import asyncio
from datetime import timedelta

from unipro.config import Settings
from unipro.engine.search import SearchOrchestrator
from unipro.models import Journey, RouteAlternative, SearchRequest


DEFAULT_HUBS = ("تهران", "شیراز", "یزد", "اصفهان", "کرمان", "قم")


class AlternativeRouteEngine:
    def __init__(self, orchestrator: SearchOrchestrator, settings: Settings, hubs: tuple[str, ...] = DEFAULT_HUBS):
        self.orchestrator = orchestrator
        self.settings = settings
        self.hubs = hubs

    async def search(self, request: SearchRequest, limit: int = 3) -> list[RouteAlternative]:
        hubs = [hub for hub in self.hubs if hub not in {request.origin, request.destination}]
        results = await asyncio.gather(*(self._via_hub(request, hub) for hub in hubs))
        alternatives = [item for group in results for item in group]
        alternatives.sort(key=lambda item: item.score)
        return alternatives[:limit]

    async def _via_hub(self, request: SearchRequest, hub: str) -> list[RouteAlternative]:
        first_request = SearchRequest(
            origin=request.origin,
            destination=hub,
            travel_date=request.travel_date,
            modes=request.modes,
            passengers=request.passengers,
        )
        first_snapshot = await self.orchestrator.search(first_request)
        if not first_snapshot.journeys:
            return []

        second_dates = {j.arrival_at.date() for j in first_snapshot.journeys}
        second_dates.update({d + timedelta(days=1) for d in list(second_dates)})
        second_snapshots = await asyncio.gather(
            *(
                self.orchestrator.search(
                    SearchRequest(
                        origin=hub,
                        destination=request.destination,
                        travel_date=day,
                        modes=request.modes,
                        passengers=request.passengers,
                    )
                )
                for day in sorted(second_dates)
            )
        )
        second_journeys = [journey for snap in second_snapshots for journey in snap.journeys]
        return self._combine(first_snapshot.journeys, second_journeys)

    def _combine(self, first_legs: list[Journey], second_legs: list[Journey]) -> list[RouteAlternative]:
        result: list[RouteAlternative] = []
        min_transfer = timedelta(minutes=self.settings.min_transfer_minutes)
        max_wait = timedelta(hours=self.settings.max_transfer_wait_hours)

        for first in first_legs:
            for second in second_legs:
                if first.destination.strip().lower() != second.origin.strip().lower():
                    continue
                wait = second.departure_at - first.arrival_at
                if wait < min_transfer or wait > max_wait:
                    continue
                result.append(
                    RouteAlternative(
                        first_leg=first,
                        second_leg=second,
                        transfer_minutes=int(wait.total_seconds() // 60),
                    )
                )
        return result
