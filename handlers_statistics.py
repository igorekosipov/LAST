from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from datetime import datetime
from database import get_today_shifts, get_all_previous_shifts, get_month_shifts, is_admin
from keyboards_main_menu import get_main_menu
from utils_subscription_check import check_subscription
import aiosqlite
from database import DB_NAME
from calendar import monthcalendar

stat_router = Router()

MONTHS_RU = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"]
DAYS_RU = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]

class PeriodState(StatesGroup):
    waiting_for_start = State()
    waiting_for_end = State()

async def build_calendar(year: int, month: int, prefix: str) -> types.InlineKeyboardMarkup:
    markup = types.InlineKeyboardMarkup(inline_keyboard=[])
    markup.inline_keyboard.append([types.InlineKeyboardButton(text=f"{MONTHS_RU[month-1]} {year}", callback_data=f"{prefix}_ignore")])
    markup.inline_keyboard.append([
        types.InlineKeyboardButton(text="◀️", callback_data=f"{prefix}_nav:prev:{year}:{month}"),
        types.InlineKeyboardButton(text="▶️", callback_data=f"{prefix}_nav:next:{year}:{month}")
    ])
    markup.inline_keyboard.append([types.InlineKeyboardButton(text=day, callback_data=f"{prefix}_ignore") for day in DAYS_RU])
    weeks = monthcalendar(year, month)
    today = datetime.now()
    for week in weeks:
        row = []
        for day in week:
            if day == 0:
                row.append(types.InlineKeyboardButton(text=" ", callback_data=f"{prefix}_ignore"))
            else:
                date_str = f"{year}-{month:02d}-{day:02d}"
                if datetime(year, month, day).date() > today.date():
                    row.append(types.InlineKeyboardButton(text=f"❌{day}", callback_data=f"{prefix}_ignore"))
                else:
                    row.append(types.InlineKeyboardButton(text=str(day), callback_data=f"{prefix}_day:{date_str}"))
        markup.inline_keyboard.append(row)
    markup.inline_keyboard.append([types.InlineKeyboardButton(text="🔙 Отмена", callback_data=f"{prefix}_cancel")])
    return markup

async def get_shifts_for_range(user_id: int, start_date: str, end_date: str):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT * FROM shifts WHERE user_id=? AND date >= ? AND date <= ? ORDER BY date", (user_id, start_date, end_date))
        return await cursor.fetchall()

async def get_shifts_for_date(user_id: int, date_str: str):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT * FROM shifts WHERE user_id=? AND date=?", (user_id, date_str))
        return await cursor.fetchall()

def format_statistics(shifts, title=None):
    if not shifts:
        return f"{title}\n\nНет данных." if title else "Нет данных."
    total_hours = 0
    total_hourly_pay = 0
    total_revenue = 0
    total_revenue_share = 0
    total_tips = 0
    total_salary = 0
    for shift in shifts:
        hours, rate, revenue, percent, tips, salary = shift[3] or 0, shift[4] or 0, shift[5] or 0, shift[6] or 0, shift[7] or 0, shift[8] or 0
        hourly_pay = hours * rate
        revenue_share = revenue * percent / 100
        total_hours += hours
        total_hourly_pay += hourly_pay
        total_revenue += revenue
        total_revenue_share += revenue_share
        total_tips += tips
        total_salary += hourly_pay + revenue_share
    text = f"{title}\n\n" if title else ""
    text += (
        f"⏱️ Часы: {total_hours:.1f} ч\n"
        f"💵 По часам: {total_hourly_pay:.2f} ₽\n"
        f"📈 Выручка: {total_revenue:.2f} ₽\n"
        f"📊 % с выручки: {total_revenue_share:.2f} ₽\n\n"
        f"━━━━━━━━━━━━━\n"
        f"💰 ИТОГО ЗП: {total_salary:.2f} ₽\n"
        f"💝 ИТОГО ЧАЕВЫЕ: {total_tips:.2f} ₽\n"
        f"━━━━━━━━━━━━━\n"
        f"💵 ВСЕГО: {total_salary + total_tips:.2f} ₽"
    )
    return text

@stat_router.message(lambda m: m.text == "📊 Моя статистика")
async def statistics_main(message: types.Message):
    if not await check_subscription(message.from_user.id):
        await message.answer("⚠️ У вас нет активной подписки.")
        return
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="📌 За сегодня", callback_data="stat_today")],
        [types.InlineKeyboardButton(text="📅 За месяц", callback_data="stat_month")],
        [types.InlineKeyboardButton(text="📊 За всё время", callback_data="stat_all")],
        [types.InlineKeyboardButton(text="🗓 Выбрать день", callback_data="stat_day")],
        [types.InlineKeyboardButton(text="📆 Выбрать период", callback_data="stat_period")],
        [types.InlineKeyboardButton(text="🔙 Назад", callback_data="stat_back")]
    ])
    await message.answer("Выберите:", reply_markup=keyboard)

@stat_router.callback_query(F.data == "stat_today")
async def stat_today(callback: types.CallbackQuery):
    if not await check_subscription(callback.from_user.id): return await callback.answer("Нет подписки", show_alert=True)
    today = datetime.now().strftime("%Y-%m-%d")
    shifts = await get_shifts_for_date(callback.from_user.id, today)
    text = format_statistics(shifts, f"📌 Сегодня ({datetime.now().strftime('%d.%m.%Y')})")
    await callback.message.edit_text(text, reply_markup=get_back_kb(), parse_mode="HTML")
    await callback.answer()

@stat_router.callback_query(F.data == "stat_month")
async def stat_month(callback: types.CallbackQuery):
    if not await check_subscription(callback.from_user.id): return await callback.answer("Нет подписки", show_alert=True)
    now = datetime.now()
    shifts = await get_month_shifts(callback.from_user.id, now.year, now.month)
    text = format_statistics(shifts, f"📅 {MONTHS_RU[now.month-1]} {now.year}")
    await callback.message.edit_text(text, reply_markup=get_back_kb(), parse_mode="HTML")
    await callback.answer()

@stat_router.callback_query(F.data == "stat_all")
async def stat_all(callback: types.CallbackQuery):
    if not await check_subscription(callback.from_user.id): return await callback.answer("Нет подписки", show_alert=True)
    prev = await get_all_previous_shifts(callback.from_user.id)
    today = await get_today_shifts(callback.from_user.id)
    shifts = list(prev) + list(today)
    text = format_statistics(shifts, "📊 Всё время")
    await callback.message.edit_text(text, reply_markup=get_back_kb(), parse_mode="HTML")
    await callback.answer()

@stat_router.callback_query(F.data == "stat_day")
async def stat_day(callback: types.CallbackQuery):
    if not await check_subscription(callback.from_user.id): return await callback.answer("Нет подписки", show_alert=True)
    now = datetime.now()
    await callback.message.edit_text("📅 Выберите дату:", reply_markup=await build_calendar(now.year, now.month, "stat"))
    await callback.answer()

@stat_router.callback_query(F.data.startswith("stat_nav:"))
async def stat_nav(callback: types.CallbackQuery):
    parts = callback.data.split(":")
    direction, year, month = parts[1], int(parts[2]), int(parts[3])
    if direction == "prev":
        month -= 1
        if month == 0: month = 12; year -= 1
    else:
        month += 1
        if month == 13: month = 1; year += 1
    await callback.message.edit_reply_markup(reply_markup=await build_calendar(year, month, "stat"))
    await callback.answer()

@stat_router.callback_query(F.data.startswith("stat_day:"))
async def stat_day_selected(callback: types.CallbackQuery):
    if not await check_subscription(callback.from_user.id): return await callback.answer("Нет подписки", show_alert=True)
    date_str = callback.data.split(":")[1]
    date_obj = datetime.strptime(date_str, "%Y-%m-%d")
    shifts = await get_shifts_for_date(callback.from_user.id, date_str)
    text = format_statistics(shifts, f"🗓 {date_obj.strftime('%d.%m.%Y')}")
    await callback.message.edit_text(text, reply_markup=get_back_kb(), parse_mode="HTML")
    await callback.answer()

@stat_router.callback_query(F.data == "stat_period")
async def stat_period(callback: types.CallbackQuery, state: FSMContext):
    if not await check_subscription(callback.from_user.id): return await callback.answer("Нет подписки", show_alert=True)
    now = datetime.now()
    await callback.message.edit_text("📅 Выберите НАЧАЛЬНУЮ дату:", reply_markup=await build_calendar(now.year, now.month, "st1"))
    await state.set_state(PeriodState.waiting_for_start)
    await callback.answer()

@stat_router.callback_query(PeriodState.waiting_for_start, F.data.startswith("st1_nav:"))
async def st1_nav(callback: types.CallbackQuery):
    parts = callback.data.split(":")
    direction, year, month = parts[1], int(parts[2]), int(parts[3])
    if direction == "prev":
        month -= 1
        if month == 0: month = 12; year -= 1
    else:
        month += 1
        if month == 13: month = 1; year += 1
    await callback.message.edit_reply_markup(reply_markup=await build_calendar(year, month, "st1"))
    await callback.answer()

@stat_router.callback_query(PeriodState.waiting_for_start, F.data.startswith("st1_day:"))
async def st1_day(callback: types.CallbackQuery, state: FSMContext):
    date_str = callback.data.split(":")[1]
    await state.update_data(start_date=date_str)
    now = datetime.now()
    await callback.message.edit_text(f"✅ Начало: {date_str}\n📅 Выберите КОНЕЧНУЮ дату:", reply_markup=await build_calendar(now.year, now.month, "st2"))
    await state.set_state(PeriodState.waiting_for_end)
    await callback.answer()

@stat_router.callback_query(PeriodState.waiting_for_end, F.data.startswith("st2_nav:"))
async def st2_nav(callback: types.CallbackQuery):
    parts = callback.data.split(":")
    direction, year, month = parts[1], int(parts[2]), int(parts[3])
    if direction == "prev":
        month -= 1
        if month == 0: month = 12; year -= 1
    else:
        month += 1
        if month == 13: month = 1; year += 1
    await callback.message.edit_reply_markup(reply_markup=await build_calendar(year, month, "st2"))
    await callback.answer()

@stat_router.callback_query(PeriodState.waiting_for_end, F.data.startswith("st2_day:"))
async def st2_day(callback: types.CallbackQuery, state: FSMContext):
    end_date = callback.data.split(":")[1]
    data = await state.get_data()
    start_date = data['start_date']
    if end_date < start_date:
        await callback.answer("Конечная дата раньше начальной!", show_alert=True)
        return
    shifts = await get_shifts_for_range(callback.from_user.id, start_date, end_date)
    text = format_statistics(shifts, f"📆 {start_date} — {end_date}")
    await callback.message.edit_text(text, reply_markup=get_back_kb(), parse_mode="HTML")
    await state.clear()
    await callback.answer()

@stat_router.callback_query(F.data.in_({"stat_ignore", "st1_ignore", "st2_ignore"}))
async def ignore_all(callback: types.CallbackQuery): await callback.answer()

@stat_router.callback_query(F.data.in_({"stat_cancel", "st1_cancel", "st2_cancel"}))
async def cancel_all(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("Отменено.", reply_markup=get_back_kb())
    await callback.answer()

@stat_router.callback_query(F.data == "stat_back")
async def stat_back(callback: types.CallbackQuery):
    await callback.message.delete()
    await callback.bot.send_message(callback.from_user.id, "Главное меню", reply_markup=get_main_menu(await is_admin(callback.from_user.id)))
    await callback.answer()

@stat_router.callback_query(F.data == "stat_back_menu")
async def stat_back_menu(callback: types.CallbackQuery):
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="📌 За сегодня", callback_data="stat_today")],
        [types.InlineKeyboardButton(text="📅 За месяц", callback_data="stat_month")],
        [types.InlineKeyboardButton(text="📊 За всё время", callback_data="stat_all")],
        [types.InlineKeyboardButton(text="🗓 Выбрать день", callback_data="stat_day")],
        [types.InlineKeyboardButton(text="📆 Выбрать период", callback_data="stat_period")],
        [types.InlineKeyboardButton(text="🔙 Назад", callback_data="stat_back")]
    ])
    await callback.message.edit_text("Выберите:", reply_markup=keyboard)
    await callback.answer()

def get_back_kb():
    return types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="🔙 Назад", callback_data="stat_back_menu")]
    ])
