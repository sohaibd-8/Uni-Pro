from datetime import date, datetime, timedelta, timezone

from unipro.config import Settings
from unipro.engine.watch import alert_reason, next_interval_seconds, result_signature
from unipro.models import AvailabilityState, Journey, SearchSnapshot, TravelMode


def journey(service_id: str, price: int, hour: int = 18) -> Journey:
    depart = datetime(2026, 11, 11, hour, 0, tzinfo=timezone.utc)
    return Journey(
        provider_id="demo",
        seller_name="Seller",
        mode=TravelMode.TRAIN,
        origin="تهران",
        destination="مشهد",
        departure_at=depart,
        arrival_at=depart + timedelta(hours=12),
        price_irr=price,
        booking_url="https://example.com",
        service_id=service_id,
    )


def snapshot(*journeys: Journey) -> SearchSnapshot:
    return SearchSnapshot(
        state=AvailabilityState.AVAILABLE if journeys else AvailabilityState.UNAVAILABLE,
        journeys=list(journeys),
        provider_states={},
        errors={},
    )


def settings() -> Settings:
    return Settings(
        watch_change_alert_cooldown_seconds=900,
        watch_price_drop_min_irr=500_000,
        watch_price_drop_min_percent=3,
        watch_interval_urgent_seconds=60,
        watch_interval_near_seconds=120,
        watch_interval_mid_seconds=300,
        watch_interval_far_seconds=600,
        watch_error_retry_seconds=90,
    )


def base_watch() -> dict:
    return {
        "travel_date": "2026-11-11",
        "flexibility_days": 0,
        "last_state": "available",
        "last_alerted_hash": None,
        "last_alerted_at": None,
        "last_alerted_price_irr": None,
        "last_best_price_irr": None,
        "check_count": 3,
    }


def test_result_signature_ignores_small_price_changes():
    first = result_signature(snapshot(journey("401", 10_000_000)))
    second = result_signature(snapshot(journey("401", 9_900_000)))
    assert first == second


def test_result_signature_changes_when_new_departure_appears():
    first = result_signature(snapshot(journey("401", 10_000_000)))
    second = result_signature(
        snapshot(
            journey("401", 10_000_000),
            journey("402", 10_000_000, hour=20),
        )
    )
    assert first != second


def test_first_available_result_alerts():
    current = snapshot(journey("401", 10_000_000))
    watch = base_watch()
    watch["last_state"] = "unavailable"
    assert alert_reason(
        watch,
        current,
        result_signature(current),
        10_000_000,
        settings(),
    ) == "reappeared"


def test_material_price_drop_alerts_against_last_alerted_price():
    current = snapshot(journey("401", 9_000_000))
    watch = base_watch()
    watch["last_alerted_hash"] = result_signature(current)
    watch["last_alerted_price_irr"] = 10_000_000
    watch["last_best_price_irr"] = 9_800_000

    assert alert_reason(
        watch,
        current,
        result_signature(current),
        9_000_000,
        settings(),
    ) == "price_drop"


def test_small_price_drop_does_not_spam():
    current = snapshot(journey("401", 9_800_000))
    watch = base_watch()
    watch["last_alerted_hash"] = result_signature(current)
    watch["last_alerted_price_irr"] = 10_000_000

    assert alert_reason(
        watch,
        current,
        result_signature(current),
        9_800_000,
        settings(),
    ) is None


def test_new_trip_respects_change_cooldown():
    old = snapshot(journey("401", 10_000_000))
    current = snapshot(
        journey("401", 10_000_000),
        journey("402", 11_000_000, hour=20),
    )
    watch = base_watch()
    watch["last_alerted_hash"] = result_signature(old)
    now = datetime(2026, 10, 4, 12, 0, tzinfo=timezone.utc)
    watch["last_alerted_at"] = (now - timedelta(minutes=20)).isoformat()

    assert alert_reason(
        watch,
        current,
        result_signature(current),
        10_000_000,
        settings(),
        now=now,
    ) == "new_option"


def test_adaptive_intervals():
    cfg = settings()
    watch = base_watch()
    watch["last_state"] = "unavailable"

    watch["travel_date"] = "2026-10-05"
    assert next_interval_seconds(
        watch,
        AvailabilityState.UNAVAILABLE,
        cfg,
        today=date(2026, 10, 4),
    ) == 60

    watch["travel_date"] = "2026-10-10"
    assert next_interval_seconds(
        watch,
        AvailabilityState.UNAVAILABLE,
        cfg,
        today=date(2026, 10, 4),
    ) == 120

    watch["travel_date"] = "2026-10-24"
    assert next_interval_seconds(
        watch,
        AvailabilityState.UNAVAILABLE,
        cfg,
        today=date(2026, 10, 4),
    ) == 300

    watch["travel_date"] = "2026-12-20"
    assert next_interval_seconds(
        watch,
        AvailabilityState.UNAVAILABLE,
        cfg,
        today=date(2026, 10, 4),
    ) == 600
