from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from html import escape

from aiogram import F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from unipro.bot.keyboards import (
    alternatives_keyboard,
    flexibility_keyboard,
    main_menu,
    mode_keyboard,
    watches_keyboard,
)
from unipro.config import Settings
from unipro.db import Database
from unipro.engine.routes import AlternativeRouteEngine
from unipro.engine.search import SearchOrchestrator
from unipro.engine.watch import (
    best_price,
    merge_snapshots,
    next_interval_seconds,
    result_signature,
)
from unipro.models import SearchRequest, TravelMode
from unipro.notifications import render_alternatives, render_snapshot
from unipro.utils.dates import format_jalali, parse_user_date


class TripFlow(StatesGroup):
    origin = State()
    destination = State()
    travel_date = State()
    flexibility = State()
    modes = State()
    alternatives = State()
    deadline = State()
    budget = State()


def build_user_router(
    db: Database,
    orchestrator: SearchOrchestrator,
    route_engine: AlternativeRouteEngine,
    settings: Settings,
) -> Router:
    router = Router(name="user")

    async def remember(message_or_query) -> int:
        user = message_or_query.from_user
        await db.upsert_user(user.id, user.username, user.first_name)
        return user.id

    @router.message(Command("id"))
    async def show_id(message: Message) -> None:
        await remember(message)
        await message.answer(f"شناسه عددی تلگرام شما: <code>{message.from_user.id}</code>")

    @router.message(Command("start"))
    async def start(message: Message, state: FSMContext) -> None:
        await state.clear()
        await remember(message)
        await message.answer(
            "🎓 <b>UniPro</b>\nدستیار زندگی دانشجویی\n\nسفرت رو بسپر به من 👋",
            reply_markup=main_menu(),
        )

    @router.callback_query(F.data == "menu:main")
    async def menu(query: CallbackQuery, state: FSMContext) -> None:
        await state.clear()
        await remember(query)
        await query.message.edit_text(
            "🎓 <b>UniPro</b>\nدستیار زندگی دانشجویی\n\nسفرت رو بسپر به من 👋",
            reply_markup=main_menu(),
        )
        await query.answer()

    @router.callback_query(F.data.in_({"action:watch", "action:search", "action:rescue"}))
    async def begin(query: CallbackQuery, state: FSMContext) -> None:
        await remember(query)
        intent = query.data.split(":", 1)[1]
        await state.clear()
        await state.update_data(intent=intent)
        await state.set_state(TripFlow.origin)
        if intent == "rescue":
            text = "🆘 از کجا حرکت می‌کنی؟\n\nمن دنبال راهی می‌گردم که واقعاً به مقصد برسونتت."
        else:
            text = "📍 از کجا می‌خوای حرکت کنی؟\nنام شهر رو بنویس؛ مثلاً: بندرعباس"
        await query.message.edit_text(text)
        await query.answer()

    @router.message(TripFlow.origin)
    async def origin(message: Message, state: FSMContext) -> None:
        await remember(message)
        value = (message.text or "").strip()
        if len(value) < 2:
            await message.answer("نام مبدأ رو کامل‌تر بنویس.")
            return
        await state.update_data(origin=value)
        await state.set_state(TripFlow.destination)
        await message.answer("📍 مقصدت کجاست؟")

    @router.message(TripFlow.destination)
    async def destination(message: Message, state: FSMContext) -> None:
        value = (message.text or "").strip()
        data = await state.get_data()
        if len(value) < 2 or value.casefold() == str(data.get("origin", "")).casefold():
            await message.answer("مقصد باید با مبدأ متفاوت باشه. دوباره بنویس.")
            return
        await state.update_data(destination=value)
        intent = data.get("intent")
        if intent == "rescue":
            await state.set_state(TripFlow.deadline)
            await message.answer(
                "⏰ حداکثر تا چه زمانی باید برسی؟\n"
                "مثال: <code>1405/08/20 22:00</code>"
            )
            return
        await state.set_state(TripFlow.travel_date)
        await message.answer(
            "📅 برای چه تاریخی؟\n"
            "شمسی یا میلادی می‌تونی بنویسی؛ مثلاً <code>1405/08/20</code> یا <code>2026/11/11</code>."
        )

    @router.message(TripFlow.deadline)
    async def rescue_deadline(message: Message, state: FSMContext) -> None:
        raw = (message.text or "").strip()
        try:
            date_part, time_part = raw.split(maxsplit=1)
            deadline_date = parse_user_date(date_part)
            hour, minute = map(int, time_part.split(":"))
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                raise ValueError
        except Exception:
            await message.answer("فرمت رو مثل <code>1405/08/20 22:00</code> بفرست.")
            return
        if deadline_date < date.today():
            await message.answer("این تاریخ گذشته. یک زمان آینده وارد کن.")
            return
        await state.update_data(
            travel_date=deadline_date.isoformat(),
            rescue_deadline=f"{deadline_date.isoformat()} {hour:02d}:{minute:02d}",
            flexibility_days=1,
            allow_alternatives=True,
        )
        await state.set_state(TripFlow.budget)
        await message.answer("💰 سقف بودجه‌ات چند تومنه؟ فقط عدد بفرست؛ اگر محدودیت نداری <code>0</code> بفرست.")

    @router.message(TripFlow.budget)
    async def rescue_budget(message: Message, state: FSMContext) -> None:
        raw = (message.text or "").replace(",", "").strip()
        if not raw.isdigit():
            await message.answer("فقط عدد بفرست؛ مثلاً <code>2000000</code>.")
            return
        toman = int(raw)
        await state.update_data(max_price_irr=(toman * 10 if toman else None))
        await state.set_state(TripFlow.modes)
        await message.answer("با چی بگردم؟", reply_markup=mode_keyboard())

    @router.message(TripFlow.travel_date)
    async def travel_date(message: Message, state: FSMContext) -> None:
        try:
            parsed = parse_user_date(message.text or "")
        except Exception:
            await message.answer("تاریخ رو مثل <code>1405/08/20</code> بفرست.")
            return
        if parsed < date.today():
            await message.answer("این تاریخ گذشته. یک تاریخ آینده بفرست.")
            return
        await state.update_data(travel_date=parsed.isoformat())
        await state.set_state(TripFlow.flexibility)
        await message.answer("اگه یک روز قبل یا بعد بلیت خوب پیدا شد خبرت کنم؟", reply_markup=flexibility_keyboard())

    @router.callback_query(TripFlow.flexibility, F.data.startswith("flex:"))
    async def flexibility(query: CallbackQuery, state: FSMContext) -> None:
        days = int(query.data.split(":")[1])
        await state.update_data(flexibility_days=days)
        await state.set_state(TripFlow.modes)
        await query.message.edit_text("ترجیح میدی با چی بری؟", reply_markup=mode_keyboard())
        await query.answer()

    @router.callback_query(TripFlow.modes, F.data.startswith("mode:"))
    async def modes(query: CallbackQuery, state: FSMContext) -> None:
        selected = query.data.split(":")[1]
        mode_values = ["train", "bus"] if selected == "both" else [selected]
        await state.update_data(modes=mode_values)
        data = await state.get_data()
        if data.get("intent") == "rescue":
            await state.update_data(allow_alternatives=True)
            await _finish_flow(query, state, db, orchestrator, route_engine, settings)
            return
        await state.set_state(TripFlow.alternatives)
        await query.message.edit_text(
            "اگر مسیر مستقیم نبود، راه‌های یک‌توقفه رو هم بررسی کنم؟",
            reply_markup=alternatives_keyboard(),
        )
        await query.answer()

    @router.callback_query(TripFlow.alternatives, F.data.startswith("alt:"))
    async def alternatives(query: CallbackQuery, state: FSMContext) -> None:
        await state.update_data(allow_alternatives=query.data.endswith("1"))
        await _finish_flow(query, state, db, orchestrator, route_engine, settings)

    @router.callback_query(F.data == "watches:list")
    async def list_watches(query: CallbackQuery) -> None:
        await remember(query)
        watches = await db.list_user_watches(query.from_user.id)
        if not watches:
            await query.message.edit_text("هنوز سفری زیر نظر نداری.", reply_markup=main_menu())
            await query.answer()
            return
        await query.message.edit_text("👀 <b>سفرهای تحت نظر تو</b>", reply_markup=watches_keyboard(watches))
        await query.answer()

    @router.callback_query(F.data.startswith("watch:view:"))
    async def view_watch(query: CallbackQuery) -> None:
        watch_id = int(query.data.rsplit(":", 1)[1])
        watch = await db.get_watch(watch_id)
        if not watch or int(watch["user_id"]) != query.from_user.id:
            await query.answer("Watch پیدا نشد.", show_alert=True)
            return
        modes_text = " + ".join(
            "قطار" if m == "train" else "اتوبوس" if m == "bus" else m
            for m in watch["modes"]
        )
        state_labels = {
            "available": "🟢 بلیت دیده شده؛ پایش ادامه دارد",
            "unavailable": "🟠 فعلاً بلیت مناسبی نیست؛ دارم می‌پام",
            "not_released": "🗓 فروش هنوز شروع نشده؛ منتظر باز شدنم",
        }
        if watch["status"] == "expired":
            state_text = "⌛ تاریخ سفر گذشته و Watch پایان یافته"
        elif watch["status"] == "cancelled":
            state_text = "⛔ پایش متوقف شده"
        else:
            state_text = state_labels.get(
                watch.get("last_state"),
                "👀 پایش فعاله؛ در حال بررسی",
            )
            if watch.get("last_provider_errors") and not watch.get("last_state"):
                state_text = "⚠️ آخرین بررسی نامطمئن بود؛ دوباره تلاش می‌کنم"

        flex = int(watch.get("flexibility_days") or 0)
        date_text = format_jalali(date.fromisoformat(watch["travel_date"]))
        if flex:
            date_text += f"  (±{flex} روز)"

        details = [
            f"👀 <b>Watch #{watch['id']}</b>",
            "",
            f"📍 {escape(watch['origin'])} → {escape(watch['destination'])}",
            f"📅 {date_text}",
            f"🚆🚌 {modes_text}",
            f"🔔 {state_text}",
            f"🔎 تعداد بررسی‌ها: <b>{int(watch.get('check_count') or 0)}</b>",
        ]
        if watch.get("last_checked_at"):
            details.append(f"🕒 آخرین بررسی: {_format_watch_time(watch['last_checked_at'])}")
        if watch.get("next_check_at") and watch["status"] == "active":
            details.append(f"⏭ بررسی بعدی: {_format_watch_time(watch['next_check_at'])}")
        if watch.get("last_available_at"):
            details.append(f"🎫 آخرین مشاهده بلیت: {_format_watch_time(watch['last_available_at'])}")
        text = "\n".join(details)
        await query.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="🔄 ادامه پایش", callback_data=f"watch:resume:{watch_id}")],
                    [InlineKeyboardButton(text="⛔ توقف", callback_data=f"watch:cancel:{watch_id}")],
                    [InlineKeyboardButton(text="⬅️ برگشت", callback_data="watches:list")],
                ]
            ),
        )
        await query.answer()

    @router.callback_query(F.data.startswith("watch:cancel:"))
    async def cancel_watch(query: CallbackQuery) -> None:
        watch_id = int(query.data.rsplit(":", 1)[1])
        watch = await db.get_watch(watch_id)
        if not watch or int(watch["user_id"]) != query.from_user.id:
            await query.answer("اجازه این کار رو نداری.", show_alert=True)
            return
        await db.update_watch_status(watch_id, "cancelled")
        await query.answer("Watch متوقف شد.", show_alert=True)
        watches = await db.list_user_watches(query.from_user.id)
        if watches:
            await query.message.edit_text("👀 <b>سفرهای تحت نظر تو</b>", reply_markup=watches_keyboard(watches))
        else:
            await query.message.edit_text("هنوز سفری زیر نظر نداری.", reply_markup=main_menu())

    @router.callback_query(F.data.startswith("watch:resume:"))
    async def resume_watch(query: CallbackQuery) -> None:
        watch_id = int(query.data.rsplit(":", 1)[1])
        watch = await db.get_watch(watch_id)
        if not watch or int(watch["user_id"]) != query.from_user.id:
            await query.answer("اجازه این کار رو نداری.", show_alert=True)
            return
        await db.update_watch_status(watch_id, "active")
        await query.answer("پایش دوباره فعال شد.", show_alert=True)

    @router.message(StateFilter(None))
    async def fallback(message: Message) -> None:
        await remember(message)
        await message.answer("از منوی زیر شروع کن 👇", reply_markup=main_menu())

    return router


async def _finish_flow(
    query: CallbackQuery,
    state: FSMContext,
    db: Database,
    orchestrator: SearchOrchestrator,
    route_engine: AlternativeRouteEngine,
    settings: Settings,
) -> None:
    data = await state.get_data()
    await state.clear()
    modes = tuple(TravelMode(value) for value in data["modes"])
    request = SearchRequest(
        origin=data["origin"],
        destination=data["destination"],
        travel_date=date.fromisoformat(data["travel_date"]),
        modes=modes,
        passengers=1,
    )
    intent = data.get("intent", "watch")
    watch_id: int | None = None
    if intent in {"watch", "rescue"}:
        watch_id = await db.create_watch(
            user_id=query.from_user.id,
            origin=request.origin,
            destination=request.destination,
            travel_date=request.travel_date.isoformat(),
            flexibility_days=int(data.get("flexibility_days", 0)),
            modes=[mode.value for mode in modes],
            passengers=1,
            max_price_irr=data.get("max_price_irr"),
            allow_alternatives=bool(data.get("allow_alternatives", True)),
        )

    await query.message.edit_text("🔎 دارم همین الآن چند منبع رو بررسی می‌کنم…")

    flex = int(data.get("flexibility_days", 0))
    search_dates = [
        request.travel_date + timedelta(days=delta)
        for delta in range(-flex, flex + 1)
        if request.travel_date + timedelta(days=delta) >= date.today()
    ]
    snapshots = await asyncio.gather(
        *(
            orchestrator.search(
                SearchRequest(
                    origin=request.origin,
                    destination=request.destination,
                    travel_date=travel_date,
                    modes=modes,
                    passengers=request.passengers,
                )
            )
            for travel_date in search_dates
        )
    )
    snapshot = merge_snapshots(list(snapshots))

    if watch_id:
        watch = await db.get_watch(watch_id)
        if watch:
            signature = result_signature(snapshot)
            current_best = best_price(snapshot)
            interval = next_interval_seconds(watch, snapshot.state, settings)
            now = datetime.now(timezone.utc)
            await db.record_watch_observation(
                watch_id,
                state=snapshot.state.value,
                result_hash=signature,
                best_price_irr=current_best,
                provider_errors=snapshot.errors,
                next_check_at=(now + timedelta(seconds=interval)).isoformat(),
            )
            # The current result is already visible in this chat interaction,
            # so store it as the alert baseline and avoid a duplicate alert
            # on the next background cycle.
            if signature and snapshot.journeys:
                await db.mark_watch_alerted(watch_id, signature, current_best)

    text, keyboard = render_snapshot(snapshot, title="نتیجه اولیه")

    if snapshot.journeys:
        rows = list(keyboard.inline_keyboard) if keyboard else []
        if watch_id:
            text += (
                "\n\n👀 <b>Watch روشن موند.</b> "
                "اگر این بلیت ناپدید بشه و دوباره برگرده، قیمت بهتر بشه، "
                "یا گزینه تازه‌ای اضافه بشه دوباره خبرت می‌کنم."
            )
            rows.append(
                [InlineKeyboardButton(text="👀 وضعیت Watch", callback_data=f"watch:view:{watch_id}")]
            )
        rows.append([InlineKeyboardButton(text="🏠 منوی اصلی", callback_data="menu:main")])
        await query.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        )
        await query.answer()
        return

    alt_text = ""
    if data.get("allow_alternatives", True):
        alternatives = await route_engine.search(request)
        if alternatives:
            alt_text = "\n\n" + render_alternatives(alternatives)
            if watch_id:
                await db.claim_alternative_notification(watch_id)

    if watch_id:
        state_line = (
            "\n\n🗓 هنوز فروش باز نشده؛ من شروع فروش رو هم زیر نظر می‌گیرم."
            if snapshot.state.value == "not_released"
            else (
                "\n\n🔔 Watch فعال شد. فعلاً بلیتی ندیدم؛ "
                "ممکنه فروش هنوز باز نشده باشه یا ظرفیت موجود نباشه. "
                "لازم نیست خودت دوباره چک کنی."
            )
        )
        text += state_line
    else:
        text += "\n\nبرای پایش مداوم از دکمه «بلیت این تاریخ اومد، خبرم کن» استفاده کن."

    rows = [[InlineKeyboardButton(text="🏠 منوی اصلی", callback_data="menu:main")]]
    if watch_id:
        rows.insert(0, [InlineKeyboardButton(text="👀 Watch من", callback_data=f"watch:view:{watch_id}")])
    await query.message.edit_text(text + alt_text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    await query.answer()



def _format_watch_time(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        local = parsed.astimezone(ZoneInfo("Asia/Tehran"))
        return f"{format_jalali(local.date())}، {local.strftime('%H:%M')}"
    except (TypeError, ValueError):
        return "نامشخص"
