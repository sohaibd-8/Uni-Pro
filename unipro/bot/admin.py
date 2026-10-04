from __future__ import annotations

from html import escape

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from unipro.bot.keyboards import admin_menu
from unipro.config import Settings
from unipro.db import Database
from unipro.engine.watch import WatchRunner
from unipro.providers.registry import ProviderRegistry


class AdminStates(StatesGroup):
    broadcast = State()


def build_admin_router(
    *,
    db: Database,
    registry: ProviderRegistry,
    runner: WatchRunner,
    settings: Settings,
) -> Router:
    router = Router(name="admin")

    def allowed(user_id: int) -> bool:
        return user_id in settings.admin_id_set

    async def show_home(message, user_id: int) -> None:
        polling = await db.get_flag("polling_enabled", "1") == "1"
        stats = await db.stats()
        text = (
            "🛠 <b>UniPro Admin</b>\n\n"
            f"👤 کاربران: <b>{stats['users']}</b>\n"
            f"👀 Watch فعال: <b>{stats['active_watches']}</b>\n"
            f"📨 Watchهای Notify شده: <b>{stats['notified_watches']}</b>\n"
            f"🔁 Watch Engine: <b>{'فعال' if polling else 'متوقف'}</b>\n"
            f"🧩 Provider فعال: <b>{len(registry.providers)}</b>"
        )
        await message.edit_text(text, reply_markup=admin_menu(polling))

    @router.message(Command("admin"))
    async def admin_command(message: Message, state: FSMContext) -> None:
        if not allowed(message.from_user.id):
            return
        await state.clear()
        polling = await db.get_flag("polling_enabled", "1") == "1"
        stats = await db.stats()
        await message.answer(
            "🛠 <b>UniPro Admin</b>\n\n"
            f"👤 کاربران: <b>{stats['users']}</b>\n"
            f"👀 Watch فعال: <b>{stats['active_watches']}</b>\n"
            f"📨 Notify شده: <b>{stats['notified_watches']}</b>\n"
            f"🔁 Engine: <b>{'فعال' if polling else 'متوقف'}</b>",
            reply_markup=admin_menu(polling),
        )
        await db.audit("admin_open", message.from_user.id)

    @router.callback_query(F.data.startswith("admin:"))
    async def admin_callbacks(query: CallbackQuery, state: FSMContext) -> None:
        if not allowed(query.from_user.id):
            await query.answer("دسترسی ندارید.", show_alert=True)
            return

        action = query.data.split(":", 1)[1]
        if action == "home":
            await state.clear()
            await show_home(query.message, query.from_user.id)

        elif action == "stats":
            stats = await db.stats()
            await query.message.edit_text(
                "📊 <b>آمار UniPro</b>\n\n"
                f"کاربران: {stats['users']}\n"
                f"کل Watchها: {stats['total_watches']}\n"
                f"Watch فعال: {stats['active_watches']}\n"
                f"Notify شده: {stats['notified_watches']}\n\n"
                f"Search Group در آخرین چرخه: {runner.last_group_count}",
                reply_markup=_back_admin(),
            )

        elif action == "watches":
            watches = await db.list_recent_watches(15)
            if watches:
                lines = ["👀 <b>Watchهای اخیر</b>", "", "برای مدیریت روی Watch بزن:"]
                rows = []
                for w in watches:
                    lines.append(
                        f"#{w['id']} · {escape(w['origin'])} → {escape(w['destination'])} · "
                        f"<code>{w['status']}</code> · user {w['user_id']}"
                    )
                    rows.append([InlineKeyboardButton(
                        text=f"#{w['id']} {w['origin']} → {w['destination']}",
                        callback_data=f"admin:watch:{w['id']}",
                    )])
                rows.append([InlineKeyboardButton(text="⬅️ برگشت به پنل", callback_data="admin:home")])
                text = "\n".join(lines)
                await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
            else:
                await query.message.edit_text("👀 هنوز Watchی ثبت نشده.", reply_markup=_back_admin())

        elif action.startswith("watch:"):
            watch_id = int(action.split(":", 1)[1])
            watch = await db.get_watch(watch_id)
            if not watch:
                await query.message.edit_text("Watch پیدا نشد.", reply_markup=_back_admin())
            else:
                text = (
                    f"🧭 <b>Watch #{watch['id']}</b>\n\n"
                    f"User: <code>{watch['user_id']}</code>\n"
                    f"Route: {escape(watch['origin'])} → {escape(watch['destination'])}\n"
                    f"Date: <code>{watch['travel_date']}</code>\n"
                    f"Modes: <code>{', '.join(watch['modes'])}</code>\n"
                    f"Status: <code>{watch['status']}</code>\n"
                    f"Alternatives: {'yes' if watch['allow_alternatives'] else 'no'}"
                )
                await query.message.edit_text(
                    text,
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="▶️ فعال", callback_data=f"admin:watch_activate:{watch_id}"),
                         InlineKeyboardButton(text="⏸ توقف", callback_data=f"admin:watch_pause:{watch_id}")],
                        [InlineKeyboardButton(text="🗑 لغو", callback_data=f"admin:watch_cancel:{watch_id}")],
                        [InlineKeyboardButton(text="⬅️ Watchها", callback_data="admin:watches")],
                    ]),
                )

        elif action.startswith("watch_activate:"):
            watch_id = int(action.rsplit(":", 1)[1])
            await db.update_watch_status(watch_id, "active")
            await db.audit("admin_watch_activate", query.from_user.id, {"watch_id": watch_id})
            await query.answer("Watch فعال شد.", show_alert=True)
            return

        elif action.startswith("watch_pause:"):
            watch_id = int(action.rsplit(":", 1)[1])
            await db.update_watch_status(watch_id, "paused")
            await db.audit("admin_watch_pause", query.from_user.id, {"watch_id": watch_id})
            await query.answer("Watch متوقف شد.", show_alert=True)
            return

        elif action.startswith("watch_cancel:"):
            watch_id = int(action.rsplit(":", 1)[1])
            await db.update_watch_status(watch_id, "cancelled")
            await db.audit("admin_watch_cancel", query.from_user.id, {"watch_id": watch_id})
            await query.answer("Watch لغو شد.", show_alert=True)
            return

        elif action == "providers":
            lines = ["🧩 <b>Providerها</b>", "", *registry.status_lines()]
            if settings.demo_mode:
                lines.extend(["", "⚠️ Demo Mode فعاله؛ قیمت‌ها و لینک‌های Demo واقعی نیستند."])
            await query.message.edit_text("\n".join(lines), reply_markup=_back_admin())

        elif action == "toggle_polling":
            current = await db.get_flag("polling_enabled", "1") == "1"
            await db.set_flag("polling_enabled", "0" if current else "1")
            await db.audit("polling_toggle", query.from_user.id, {"enabled": not current})
            await show_home(query.message, query.from_user.id)

        elif action == "health":
            db_ok = await db.ping()
            polling = await db.get_flag("polling_enabled", "1") == "1"
            await query.message.edit_text(
                "❤️ <b>System Health</b>\n\n"
                f"Database: {'✅' if db_ok else '❌'}\n"
                f"Watch Engine: {'✅' if polling else '⏸'}\n"
                f"Last cycle: <code>{escape(runner.last_cycle_at or 'هنوز اجرا نشده')}</code>\n"
                f"Groups last cycle: {runner.last_group_count}\n"
                f"Providers: {len(registry.providers)}\n"
                f"Demo mode: {'ON' if settings.demo_mode else 'OFF'}",
                reply_markup=_back_admin(),
            )

        elif action == "broadcast":
            await state.set_state(AdminStates.broadcast)
            await query.message.edit_text(
                "📣 متن Broadcast رو بفرست.\n\nبرای لغو: /cancel",
                reply_markup=_back_admin(),
            )

        await query.answer()

    @router.message(AdminStates.broadcast, Command("cancel"))
    async def cancel_broadcast(message: Message, state: FSMContext) -> None:
        if not allowed(message.from_user.id):
            return
        await state.clear()
        await message.answer("Broadcast لغو شد. /admin")

    @router.message(AdminStates.broadcast)
    async def do_broadcast(message: Message, state: FSMContext) -> None:
        if not allowed(message.from_user.id):
            return
        text = message.html_text or message.text or ""
        if not text.strip():
            await message.answer("پیام خالیه.")
            return
        await state.clear()
        user_ids = await db.list_user_ids()
        sent = 0
        failed = 0
        for user_id in user_ids:
            try:
                await message.bot.send_message(user_id, text)
                sent += 1
            except Exception:
                failed += 1
        await db.audit("broadcast", message.from_user.id, {"sent": sent, "failed": failed})
        await message.answer(f"📣 Broadcast تمام شد.\n✅ ارسال: {sent}\n❌ خطا: {failed}\n\n/admin")

    return router


def _back_admin() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="⬅️ برگشت به پنل", callback_data="admin:home")]]
    )
