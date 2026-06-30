from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from datetime import datetime, timedelta
from database import get_today_shifts, get_all_previous_shifts, get_month_shifts, is_admin
from keyboards.main_menu import get_main_menu
from utils.subscription_check import check_subscription
import aiosqlite
from database import DB_NAME
from calendar import monthcalendar

router = Router()

# Русские названия месяцев
MONTHS_RU = [
    "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"
]

# Дни недели на русском
DAYS_RU = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]


class PeriodState(StatesGroup):
    waiting_for_start_date = State()
    waiting_for_end_date = State()


class RangeCalendar:
    """Календарь для выбора диапазона дат (префикс range_)"""

    def __init__(self, prefix: str = "range"):
        self.prefix = prefix

    async def start_calendar(self, year: int = None, month: int = None) -> types.InlineKeyboardMarkup:
        today = datetime.now()
        if year is None:
            year = today.year
        if month is None:
            month = today.month

        markup = types.InlineKeyboardMarkup(inline_keyboard=[])

        # Заголовок с месяцем и годом
        markup.inline_keyboard.append([
            types.InlineKeyboardButton(
                text=f"{MONTHS_RU[month - 1]} {year}",
                callback_data=f"{self.prefix}_ignore"
            )
        ])

        # Кнопки навигации
        markup.inline_keyboard.append([
            types.InlineKeyboardButton(text="◀️", callback_data=f"{self.prefix}_cal_nav:prev:{year}:{month}"),
            types.InlineKeyboardButton(text="▶️", callback_data=f"{self.prefix}_cal_nav:next:{year}:{month}")
        ])

        # Дни недели
        markup.inline_keyboard.append([
            types.InlineKeyboardButton(text=day, callback_data=f"{self.prefix}_ignore") for day in DAYS_RU
        ])

        # Дни месяца
        weeks = monthcalendar(year, month)

        for week in weeks:
            row = []
            for day in week:
                if day == 0:
                    row.append(types.InlineKeyboardButton(text=" ", callback_data=f"{self.prefix}_ignore"))
                else:
                    date_str = f"{year}-{month:02d}-{day:02d}"
                    date_obj = datetime(year, month, day)

                    if date_obj.date() > today.date():
                        row.append(types.InlineKeyboardButton(text=f"❌{day}", callback_data=f"{self.prefix}_ignore"))
                    else:
                        row.append(types.InlineKeyboardButton(
                            text=str(day),
                            callback_data=f"{self.prefix}_day:{date_str}"
                        ))
            markup.inline_keyboard.append(row)

        # Кнопка "Назад"
        markup.inline_keyboard.append([
            types.InlineKeyboardButton(text="🔙 Отмена", callback_data=f"{self.prefix}_cancel")
        ])

        return markup


class RuStatCalendar:
    """Календарь на русском языке для статистики (префикс stat_)"""

    async def start_calendar(self, year: int = None, month: int = None) -> types.InlineKeyboardMarkup:
        today = datetime.now()
        if year is None:
            year = today.year
        if month is None:
            month = today.month

        markup = types.InlineKeyboardMarkup(inline_keyboard=[])

        markup.inline_keyboard.append([
            types.InlineKeyboardButton(
                text=f"{MONTHS_RU[month - 1]} {year}",
                callback_data="stat_ignore"
            )
        ])

        markup.inline_keyboard.append([
            types.InlineKeyboardButton(text="◀️", callback_data=f"stat_cal_nav:prev:{year}:{month}"),
            types.InlineKeyboardButton(text="▶️", callback_data=f"stat_cal_nav:next:{year}:{month}")
        ])

        markup.inline_keyboard.append([
            types.InlineKeyboardButton(text=day, callback_data="stat_ignore") for day in DAYS_RU
        ])

        weeks = monthcalendar(year, month)

        for week in weeks:
            row = []
            for day in week:
                if day == 0:
                    row.append(types.InlineKeyboardButton(text=" ", callback_data="stat_ignore"))
                else:
                    date_str = f"{year}-{month:02d}-{day:02d}"
                    row.append(types.InlineKeyboardButton(
                        text=str(day),
                        callback_data=f"stat_day:{date_str}"
                    ))
            markup.inline_keyboard.append(row)

        markup.inline_keyboard.append([
            types.InlineKeyboardButton(text="🔙 Назад к статистике", callback_data="stat_back_to_menu")
        ])

        return markup


async def get_shifts_for_range(user_id: int, start_date: str, end_date: str):
    """Получает смены за диапазон дат"""
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute(
            "SELECT * FROM shifts WHERE user_id=? AND date >= ? AND date <= ? ORDER BY date",
            (user_id, start_date, end_date)
        )
        return await cursor.fetchall()


async def get_shifts_for_date(user_id: int, date_str: str):
    """Получает смены за конкретную дату"""
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT * FROM shifts WHERE user_id=? AND date=?", (user_id, date_str))
        return await cursor.fetchall()


def format_statistics(shifts, title=None):
    """Форматирует детальную статистику по сменам"""
    if not shifts:
        text = "Нет данных за выбранный период."
        if title:
            text = f"{title}\n\n{text}"
        return text

    total_hours = 0
    total_hourly_pay = 0
    total_revenue = 0
    total_revenue_share = 0
    total_tips = 0
    total_salary = 0
    shift_count = len(shifts)

    shift_details = []

    for idx, shift in enumerate(shifts, 1):
        hours = shift[3] or 0
        rate = shift[4] or 0
        revenue = shift[5] or 0
        percent = shift[6] or 0
        tips = shift[7] or 0
        salary = shift[8] or 0
        date = shift[2]

        hourly_pay = hours * rate
        revenue_share = revenue * percent / 100
        salary_without_tips = hourly_pay + revenue_share

        total_hours += hours
        total_hourly_pay += hourly_pay
        total_revenue += revenue
        total_revenue_share += revenue_share
        total_tips += tips
        total_salary += salary_without_tips

        if shift_count > 1:
            date_obj = datetime.strptime(date, "%Y-%m-%d")
            date_formatted = date_obj.strftime("%d.%m.%Y")
            shift_details.append(
                f"📅 {date_formatted} | Смена {idx}:\n"
                f"⏱ {hours:.1f} ч × {rate:.0f} ₽/ч = {hourly_pay:.2f} ₽\n"
                f"📈 Выручка: {revenue:.2f} ₽ × {percent:.0f}% = {revenue_share:.2f} ₽\n"
                f"💰 ЗП: {salary_without_tips:.2f} ₽ | 💝 Чаевые: {tips:.2f} ₽\n"
            )

    text = ""
    if title:
        text += f"{title}\n\n"

    if shift_details:
        text += "\n".join(shift_details) + "\n\n"

    text += (
        f"📊 <b>Всего смен:</b> {shift_count}\n"
        f"⏱️ <b>Всего часов:</b> {total_hours:.1f} ч\n"
        f"💵 <b>Зарплата по часам:</b> {total_hourly_pay:.2f} ₽\n"
        f"📈 <b>Общая выручка:</b> {total_revenue:.2f} ₽\n"
        f"📊 <b>Процент с выручки:</b> {total_revenue_share:.2f} ₽\n\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"💰 <b>ИТОГО ЗП:</b> {total_salary:.2f} ₽\n"
        f"💝 <b>ИТОГО ЧАЕВЫЕ:</b> {total_tips:.2f} ₽\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"💵 <b>ВСЕГО:</b> {total_salary + total_tips:.2f} ₽"
    )

    return text


@router.message(lambda m: m.text == "📊 Моя статистика")
async def statistics_main(message: types.Message):
    if not await check_subscription(message.from_user.id):
        await message.answer("⚠️ У вас нет активной подписки. Перейдите в раздел «💳 Моя подписка» для оплаты.")
        return

    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="📌 За сегодня", callback_data="stat_today")],
        [types.InlineKeyboardButton(text="📅 За месяц", callback_data="stat_month")],
        [types.InlineKeyboardButton(text="📊 За всё время", callback_data="stat_all")],
        [types.InlineKeyboardButton(text="🗓 Выбрать день", callback_data="stat_calendar")],
        [types.InlineKeyboardButton(text="📆 Выбрать период", callback_data="stat_period")],
        [types.InlineKeyboardButton(text="🔙 Назад", callback_data="stat_back")]
    ])
    await message.answer("Выберите период:", reply_markup=keyboard)


# ==================== Обработчики периода ====================

@router.callback_query(F.data == "stat_period")
async def stat_period_start(callback: types.CallbackQuery, state: FSMContext):
    """Начало выбора периода - показываем календарь для выбора начальной даты"""
    if not await check_subscription(callback.from_user.id):
        await callback.answer("Нет подписки", show_alert=True)
        return

    calendar = RangeCalendar(prefix="range_start")
    await callback.message.edit_text(
        "📅 Выберите <b>НАЧАЛЬНУЮ</b> дату периода:",
        reply_markup=await calendar.start_calendar(),
        parse_mode="HTML"
    )
    await state.set_state(PeriodState.waiting_for_start_date)
    await callback.answer()


@router.callback_query(PeriodState.waiting_for_start_date, F.data.startswith("range_start_cal_nav:"))
async def range_start_nav(callback: types.CallbackQuery):
    """Навигация по календарю начальной даты"""
    if not await check_subscription(callback.from_user.id):
        await callback.answer("Нет подписки", show_alert=True)
        return

    parts = callback.data.split(":")
    direction = parts[1]
    year = int(parts[2])
    month = int(parts[3])

    if direction == "prev":
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    else:
        month += 1
        if month == 13:
            month = 1
            year += 1

    calendar = RangeCalendar(prefix="range_start")
    await callback.message.edit_reply_markup(
        reply_markup=await calendar.start_calendar(year, month)
    )
    await callback.answer()


@router.callback_query(PeriodState.waiting_for_start_date, F.data.startswith("range_start_day:"))
async def range_start_selected(callback: types.CallbackQuery, state: FSMContext):
    """Выбрана начальная дата - показываем календарь для конечной даты"""
    if not await check_subscription(callback.from_user.id):
        await callback.answer("Нет подписки", show_alert=True)
        return

    date_str = callback.data.split(":")[1]
    date_obj = datetime.strptime(date_str, "%Y-%m-%d")
    date_formatted = date_obj.strftime("%d.%m.%Y")

    await state.update_data(range_start=date_str, range_start_formatted=date_formatted)

    calendar = RangeCalendar(prefix="range_end")
    await callback.message.edit_text(
        f"✅ Начальная дата: <b>{date_formatted}</b>\n\n"
        f"📅 Теперь выберите <b>КОНЕЧНУЮ</b> дату периода:",
        reply_markup=await calendar.start_calendar(),
        parse_mode="HTML"
    )
    await state.set_state(PeriodState.waiting_for_end_date)
    await callback.answer()


@router.callback_query(PeriodState.waiting_for_start_date, F.data.startswith("range_start_ignore"))
async def range_start_ignore(callback: types.CallbackQuery):
    await callback.answer()


@router.callback_query(PeriodState.waiting_for_start_date, F.data == "range_start_cancel")
async def range_start_cancel(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("Выбор периода отменён.", reply_markup=get_back_to_stat_kb())
    await callback.answer()


# Конечная дата
@router.callback_query(PeriodState.waiting_for_end_date, F.data.startswith("range_end_cal_nav:"))
async def range_end_nav(callback: types.CallbackQuery):
    """Навигация по календарю конечной даты"""
    if not await check_subscription(callback.from_user.id):
        await callback.answer("Нет подписки", show_alert=True)
        return

    parts = callback.data.split(":")
    direction = parts[1]
    year = int(parts[2])
    month = int(parts[3])

    if direction == "prev":
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    else:
        month += 1
        if month == 13:
            month = 1
            year += 1

    calendar = RangeCalendar(prefix="range_end")
    await callback.message.edit_reply_markup(
        reply_markup=await calendar.start_calendar(year, month)
    )
    await callback.answer()


@router.callback_query(PeriodState.waiting_for_end_date, F.data.startswith("range_end_day:"))
async def range_end_selected(callback: types.CallbackQuery, state: FSMContext):
    """Выбрана конечная дата - показываем статистику за период"""
    if not await check_subscription(callback.from_user.id):
        await callback.answer("Нет подписки", show_alert=True)
        return

    end_date_str = callback.data.split(":")[1]
    data = await state.get_data()
    start_date_str = data['range_start']
    start_formatted = data['range_start_formatted']

    end_date_obj = datetime.strptime(end_date_str, "%Y-%m-%d")
    end_formatted = end_date_obj.strftime("%d.%m.%Y")

    # Проверяем что конечная дата не раньше начальной
    start_date_obj = datetime.strptime(start_date_str, "%Y-%m-%d")
    if end_date_obj < start_date_obj:
        await callback.answer("Конечная дата не может быть раньше начальной!", show_alert=True)
        return

    user_id = callback.from_user.id
    shifts = await get_shifts_for_range(user_id, start_date_str, end_date_str)
    title = f"📆 <b>Статистика за период</b>\n{start_formatted} — {end_formatted}"
    text = format_statistics(shifts, title)

    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="📆 Выбрать другой период", callback_data="stat_period")],
        [types.InlineKeyboardButton(text="🔙 Назад к статистике", callback_data="stat_back_to_menu")]
    ])

    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await state.clear()
    await callback.answer()


@router.callback_query(PeriodState.waiting_for_end_date, F.data.startswith("range_end_ignore"))
async def range_end_ignore(callback: types.CallbackQuery):
    await callback.answer()


@router.callback_query(PeriodState.waiting_for_end_date, F.data == "range_end_cancel")
async def range_end_cancel(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("Выбор периода отменён.", reply_markup=get_back_to_stat_kb())
    await callback.answer()


# ==================== Остальные обработчики ====================

@router.callback_query(F.data == "stat_today")
async def stat_today(callback: types.CallbackQuery):
    if not await check_subscription(callback.from_user.id):
        await callback.answer("Нет подписки", show_alert=True)
        return

    user_id = callback.from_user.id
    today = datetime.now().strftime("%Y-%m-%d")
    shifts = await get_shifts_for_date(user_id, today)
    title = f"📌 <b>Статистика за сегодня</b> ({datetime.now().strftime('%d.%m.%Y')})"
    text = format_statistics(shifts, title)
    await callback.message.edit_text(text, reply_markup=get_back_keyboard(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "stat_month")
async def stat_month(callback: types.CallbackQuery):
    if not await check_subscription(callback.from_user.id):
        await callback.answer("Нет подписки", show_alert=True)
        return

    user_id = callback.from_user.id
    now = datetime.now()
    shifts = await get_month_shifts(user_id, now.year, now.month)
    title = f"📅 <b>Статистика за {MONTHS_RU[now.month - 1].lower()} {now.year}</b>"
    text = format_statistics(shifts, title)
    await callback.message.edit_text(text, reply_markup=get_back_keyboard(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "stat_all")
async def stat_all(callback: types.CallbackQuery):
    if not await check_subscription(callback.from_user.id):
        await callback.answer("Нет подписки", show_alert=True)
        return

    user_id = callback.from_user.id
    prev_shifts = await get_all_previous_shifts(user_id)
    today_shifts = await get_today_shifts(user_id)
    all_shifts = list(prev_shifts) + list(today_shifts)
    title = "📊 <b>Статистика за всё время</b>"
    text = format_statistics(all_shifts, title)
    await callback.message.edit_text(text, reply_markup=get_back_keyboard(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "stat_calendar")
async def stat_calendar(callback: types.CallbackQuery):
    """Открывает русский календарь для выбора дня"""
    if not await check_subscription(callback.from_user.id):
        await callback.answer("Нет подписки", show_alert=True)
        return

    calendar = RuStatCalendar()
    await callback.message.edit_text(
        "📅 Выберите дату для просмотра статистики:",
        reply_markup=await calendar.start_calendar()
    )
    await callback.answer()


@router.callback_query(F.data.startswith("stat_cal_nav:"))
async def stat_cal_nav(callback: types.CallbackQuery):
    """Навигация по календарю статистики"""
    if not await check_subscription(callback.from_user.id):
        await callback.answer("Нет подписки", show_alert=True)
        return

    parts = callback.data.split(":")
    direction = parts[1]
    year = int(parts[2])
    month = int(parts[3])

    if direction == "prev":
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    else:
        month += 1
        if month == 13:
            month = 1
            year += 1

    calendar = RuStatCalendar()
    await callback.message.edit_reply_markup(
        reply_markup=await calendar.start_calendar(year, month)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("stat_day:"))
async def stat_day_selected(callback: types.CallbackQuery):
    """Обрабатывает выбор даты в календаре статистики"""
    if not await check_subscription(callback.from_user.id):
        await callback.answer("Нет подписки", show_alert=True)
        return

    date_str = callback.data.split(":")[1]
    date_obj = datetime.strptime(date_str, "%Y-%m-%d")
    date_formatted = date_obj.strftime("%d.%m.%Y")

    user_id = callback.from_user.id
    shifts = await get_shifts_for_date(user_id, date_str)
    title = f"🗓 <b>Статистика за {date_formatted}</b>"
    text = format_statistics(shifts, title)

    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="📅 Выбрать другой день", callback_data="stat_calendar")],
        [types.InlineKeyboardButton(text="📆 Выбрать период", callback_data="stat_period")],
        [types.InlineKeyboardButton(text="🔙 Назад к статистике", callback_data="stat_back_to_menu")]
    ])

    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "stat_ignore")
async def stat_ignore(callback: types.CallbackQuery):
    """Игнорируем нажатия на неактивные кнопки"""
    await callback.answer()


@router.callback_query(F.data == "stat_back")
async def stat_back(callback: types.CallbackQuery):
    await callback.message.delete()
    await callback.bot.send_message(
        callback.from_user.id,
        "Главное меню",
        reply_markup=get_main_menu(await is_admin(callback.from_user.id))
    )
    await callback.answer()


@router.callback_query(F.data == "stat_back_to_menu")
async def stat_back_to_menu(callback: types.CallbackQuery):
    if not await check_subscription(callback.from_user.id):
        await callback.answer("Нет подписки", show_alert=True)
        return

    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="📌 За сегодня", callback_data="stat_today")],
        [types.InlineKeyboardButton(text="📅 За месяц", callback_data="stat_month")],
        [types.InlineKeyboardButton(text="📊 За всё время", callback_data="stat_all")],
        [types.InlineKeyboardButton(text="🗓 Выбрать день", callback_data="stat_calendar")],
        [types.InlineKeyboardButton(text="📆 Выбрать период", callback_data="stat_period")],
        [types.InlineKeyboardButton(text="🔙 Назад", callback_data="stat_back")]
    ])
    await callback.message.edit_text("Выберите период:", reply_markup=keyboard)
    await callback.answer()


def get_back_keyboard():
    return types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="📅 Выбрать другой день", callback_data="stat_calendar")],
        [types.InlineKeyboardButton(text="📆 Выбрать период", callback_data="stat_period")],
        [types.InlineKeyboardButton(text="🔙 Назад к статистике", callback_data="stat_back_to_menu")]
    ])


def get_back_to_stat_kb():
    return types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="🔙 Назад к статистике", callback_data="stat_back_to_menu")]
    ])