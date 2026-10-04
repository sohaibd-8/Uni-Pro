from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum
from typing import Any


class TravelMode(StrEnum):
    TRAIN = "train"
    BUS = "bus"
    FLIGHT = "flight"


class AvailabilityState(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    NOT_RELEASED = "not_released"
    ERROR = "error"


@dataclass(slots=True, frozen=True)
class SearchRequest:
    origin: str
    destination: str
    travel_date: date
    modes: tuple[TravelMode, ...]
    passengers: int = 1

    @property
    def key(self) -> str:
        mode_key = ",".join(sorted(mode.value for mode in self.modes))
        return f"{self.origin.strip().lower()}|{self.destination.strip().lower()}|{self.travel_date.isoformat()}|{mode_key}|{self.passengers}"


@dataclass(slots=True)
class Journey:
    provider_id: str
    seller_name: str
    mode: TravelMode
    origin: str
    destination: str
    departure_at: datetime
    arrival_at: datetime
    price_irr: int
    booking_url: str
    service_id: str
    seats: int | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def identity_key(self) -> str:
        return "|".join(
            [
                self.mode.value,
                self.origin.strip().lower(),
                self.destination.strip().lower(),
                self.departure_at.isoformat(timespec="minutes"),
                self.arrival_at.isoformat(timespec="minutes"),
                self.service_id.strip().lower(),
            ]
        )


@dataclass(slots=True)
class ProviderResult:
    provider_id: str
    state: AvailabilityState
    journeys: list[Journey] = field(default_factory=list)
    message: str | None = None


@dataclass(slots=True)
class SearchSnapshot:
    state: AvailabilityState
    journeys: list[Journey]
    provider_states: dict[str, AvailabilityState]
    errors: dict[str, str]


@dataclass(slots=True)
class TicketGroup:
    identity_key: str
    journeys: list[Journey]

    @property
    def cheapest(self) -> Journey:
        return min(self.journeys, key=lambda item: item.price_irr)

    @property
    def most_expensive(self) -> Journey:
        return max(self.journeys, key=lambda item: item.price_irr)


@dataclass(slots=True)
class RouteAlternative:
    first_leg: Journey
    second_leg: Journey
    transfer_minutes: int

    @property
    def total_price_irr(self) -> int:
        return self.first_leg.price_irr + self.second_leg.price_irr

    @property
    def total_minutes(self) -> int:
        delta = self.second_leg.arrival_at - self.first_leg.departure_at
        return max(0, int(delta.total_seconds() // 60))

    @property
    def score(self) -> float:
        price_component = self.total_price_irr / 100_000
        duration_component = self.total_minutes / 30
        transfer_component = self.transfer_minutes / 60
        return price_component + duration_component + transfer_component
