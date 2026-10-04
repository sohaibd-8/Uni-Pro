from datetime import datetime, timezone

from unipro.config import Settings
from unipro.engine.routes import AlternativeRouteEngine
from unipro.models import Journey, TravelMode


class DummyOrchestrator:
    pass


def journey(origin, destination, depart_hour, arrive_hour, price, service):
    return Journey(
        provider_id="demo",
        seller_name="Demo",
        mode=TravelMode.BUS,
        origin=origin,
        destination=destination,
        departure_at=datetime(2026, 11, 1, depart_hour, 0, tzinfo=timezone.utc),
        arrival_at=datetime(2026, 11, 1, arrive_hour, 0, tzinfo=timezone.utc),
        price_irr=price,
        booking_url="https://example.com",
        service_id=service,
    )


def test_combine_rejects_too_short_transfer():
    settings = Settings(min_transfer_minutes=75, max_transfer_wait_hours=12)
    engine = AlternativeRouteEngine(DummyOrchestrator(), settings)
    first = journey("A", "H", 8, 12, 100, "1")
    too_soon = journey("H", "B", 13, 17, 100, "2")
    good = journey("H", "B", 14, 18, 100, "3")

    result = engine._combine([first], [too_soon, good])
    assert len(result) == 1
    assert result[0].second_leg.service_id == "3"
