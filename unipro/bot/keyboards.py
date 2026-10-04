from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔔 بلیت این تاریخ اومد، خبرم کن", callback_data="action:watch")],
            [InlineKeyboardButton(text="🔍 الان بلیت پیدا کن", callback_data="action:search")],
            [InlineKeyboardButton(text="🆘 هرجوری شده برسون من", callback_data="action:rescue")],
            [InlineKeyboardButton(text="👀 سفرهای تحت نظر", callback_data="watches:list")],
        ]
    )


def flexibility_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="فقط همین تاریخ", callback_data="flex:0")],
            [InlineKeyboardButton(text="± ۱ روز", callback_data="flex:1")],
        ]
    )


def mode_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🚆 فقط قطار", callback_data="mode:train")],
            [InlineKeyboardButton(text="🚌 فقط اتوبوس", callback_data="mode:bus")],
            [InlineKeyboardButton(text="🚆🚌 هر دو", callback_data="mode:both")],
        ]
    )


def alternatives_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ آره، راه جایگزین هم پیدا کن", callback_data="alt:1")],
            [InlineKeyboardButton(text="❌ فقط مسیر مستقیم", callback_data="alt:0")],
        ]
    )


def watches_keyboard(watches: list[dict]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for watch in watches[:10]:
        status = "🟢" if watch["status"] == "active" else "🟡" if watch["status"] == "notified" else "⚫"
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{status} #{watch['id']} {watch['origin']} → {watch['destination']}",
                    callback_data=f"watch:view:{watch['id']}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="⬅️ منوی اصلی", callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_menu(polling_enabled: bool) -> InlineKeyboardMarkup:
    toggle_text = "⏸ توقف Watch Engine" if polling_enabled else "▶️ فعال‌سازی Watch Engine"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📊 آمار", callback_data="admin:stats")],
            [InlineKeyboardButton(text="👀 Watchهای اخیر", callback_data="admin:watches")],
            [InlineKeyboardButton(text="🧩 Providerها", callback_data="admin:providers")],
            [InlineKeyboardButton(text=toggle_text, callback_data="admin:toggle_polling")],
            [InlineKeyboardButton(text="❤️ سلامت سیستم", callback_data="admin:health")],
            [InlineKeyboardButton(text="📣 Broadcast", callback_data="admin:broadcast")],
            [InlineKeyboardButton(text="🔄 تازه‌سازی", callback_data="admin:home")],
        ]
    )
