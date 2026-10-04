from __future__ import annotations

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from unipro.models import AvailabilityState, Journey, ProviderResult, SearchRequest, TravelMode
from unipro.providers.base import TravelProvider


class DemoProvider(TravelProvider):
    """Deterministic fake provider for product testing before real API onboarding."""

    def __init__(
        self,
        provider_id: str,
        display_name: str,
        modes: set[TravelMode],
        price_multiplier: float = 1.0,
        timezone_name: str = "Asia/Tehran",
    ) -> None:
        self.provider_id = provider_id
        self.display_name = display_name
        self.supported_modes = frozenset(modes)
        self.price_multiplier = price_multiplier
        self.tz = ZoneInfo(timezone_name)

    async def search(self, request: SearchRequest) -> ProviderResult:
        supported = [mode for mode in request.modes if mode in self.supported_modes]
        if not supported:
            return ProviderResult(self.provider_id, AvailabilityState.UNAVAILABLE, [])

        origin = self._normalize_city(request.origin)
        destination = self._normalize_city(request.destination)

        if (origin, destination) in {("بندرعباس", "تهران"), ("bandar abbas", "tehran")}:
            return ProviderResult(self.provider_id, AvailabilityState.UNAVAILABLE, [])

        routes = {
            ("بندرعباس", "شیراز"),
            ("شیراز", "تهران"),
            ("بندرعباس", "یزد"),
            ("یزد", "تهران"),
            ("تهران", "شیراز"),
            ("شیراز", "بندرعباس"),
            ("tehran", "shiraz"),
            ("bandar abbas", "shiraz"),
            ("shiraz", "tehran"),
        }
        if (origin, destination) not in routes:
            return ProviderResult(self.provider_id, AvailabilityState.UNAVAILABLE, [])

        journeys: list[Journey] = []
        for mode in supported:
            if mode == TravelMode.TRAIN:
                journeys.append(self._train(request))
            elif mode == TravelMode.BUS:
                journeys.append(self._bus(request))

        state = AvailabilityState.AVAILABLE if journeys else AvailabilityState.UNAVAILABLE
        return ProviderResult(self.provider_id, state, journeys)

    def _train(self, request: SearchRequest) -> Journey:
        depart = datetime.combine(request.travel_date, time(19, 30), self.tz)
        arrive = depart + timedelta(hours=11)
        base = self._base_price(request.origin, request.destination, TravelMode.TRAIN)
        return Journey(
            provider_id=self.provider_id,
            seller_name=self.display_name,
            mode=TravelMode.TRAIN,
            origin=request.origin,
            destination=request.destination,
            departure_at=depart,
            arrival_at=arrive,
            price_irr=int(base * self.price_multiplier),
            booking_url=f"https://example.com/demo/{self.provider_id}/train",
            service_id="DEMO-T-101",
            seats=4,
        )

    def _bus(self, request: SearchRequest) -> Journey:
        depart = datetime.combine(request.travel_date, time(8, 0), self.tz)
        arrive = depart + timedelta(hours=8)
        base = self._base_price(request.origin, request.destination, TravelMode.BUS)
        return Journey(
            provider_id=self.provider_id,
            seller_name=self.display_name,
            mode=TravelMode.BUS,
            origin=request.origin,
            destination=request.destination,
            departure_at=depart,
            arrival_at=arrive,
            price_irr=int(base * self.price_multiplier),
            booking_url=f"https://example.com/demo/{self.provider_id}/bus",
            service_id="DEMO-B-201",
            seats=7,
        )

    @staticmethod
    def _normalize_city(value: str) -> str:
        return value.strip().lower().replace("بندر عباس", "بندرعباس")

    @staticmethod
    def _base_price(origin: str, destination: str, mode: TravelMode) -> int:
        seed = sum(ord(c) for c in f"{origin}-{destination}-{mode.value}")
        if mode == TravelMode.TRAIN:
            return 8_000_000 + (seed % 2_000_000)
        return 5_000_000 + (seed % 1_500_000)
