from __future__ import annotations

import asyncio
import logging
from collections import defaultdict

from unipro.models import (
    AvailabilityState,
    Journey,
    ProviderResult,
    SearchRequest,
    SearchSnapshot,
    TicketGroup,
)
from unipro.providers.registry import ProviderRegistry

logger = logging.getLogger(__name__)


class SearchOrchestrator:
    def __init__(self, registry: ProviderRegistry):
        self.registry = registry

    async def search(self, request: SearchRequest) -> SearchSnapshot:
        providers = [provider for provider in self.registry.providers if provider.supports(request)]
        if not providers:
            return SearchSnapshot(AvailabilityState.UNAVAILABLE, [], {}, {})

        raw_results = await asyncio.gather(
            *(self._safe_search(provider, request) for provider in providers)
        )

        journeys: list[Journey] = []
        states: dict[str, AvailabilityState] = {}
        errors: dict[str, str] = {}
        for result in raw_results:
            states[result.provider_id] = result.state
            journeys.extend(result.journeys)
            if result.state == AvailabilityState.ERROR and result.message:
                errors[result.provider_id] = result.message

        if journeys:
            state = AvailabilityState.AVAILABLE
        else:
            non_error_states = [state for state in states.values() if state != AvailabilityState.ERROR]
            if non_error_states and all(state == AvailabilityState.NOT_RELEASED for state in non_error_states):
                state = AvailabilityState.NOT_RELEASED
            elif non_error_states:
                state = AvailabilityState.UNAVAILABLE
            else:
                state = AvailabilityState.ERROR

        return SearchSnapshot(state=state, journeys=journeys, provider_states=states, errors=errors)

    async def _safe_search(self, provider, request: SearchRequest) -> ProviderResult:
        try:
            return await provider.search(request)
        except Exception as exc:
            logger.exception("Provider %s failed", provider.provider_id)
            return ProviderResult(
                provider_id=provider.provider_id,
                state=AvailabilityState.ERROR,
                journeys=[],
                message=str(exc),
            )


def group_journeys(journeys: list[Journey]) -> list[TicketGroup]:
    groups: dict[str, list[Journey]] = defaultdict(list)
    for journey in journeys:
        groups[journey.identity_key].append(journey)
    result = [TicketGroup(identity_key=key, journeys=value) for key, value in groups.items()]
    return sorted(result, key=lambda group: (group.cheapest.price_irr, group.cheapest.departure_at))
