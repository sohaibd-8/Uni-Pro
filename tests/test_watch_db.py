import aiosqlite
import pytest

from unipro.db import Database


@pytest.mark.asyncio
async def test_watch_v2_columns_are_migrated(tmp_path):
    path = tmp_path / "unipro.db"
    db = Database(str(path))
    await db.init()

    async with aiosqlite.connect(path) as conn:
        rows = await (await conn.execute("PRAGMA table_info(watches)")).fetchall()
        columns = {row[1] for row in rows}

    assert {
        "last_state",
        "last_result_hash",
        "last_best_price_irr",
        "last_alerted_hash",
        "last_alerted_price_irr",
        "last_alerted_at",
        "last_available_at",
        "next_check_at",
        "check_count",
        "consecutive_misses",
        "last_provider_errors_json",
    }.issubset(columns)


@pytest.mark.asyncio
async def test_watch_observation_keeps_watch_active(tmp_path):
    path = tmp_path / "unipro.db"
    db = Database(str(path))
    await db.init()
    await db.upsert_user(1, "student", "Student")
    watch_id = await db.create_watch(
        user_id=1,
        origin="تهران",
        destination="مشهد",
        travel_date="2026-11-11",
        flexibility_days=0,
        modes=["train"],
    )

    await db.record_watch_observation(
        watch_id,
        state="available",
        result_hash="trip-set-1",
        best_price_irr=9_500_000,
        provider_errors={},
        next_check_at="2026-10-04T20:00:00+00:00",
    )
    await db.mark_watch_alerted(watch_id, "trip-set-1", 9_500_000)

    watch = await db.get_watch(watch_id)
    assert watch is not None
    assert watch["status"] == "active"
    assert watch["last_state"] == "available"
    assert watch["last_alerted_price_irr"] == 9_500_000
    assert watch["check_count"] == 1
