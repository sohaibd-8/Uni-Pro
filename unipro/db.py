from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import aiosqlite


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    def __init__(self, path: str):
        self.path = path

    async def init(self) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.executescript(
                """
                PRAGMA journal_mode=WAL;
                PRAGMA foreign_keys=ON;

                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    created_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS watches (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    origin TEXT NOT NULL,
                    destination TEXT NOT NULL,
                    travel_date TEXT NOT NULL,
                    flexibility_days INTEGER NOT NULL DEFAULT 0,
                    modes_json TEXT NOT NULL,
                    passengers INTEGER NOT NULL DEFAULT 1,
                    max_price_irr INTEGER,
                    allow_alternatives INTEGER NOT NULL DEFAULT 1,
                    status TEXT NOT NULL DEFAULT 'active',
                    last_checked_at TEXT,
                    notified_at TEXT,
                    alternative_notified INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_watches_status ON watches(status);
                CREATE INDEX IF NOT EXISTS idx_watches_user ON watches(user_id);
                CREATE INDEX IF NOT EXISTS idx_watches_route ON watches(origin, destination, travel_date, status);

                CREATE TABLE IF NOT EXISTS system_flags (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    actor_user_id INTEGER,
                    action TEXT NOT NULL,
                    details_json TEXT,
                    created_at TEXT NOT NULL
                );
                """
            )
            await self._ensure_watch_columns(db)
            # Watch V1 stopped monitoring after the first ticket alert by
            # marking rows as "notified". Watch V2 is continuous, so revive
            # those rows; past dates will be expired by WatchRunner.
            await db.execute(
                "UPDATE watches SET status='active', next_check_at=NULL WHERE status='notified'"
            )
            await db.execute(
                "INSERT OR IGNORE INTO system_flags(key, value, updated_at) VALUES('polling_enabled', '1', ?)",
                (_now(),),
            )
            await db.commit()

    @staticmethod
    async def _ensure_watch_columns(db: aiosqlite.Connection) -> None:
        """Forward-only lightweight migration for existing Railway SQLite volumes."""
        rows = await (await db.execute("PRAGMA table_info(watches)")).fetchall()
        existing = {str(row[1]) for row in rows}
        columns = {
            "last_state": "TEXT",
            "last_result_hash": "TEXT",
            "last_best_price_irr": "INTEGER",
            "last_alerted_hash": "TEXT",
            "last_alerted_price_irr": "INTEGER",
            "last_alerted_at": "TEXT",
            "last_available_at": "TEXT",
            "next_check_at": "TEXT",
            "check_count": "INTEGER NOT NULL DEFAULT 0",
            "consecutive_misses": "INTEGER NOT NULL DEFAULT 0",
            "last_provider_errors_json": "TEXT NOT NULL DEFAULT '{}'",
        }
        for name, definition in columns.items():
            if name not in existing:
                await db.execute(f"ALTER TABLE watches ADD COLUMN {name} {definition}")

    async def ping(self) -> bool:
        try:
            async with aiosqlite.connect(self.path) as db:
                row = await (await db.execute("SELECT 1")).fetchone()
                return bool(row and row[0] == 1)
        except Exception:
            return False

    async def upsert_user(self, user_id: int, username: str | None, first_name: str | None) -> None:
        now = _now()
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """
                INSERT INTO users(user_id, username, first_name, created_at, last_seen_at)
                VALUES(?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    username=excluded.username,
                    first_name=excluded.first_name,
                    last_seen_at=excluded.last_seen_at
                """,
                (user_id, username, first_name, now, now),
            )
            await db.commit()

    async def list_user_ids(self) -> list[int]:
        async with aiosqlite.connect(self.path) as db:
            rows = await (await db.execute("SELECT user_id FROM users ORDER BY created_at ASC")).fetchall()
            return [int(row[0]) for row in rows]

    async def create_watch(
        self,
        *,
        user_id: int,
        origin: str,
        destination: str,
        travel_date: str,
        flexibility_days: int,
        modes: list[str],
        passengers: int = 1,
        max_price_irr: int | None = None,
        allow_alternatives: bool = True,
    ) -> int:
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                """
                INSERT INTO watches(
                    user_id, origin, destination, travel_date, flexibility_days,
                    modes_json, passengers, max_price_irr, allow_alternatives,
                    status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?)
                """,
                (
                    user_id,
                    origin.strip(),
                    destination.strip(),
                    travel_date,
                    flexibility_days,
                    json.dumps(modes, ensure_ascii=False),
                    passengers,
                    max_price_irr,
                    1 if allow_alternatives else 0,
                    _now(),
                ),
            )
            await db.commit()
            return int(cursor.lastrowid)

    async def list_user_watches(self, user_id: int, limit: int = 20) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            rows = await (
                await db.execute(
                    "SELECT * FROM watches WHERE user_id=? ORDER BY id DESC LIMIT ?",
                    (user_id, limit),
                )
            ).fetchall()
            return [self._decode_watch(dict(row)) for row in rows]

    async def get_watch(self, watch_id: int) -> dict[str, Any] | None:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            row = await (await db.execute("SELECT * FROM watches WHERE id=?", (watch_id,))).fetchone()
            return self._decode_watch(dict(row)) if row else None

    async def list_active_watches(self) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            rows = await (
                await db.execute("SELECT * FROM watches WHERE status='active' ORDER BY id ASC")
            ).fetchall()
            return [self._decode_watch(dict(row)) for row in rows]

    async def list_due_active_watches(self, now_iso: str | None = None) -> list[dict[str, Any]]:
        now_iso = now_iso or _now()
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            rows = await (
                await db.execute(
                    """
                    SELECT * FROM watches
                    WHERE status='active'
                      AND (next_check_at IS NULL OR next_check_at <= ?)
                    ORDER BY id ASC
                    """,
                    (now_iso,),
                )
            ).fetchall()
            return [self._decode_watch(dict(row)) for row in rows]

    async def list_recent_watches(self, limit: int = 20) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            rows = await (
                await db.execute("SELECT * FROM watches ORDER BY id DESC LIMIT ?", (limit,))
            ).fetchall()
            return [self._decode_watch(dict(row)) for row in rows]

    async def update_watch_status(self, watch_id: int, status: str) -> None:
        async with aiosqlite.connect(self.path) as db:
            if status == "active":
                await db.execute(
                    "UPDATE watches SET status='active', next_check_at=NULL WHERE id=?",
                    (watch_id,),
                )
            else:
                await db.execute(
                    "UPDATE watches SET status=?, next_check_at=NULL WHERE id=?",
                    (status, watch_id),
                )
            await db.commit()

    async def mark_checked(self, watch_ids: list[int]) -> None:
        if not watch_ids:
            return
        placeholders = ",".join("?" for _ in watch_ids)
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                f"UPDATE watches SET last_checked_at=? WHERE id IN ({placeholders})",
                (_now(), *watch_ids),
            )
            await db.commit()

    async def record_watch_observation(
        self,
        watch_id: int,
        *,
        state: str,
        result_hash: str | None,
        best_price_irr: int | None,
        provider_errors: dict[str, str],
        next_check_at: str,
    ) -> None:
        now = _now()
        async with aiosqlite.connect(self.path) as db:
            if state == "error":
                await db.execute(
                    """
                    UPDATE watches SET
                        last_checked_at=?,
                        next_check_at=?,
                        check_count=check_count+1,
                        last_provider_errors_json=?
                    WHERE id=? AND status='active'
                    """,
                    (
                        now,
                        next_check_at,
                        json.dumps(provider_errors, ensure_ascii=False),
                        watch_id,
                    ),
                )
            else:
                await db.execute(
                    """
                    UPDATE watches SET
                        last_checked_at=?,
                        last_state=?,
                        last_result_hash=?,
                        last_best_price_irr=?,
                        last_available_at=CASE WHEN ?='available' THEN ? ELSE last_available_at END,
                        next_check_at=?,
                        check_count=check_count+1,
                        consecutive_misses=CASE WHEN ?='available' THEN 0 ELSE consecutive_misses+1 END,
                        last_alerted_hash=CASE
                            WHEN ?!='available' AND consecutive_misses >= 1 THEN NULL
                            ELSE last_alerted_hash
                        END,
                        last_provider_errors_json=?
                    WHERE id=? AND status='active'
                    """,
                    (
                        now,
                        state,
                        result_hash,
                        best_price_irr,
                        state,
                        now,
                        next_check_at,
                        state,
                        state,
                        json.dumps(provider_errors, ensure_ascii=False),
                        watch_id,
                    ),
                )
            await db.commit()

    async def mark_watch_alerted(
        self,
        watch_id: int,
        alert_hash: str,
        best_price_irr: int | None,
    ) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """
                UPDATE watches SET
                    last_alerted_hash=?,
                    last_alerted_price_irr=?,
                    last_alerted_at=?
                WHERE id=? AND status='active'
                """,
                (alert_hash, best_price_irr, _now(), watch_id),
            )
            await db.commit()

    async def expire_watch(self, watch_id: int) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "UPDATE watches SET status='expired', next_check_at=NULL WHERE id=? AND status='active'",
                (watch_id,),
            )
            await db.commit()

    async def claim_notification(self, watch_id: int) -> bool:
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                "UPDATE watches SET status='notified', notified_at=? WHERE id=? AND status='active'",
                (_now(), watch_id),
            )
            await db.commit()
            return cursor.rowcount == 1

    async def claim_alternative_notification(self, watch_id: int) -> bool:
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                "UPDATE watches SET alternative_notified=1 WHERE id=? AND alternative_notified=0 AND status='active'",
                (watch_id,),
            )
            await db.commit()
            return cursor.rowcount == 1

    async def set_flag(self, key: str, value: str) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """
                INSERT INTO system_flags(key, value, updated_at) VALUES(?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
                """,
                (key, value, _now()),
            )
            await db.commit()

    async def get_flag(self, key: str, default: str | None = None) -> str | None:
        async with aiosqlite.connect(self.path) as db:
            row = await (await db.execute("SELECT value FROM system_flags WHERE key=?", (key,))).fetchone()
            return str(row[0]) if row else default

    async def stats(self) -> dict[str, int]:
        async with aiosqlite.connect(self.path) as db:
            users = (await (await db.execute("SELECT COUNT(*) FROM users")).fetchone())[0]
            active = (await (await db.execute("SELECT COUNT(*) FROM watches WHERE status='active'")).fetchone())[0]
            notified = (await (await db.execute("SELECT COUNT(*) FROM watches WHERE status='notified'")).fetchone())[0]
            total = (await (await db.execute("SELECT COUNT(*) FROM watches")).fetchone())[0]
            return {
                "users": int(users),
                "active_watches": int(active),
                "notified_watches": int(notified),
                "total_watches": int(total),
            }

    async def audit(self, action: str, actor_user_id: int | None = None, details: dict[str, Any] | None = None) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "INSERT INTO audit_log(actor_user_id, action, details_json, created_at) VALUES(?, ?, ?, ?)",
                (actor_user_id, action, json.dumps(details or {}, ensure_ascii=False), _now()),
            )
            await db.commit()

    @staticmethod
    def _decode_watch(row: dict[str, Any]) -> dict[str, Any]:
        row["modes"] = json.loads(row.pop("modes_json"))
        row["allow_alternatives"] = bool(row["allow_alternatives"])
        row["alternative_notified"] = bool(row["alternative_notified"])
        raw_errors = row.get("last_provider_errors_json") or "{}"
        try:
            row["last_provider_errors"] = json.loads(raw_errors)
        except (TypeError, json.JSONDecodeError):
            row["last_provider_errors"] = {}
        return row
