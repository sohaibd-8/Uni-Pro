from __future__ import annotations

from html import escape

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from unipro.engine.search import group_journeys
from unipro.models import AvailabilityState, RouteAlternative, SearchSnapshot
from unipro.utils.dates import format_clock, format_jalali


def format_irr(value: int) -> str:
    # Provider contracts expose fares in rials; users compare prices in tomans.
    return f"{round(value / 10):,} تومان"


def mode_icon(mode: str) -> str:
    return {"train": "🚆", "bus": "🚌", "flight": "✈️"}.get(mode, "🎫")


def render_snapshot(snapshot: SearchSnapshot, *, title: str = "نتیجه جست‌وجو") -> tuple[str, InlineKeyboardMarkup | None]:
    if snapshot.state == AvailabilityState.NOT_RELEASED:
        return (
            f"🗓 <b>{escape(title)}</b>\n\nفروش این تاریخ هنوز در Providerهای متصل باز نشده است.",
            None,
        )
    if snapshot.state == AvailabilityState.ERROR:
        return (
            f"⚠️ <b>{escape(title)}</b>\n\nفعلاً نتونستم از Providerها پاسخ مطمئن بگیرم. Watch می‌تونه فعال بمونه تا دوباره بررسی کنم.",
            None,
        )
    if not snapshot.journeys:
        return (
            f"😕 <b>{escape(title)}</b>\n\nفعلاً بلیت مستقیم مناسبی پیدا نکردم.",
            None,
        )

    groups = group_journeys(snapshot.journeys)[:5]
    lines = [f"✅ <b>{escape(title)}</b>", ""]
    buttons: list[list[InlineKeyboardButton]] = []
    for index, group in enumerate(groups, start=1):
        best = group.cheapest
        lines.extend(
            [
                f"{index}) {mode_icon(best.mode.value)} <b>{escape(best.origin)} → {escape(best.destination)}</b>",
                f"📅 {format_jalali(best.departure_at.date())} | ⏰ {format_clock(best.departure_at)}",
                f"💰 از <b>{format_irr(best.price_irr)}</b> — {escape(best.seller_name)}",
                f"🏪 {len(group.journeys)} فروشنده/منبع",
                "",
            ]
        )
        buttons.append(
            [InlineKeyboardButton(text=f"🎫 خرید گزینه {index}", url=best.booking_url)]
        )

    return "\n".join(lines).strip(), InlineKeyboardMarkup(inline_keyboard=buttons)


def render_alternatives(alternatives: list[RouteAlternative]) -> str:
    if not alternatives:
        return ""
    lines = ["🔀 <b>مسیرهای جایگزین</b>", ""]
    for index, alt in enumerate(alternatives, start=1):
        a, b = alt.first_leg, alt.second_leg
        lines.extend(
            [
                f"{index}) {mode_icon(a.mode.value)} {escape(a.origin)} → {escape(a.destination)}  +  {mode_icon(b.mode.value)} {escape(b.origin)} → {escape(b.destination)}",
                f"⏳ توقف بین دو سفر: {alt.transfer_minutes} دقیقه",
                f"💰 مجموع: <b>{format_irr(alt.total_price_irr)}</b>",
                f"🕒 زمان کل تقریبی: {alt.total_minutes // 60}س {alt.total_minutes % 60}د",
                "",
            ]
        )
    return "\n".join(lines).strip()


class NotificationService:
    def __init__(self, bot: Bot):
        self.bot = bot

    async def send_ticket_found(self, user_id: int, watch_id: int, snapshot: SearchSnapshot) -> None:
        text, keyboard = render_snapshot(snapshot, title="🚨 بلیت پیدا شد")
        rows = list(keyboard.inline_keyboard) if keyboard else []
        rows.append(
            [
                InlineKeyboardButton(text="🔄 ادامه پایش", callback_data=f"watch:resume:{watch_id}"),
                InlineKeyboardButton(text="⛔ توقف", callback_data=f"watch:cancel:{watch_id}"),
            ]
        )
        await self.bot.send_message(
            user_id,
            text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        )

    async def send_alternative(self, user_id: int, watch_id: int, alternatives: list[RouteAlternative]) -> None:
        text = render_alternatives(alternatives)
        if not text:
            return
        text += "\n\n👀 مسیر مستقیم رو هم همچنان زیر نظر می‌گیرم."
        await self.bot.send_message(
            user_id,
            text,
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="⛔ توقف Watch", callback_data=f"watch:cancel:{watch_id}")]
                ]
            ),
        )
