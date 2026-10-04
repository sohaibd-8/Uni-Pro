from datetime import datetime, timezone

from unipro.engine.search import group_journeys
from unipro.models import Journey, TravelMode


def make_journey(provider: str, seller: str, price: int) -> Journey:
    return Journey(
        provider_id=provider,
        seller_name=seller,
        mode=TravelMode.TRAIN,
        origin="بندرعباس",
        destination="شیراز",
        departure_at=datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc),
        arrival_at=datetime(2026, 11, 1, 20, 0, tzinfo=timezone.utc),
        price_irr=price,
        booking_url="https://example.com",
        service_id="T-1",
    )


def test_groups_same_service_and_finds_cheapest():
    groups = group_journeys(
        [
            make_journey("a", "Seller A", 9_000_000),
            make_journey("b", "Seller B", 8_500_000),
        ]
    )
    assert len(groups) == 1
    assert groups[0].cheapest.seller_name == "Seller B"
    assert groups[0].cheapest.price_irr == 8_500_000
