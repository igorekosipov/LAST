from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from datetime import datetime, timedelta
from keyboards.main_menu import get_main_menu
from keyboards.calc_menu import get_cancel_keyboard
from database import add_shift, get_today_shifts, get_all_previous_shifts, get_month_shifts, is_admin
from utils.finance import calculate_shift
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


class RuEditCalendar:
    """Календарь на русском языке для редактирования/добавления смен"""

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
                callback_data="edit_ignore"
            )
        ])

        # Кнопки навигации
        markup.inline_keyboard.append([
            types.InlineKeyboardButton(text="◀️", callback_data=f"edit_cal_nav:prev:{year}:{month}"),
            types.InlineKeyboardButton(text="▶️", callback_data=f"edit_cal_nav:next:{year}:{month}")
        ])

        # Дни недели
        markup.inline_keyboard.append([
            types.InlineKeyboardButton(text=day, callback_data="edit_ignore") for day in DAYS_RU
        ])

        # Дни месяца
        weeks = monthcalendar(year, month)

        for week in weeks:
            row = []
            for day in week:
                if day == 0:
                    row.append(types.InlineKeyboardButton(text=" ", callback_data="edit_ignore"))
                else:
                    date_str = f"{year}-{month:02d}-{day:02d}"
                    date_obj = datetime(year, month, day)

                    if date_obj.date() > today.date():
                        # Будущие даты недоступны
                        row.append(types.InlineKeyboardButton(text=f"❌{day}", callback_data="edit_ignore"))
                    else:
                        row.append(types.InlineKeyboardButton(
                            text=str(day),
                            callback_data=f"edit_day:{date_str}"
                        ))
            markup.inline_keyboard.append(row)

        # Кнопка "Назад"
        markup.inline_keyboard.append([
            types.InlineKeyboardButton(text="🔙 Отмена", callback_data="edit_cancel")
        ])

        return markup


class CalcState(StatesGroup):
    waiting_for_hours = State()
    waiting_for_rate = State()
    waiting_for_revenue = State()
    waiting_for_percent = State()
    waiting_for_tips = State()


class EditState(StatesGroup):
    waiting_for_edit_date = State()
    waiting_for_edit_select = State()
    waiting_for_edit_hours = State()
    waiting_for_edit_rate = State()
    waiting_for_edit_revenue = State()
    waiting_for_edit_percent = State()
    waiting_for_edit_tips = State()


@router.message(lambda m: m.text == "🧮 Калькулятор")
async def calc_menu(message: types.Message):
    if not await check_subscription(message.from_user.id):
        await message.answer("⚠️ У вас нет активной подписки. Перейдите в раздел «💳 Моя подписка» для оплаты.")
        return

    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="➕ Новая смена (сегодня)", callback_data="calc_new")],
        [types.InlineKeyboardButton(text="✏️ Добавить/редактировать смену за дату", callback_data="calc_edit")],
        [types.InlineKeyboardButton(text="🔙 Назад", callback_data="calc_back_to_menu")]
    ])
    await message.answer("Выберите действие:", reply_markup=keyboard)


@router.callback_query(F.data == "calc_new")
async def start_new_shift(callback: types.CallbackQuery, state: FSMContext):
    if not await check_subscription(callback.from_user.id):
        await callback.answer("Нет подписки", show_alert=True)
        return

    await callback.message.delete()
    await callback.bot.send_message(
        callback.from_user.id,
        "Введите количество отработанных часов (например, 8.5):",
        reply_markup=get_cancel_keyboard()
    )
    await state.update_data(edit_date=datetime.now().strftime("%Y-%m-%d"), is_new=True)
    await state.set_state(CalcState.waiting_for_hours)
    await callback.answer()


@router.callback_query(F.data == "calc_edit")
async def start_edit_shift(callback: types.CallbackQuery, state: FSMContext):
    if not await check_subscription(callback.from_user.id):
        await callback.answer("Нет подписки", show_alert=True)
        return

    calendar = RuEditCalendar()
    await callback.message.edit_text(
        "📅 Выберите дату для добавления или редактирования смены:",
        reply_markup=await calendar.start_calendar()
    )
    await state.set_state(EditState.waiting_for_edit_date)
    await callback.answer()


# Навигация по календарю редактирования
@router.callback_query(EditState.waiting_for_edit_date, F.data.startswith("edit_cal_nav:"))
async def edit_cal_nav(callback: types.CallbackQuery):
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

    calendar = RuEditCalendar()
    await callback.message.edit_reply_markup(
        reply_markup=await calendar.start_calendar(year, month)
    )
    await callback.answer()


# Выбор даты в календаре редактирования
@router.callback_query(EditState.waiting_for_edit_date, F.data.startswith("edit_day:"))
async def edit_day_selected(callback: types.CallbackQuery, state: FSMContext):
    if not await check_subscription(callback.from_user.id):
        await callback.answer("Нет подписки", show_alert=True)
        return

    date_str = callback.data.split(":")[1]
    date_obj = datetime.strptime(date_str, "%Y-%m-%d")
    date_formatted = date_obj.strftime("%d.%m.%Y")

    # Получаем смены за эту дату
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute(
            "SELECT * FROM shifts WHERE user_id=? AND date=?",
            (callback.from_user.id, date_str)
        )
        shifts = await cursor.fetchall()

    await state.update_data(edit_date=date_str, is_new=False)

    if not shifts:
        # Нет смен за эту дату - предлагаем добавить новую
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="➕ Добавить новую смену", callback_data=f"edit_add_new:{date_str}")],
            [types.InlineKeyboardButton(text="📅 Выбрать другую дату", callback_data="calc_edit")],
            [types.InlineKeyboardButton(text="🔙 Главное меню", callback_data="calc_back_to_menu")]
        ])
        await callback.message.edit_text(
            f"📅 На {date_formatted} смен ещё нет.\n\nХотите добавить новую смену на этот день?",
            reply_markup=keyboard
        )
        await state.set_state(EditState.waiting_for_edit_select)
    elif len(shifts) == 1:
        # Одна смена - показываем данные и предлагаем действия
        shift = shifts[0]
        hourly_pay = shift[3] * shift[4]
        revenue_share = shift[5] * shift[6] / 100
        salary_without_tips = hourly_pay + revenue_share

        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="✏️ Редактировать эту смену", callback_data=f"edit_select:{shift[0]}")],
            [types.InlineKeyboardButton(text="➕ Добавить ещё смену", callback_data=f"edit_add_new:{date_str}")],
            [types.InlineKeyboardButton(text="🗑️ Удалить эту смену", callback_data=f"edit_delete_one:{shift[0]}")],
            [types.InlineKeyboardButton(text="📅 Выбрать другую дату", callback_data="calc_edit")],
            [types.InlineKeyboardButton(text="🔙 Главное меню", callback_data="calc_back_to_menu")]
        ])
        text = (
            f"📅 Смена за {date_formatted}:\n\n"
            f"⏱ Часы: {shift[3]} ч × {shift[4]} ₽/ч = {hourly_pay:.2f} ₽\n"
            f"📈 Выручка: {shift[5]} ₽ × {shift[6]}% = {revenue_share:.2f} ₽\n"
            f"💰 Итого ЗП: {salary_without_tips:.2f} ₽\n"
            f"💝 Чаевые: {shift[7]} ₽\n\n"
            f"Выберите действие:"
        )
        await callback.message.edit_text(text, reply_markup=keyboard)
        await state.set_state(EditState.waiting_for_edit_select)
    else:
        # Несколько смен - предлагаем выбрать
        text = f"📅 Смены за {date_formatted}:\n\n"
        for idx, shift in enumerate(shifts, 1):
            hourly_pay = shift[3] * shift[4]
            revenue_share = shift[5] * shift[6] / 100
            text += (
                f"Смена {idx}:\n"
                f"⏱ {shift[3]} ч × {shift[4]} ₽/ч = {hourly_pay:.2f} ₽ | "
                f"Выручка: {shift[5]} ₽ × {shift[6]}% = {revenue_share:.2f} ₽ | "
                f"💰 ЗП: {shift[8]:.2f} ₽ | "
                f"💝 Чаевые: {shift[7]:.2f} ₽\n\n"
            )

        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text=f"✏️ Редактировать смену {i + 1}",
                                        callback_data=f"edit_select:{shift[0]}")]
            for i, shift in enumerate(shifts)
        ])
        keyboard.inline_keyboard.append([
            types.InlineKeyboardButton(text="➕ Добавить ещё смену", callback_data=f"edit_add_new:{date_str}")
        ])
        keyboard.inline_keyboard.append([
            types.InlineKeyboardButton(text="🗑️ Удалить все смены за этот день",
                                       callback_data=f"edit_delete_all:{date_str}")
        ])
        keyboard.inline_keyboard.append([
            types.InlineKeyboardButton(text="📅 Выбрать другую дату", callback_data="calc_edit"),
            types.InlineKeyboardButton(text="🔙 Главное меню", callback_data="calc_back_to_menu")
        ])

        await callback.message.edit_text(text, reply_markup=keyboard)
        await state.set_state(EditState.waiting_for_edit_select)

    await callback.answer()


# Добавление новой смены на выбранную дату
@router.callback_query(EditState.waiting_for_edit_select, F.data.startswith("edit_add_new:"))
async def edit_add_new_shift(callback: types.CallbackQuery, state: FSMContext):
    if not await check_subscription(callback.from_user.id):
        await callback.answer("Нет подписки", show_alert=True)
        return

    date_str = callback.data.split(":")[1]
    date_obj = datetime.strptime(date_str, "%Y-%m-%d")
    date_formatted = date_obj.strftime("%d.%m.%Y")

    await state.update_data(edit_date=date_str, is_new=True)

    await callback.message.delete()
    await callback.bot.send_message(
        callback.from_user.id,
        f"➕ Добавление новой смены на {date_formatted}\n\n"
        f"Введите количество отработанных часов (например, 8.5):",
        reply_markup=get_cancel_keyboard()
    )
    await state.set_state(EditState.waiting_for_edit_hours)
    await callback.answer()


# Удаление одной смены
@router.callback_query(EditState.waiting_for_edit_select, F.data.startswith("edit_delete_one:"))
async def edit_delete_one_shift(callback: types.CallbackQuery, state: FSMContext):
    if not await check_subscription(callback.from_user.id):
        await callback.answer("Нет подписки", show_alert=True)
        return

    shift_id = int(callback.data.split(":")[1])

    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM shifts WHERE id=?", (shift_id,))
        await db.commit()

    await callback.message.edit_text(
        "🗑️ Смена удалена.",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="📅 Выбрать другую дату", callback_data="calc_edit")],
            [types.InlineKeyboardButton(text="🔙 Главное меню", callback_data="calc_back_to_menu")]
        ])
    )
    await state.clear()
    await callback.answer("Удалено ✅")


# Игнорирование неактивных кнопок
@router.callback_query(F.data == "edit_ignore")
async def edit_ignore(callback: types.CallbackQuery):
    await callback.answer()


# Отмена редактирования
@router.callback_query(F.data == "edit_cancel")
async def edit_cancel(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.delete()
    await callback.bot.send_message(
        callback.from_user.id,
        "Редактирование отменено.",
        reply_markup=get_main_menu(await is_admin(callback.from_user.id))
    )
    await callback.answer()


@router.callback_query(EditState.waiting_for_edit_select, F.data.startswith("edit_select:"))
async def edit_select_shift(callback: types.CallbackQuery, state: FSMContext):
    if not await check_subscription(callback.from_user.id):
        await callback.answer("Нет подписки", show_alert=True)
        return

    shift_id = int(callback.data.split(":")[1])
    await state.update_data(edit_shift_id=shift_id, is_new=False)

    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT * FROM shifts WHERE id=?", (shift_id,))
        shift = await cursor.fetchone()

    if shift:
        date_obj = datetime.strptime(shift[2], '%Y-%m-%d')
        date_formatted = date_obj.strftime('%d.%m.%Y')

        text = (
            f"📝 Редактирование смены от {date_formatted}:\n"
            f"Текущие часы: {shift[3]} ч\n\n"
            f"Введите новое количество часов:"
        )
        await callback.message.delete()
        await callback.bot.send_message(
            callback.from_user.id,
            text,
            reply_markup=get_cancel_keyboard()
        )
        await state.set_state(EditState.waiting_for_edit_hours)

    await callback.answer()


@router.callback_query(EditState.waiting_for_edit_select, F.data.startswith("edit_delete_all:"))
async def edit_delete_all_shifts(callback: types.CallbackQuery, state: FSMContext):
    if not await check_subscription(callback.from_user.id):
        await callback.answer("Нет подписки", show_alert=True)
        return

    date_str = callback.data.split(":")[1]

    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM shifts WHERE user_id=? AND date=?", (callback.from_user.id, date_str))
        await db.commit()

    date_obj = datetime.strptime(date_str, '%Y-%m-%d')
    date_formatted = date_obj.strftime('%d.%m.%Y')

    await callback.message.edit_text(
        f"🗑️ Все смены за {date_formatted} удалены.",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="📅 Редактировать другую дату", callback_data="calc_edit")],
            [types.InlineKeyboardButton(text="🔙 Главное меню", callback_data="calc_back_to_menu")]
        ])
    )
    await state.clear()
    await callback.answer("Удалено ✅")


# Обработчики для новой смены
@router.message(CalcState.waiting_for_hours)
async def process_hours(message: types.Message, state: FSMContext):
    if message.text == "Отмена":
        await cancel_calc(message, state)
        return
    try:
        hours = float(message.text.replace(',', '.'))
        if hours <= 0:
            raise ValueError
        await state.update_data(hours=hours)
        await message.answer("Введите ставку за час (руб):")
        await state.set_state(CalcState.waiting_for_rate)
    except:
        await message.answer("Пожалуйста, введите положительное число.")


@router.message(CalcState.waiting_for_rate)
async def process_rate(message: types.Message, state: FSMContext):
    if message.text == "Отмена":
        await cancel_calc(message, state)
        return
    try:
        rate = float(message.text.replace(',', '.'))
        if rate <= 0:
            raise ValueError
        await state.update_data(rate=rate)
        await message.answer("Введите сумму выручки (руб):")
        await state.set_state(CalcState.waiting_for_revenue)
    except:
        await message.answer("Введите положительное число.")


@router.message(CalcState.waiting_for_revenue)
async def process_revenue(message: types.Message, state: FSMContext):
    if message.text == "Отмена":
        await cancel_calc(message, state)
        return
    try:
        revenue = float(message.text.replace(',', '.'))
        if revenue < 0:
            raise ValueError
        await state.update_data(revenue=revenue)
        await message.answer("Введите процент от выручки (%):")
        await state.set_state(CalcState.waiting_for_percent)
    except:
        await message.answer("Введите неотрицательное число.")


@router.message(CalcState.waiting_for_percent)
async def process_percent(message: types.Message, state: FSMContext):
    if message.text == "Отмена":
        await cancel_calc(message, state)
        return
    try:
        percent = float(message.text.replace(',', '.'))
        if percent < 0:
            raise ValueError
        await state.update_data(percent=percent)
        await message.answer("Введите сумму чаевых (руб, может быть 0):")
        await state.set_state(CalcState.waiting_for_tips)
    except:
        await message.answer("Введите неотрицательное число.")


@router.message(CalcState.waiting_for_tips)
async def process_tips(message: types.Message, state: FSMContext):
    if message.text == "Отмена":
        await cancel_calc(message, state)
        return
    try:
        tips = float(message.text.replace(',', '.'))
        if tips < 0:
            raise ValueError

        data = await state.get_data()
        hours = data['hours']
        rate = data['rate']
        revenue = data['revenue']
        percent = data['percent']

        # ЗП без чаевых
        salary_without_tips = calculate_shift(hours, rate, revenue, percent)

        user_id = message.from_user.id
        date = data.get('edit_date', datetime.now().strftime("%Y-%m-%d"))

        # Сохраняем в БД: total_salary = ЗП без чаевых
        await add_shift(user_id, date, hours, rate, revenue, percent, tips, salary_without_tips)

        await show_stats(message, user_id, hours, rate, revenue, percent, tips, date)
        await state.clear()
    except:
        await message.answer("Введите неотрицательное число.")


# Обработчики для редактирования/добавления смены
@router.message(EditState.waiting_for_edit_hours)
async def edit_process_hours(message: types.Message, state: FSMContext):
    if message.text == "Отмена":
        await state.clear()
        await message.answer("Действие отменено.", reply_markup=get_main_menu(await is_admin(message.from_user.id)))
        return
    try:
        hours = float(message.text.replace(',', '.'))
        if hours <= 0:
            raise ValueError
        await state.update_data(edit_hours=hours)
        await message.answer("Введите ставку за час (руб):")
        await state.set_state(EditState.waiting_for_edit_rate)
    except:
        await message.answer("Пожалуйста, введите положительное число.")


@router.message(EditState.waiting_for_edit_rate)
async def edit_process_rate(message: types.Message, state: FSMContext):
    if message.text == "Отмена":
        await state.clear()
        await message.answer("Действие отменено.", reply_markup=get_main_menu(await is_admin(message.from_user.id)))
        return
    try:
        rate = float(message.text.replace(',', '.'))
        if rate <= 0:
            raise ValueError
        await state.update_data(edit_rate=rate)
        await message.answer("Введите сумму выручки (руб):")
        await state.set_state(EditState.waiting_for_edit_revenue)
    except:
        await message.answer("Введите положительное число.")


@router.message(EditState.waiting_for_edit_revenue)
async def edit_process_revenue(message: types.Message, state: FSMContext):
    if message.text == "Отмена":
        await state.clear()
        await message.answer("Действие отменено.", reply_markup=get_main_menu(await is_admin(message.from_user.id)))
        return
    try:
        revenue = float(message.text.replace(',', '.'))
        if revenue < 0:
            raise ValueError
        await state.update_data(edit_revenue=revenue)
        await message.answer("Введите процент от выручки (%):")
        await state.set_state(EditState.waiting_for_edit_percent)
    except:
        await message.answer("Введите неотрицательное число.")


@router.message(EditState.waiting_for_edit_percent)
async def edit_process_percent(message: types.Message, state: FSMContext):
    if message.text == "Отмена":
        await state.clear()
        await message.answer("Действие отменено.", reply_markup=get_main_menu(await is_admin(message.from_user.id)))
        return
    try:
        percent = float(message.text.replace(',', '.'))
        if percent < 0:
            raise ValueError
        await state.update_data(edit_percent=percent)
        await message.answer("Введите сумму чаевых (руб, может быть 0):")
        await state.set_state(EditState.waiting_for_edit_tips)
    except:
        await message.answer("Введите неотрицательное число.")


@router.message(EditState.waiting_for_edit_tips)
async def edit_process_tips(message: types.Message, state: FSMContext):
    if message.text == "Отмена":
        await state.clear()
        await message.answer("Действие отменено.", reply_markup=get_main_menu(await is_admin(message.from_user.id)))
        return
    try:
        tips = float(message.text.replace(',', '.'))
        if tips < 0:
            raise ValueError

        data = await state.get_data()
        date_str = data['edit_date']
        hours = data['edit_hours']
        rate = data['edit_rate']
        revenue = data['edit_revenue']
        percent = data['edit_percent']
        is_new = data.get('is_new', False)

        # ЗП без чаевых
        salary_without_tips = calculate_shift(hours, rate, revenue, percent)

        date_obj = datetime.strptime(date_str, '%Y-%m-%d')
        date_formatted = date_obj.strftime('%d.%m.%Y')

        if is_new:
            # Добавляем новую смену
            await add_shift(message.from_user.id, date_str, hours, rate, revenue, percent, tips, salary_without_tips)

            await message.answer(
                f"✅ Новая смена добавлена на {date_formatted}!\n\n"
                f"📊 <b>Данные смены:</b>\n"
                f"⏱ Часы: {hours} ч × {rate} ₽/ч = <b>{hours * rate:.2f} ₽</b>\n"
                f"📈 Выручка: {revenue:.2f} ₽ × {percent}% = <b>{revenue * percent / 100:.2f} ₽</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"💰 Итого ЗП: <b>{salary_without_tips:.2f} ₽</b>\n"
                f"💝 Чаевые: <b>{tips:.2f} ₽</b>",
                reply_markup=get_main_menu(await is_admin(message.from_user.id)),
                parse_mode="HTML"
            )
        else:
            # Обновляем существующую смену
            shift_id = data['edit_shift_id']
            async with aiosqlite.connect(DB_NAME) as db:
                await db.execute('''
                    UPDATE shifts 
                    SET hours_worked=?, hourly_rate=?, revenue_base=?, revenue_percent=?, tips=?, total_salary=?
                    WHERE id=?
                ''', (hours, rate, revenue, percent, tips, salary_without_tips, shift_id))
                await db.commit()

            await message.answer(
                f"✅ Смена обновлена!\n\n"
                f"📊 <b>Новые данные:</b>\n"
                f"⏱ Часы: {hours} ч × {rate} ₽/ч = <b>{hours * rate:.2f} ₽</b>\n"
                f"📈 Выручка: {revenue:.2f} ₽ × {percent}% = <b>{revenue * percent / 100:.2f} ₽</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"💰 Итого ЗП: <b>{salary_without_tips:.2f} ₽</b>\n"
                f"💝 Чаевые: <b>{tips:.2f} ₽</b>",
                reply_markup=get_main_menu(await is_admin(message.from_user.id)),
                parse_mode="HTML"
            )

        await state.clear()
    except:
        await message.answer("Введите неотрицательное число.")


@router.callback_query(F.data == "calc_back_to_menu")
async def calc_back_to_menu(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.delete()
    await callback.bot.send_message(
        callback.from_user.id,
        "Главное меню",
        reply_markup=get_main_menu(await is_admin(callback.from_user.id))
    )
    await callback.answer()


async def show_stats(message: types.Message, user_id: int, hours: float, rate: float, revenue: float, percent: float,
                     tips: float, date_str: str):
    """Показывает детальную статистику после сохранения смены"""
    today = datetime.now().strftime("%Y-%m-%d")

    # Получаем все смены за сегодня
    today_shifts = await get_today_shifts(user_id)
    today_total_salary = sum(shift[8] for shift in today_shifts)  # total_salary теперь без чаевых
    today_total_tips = sum(shift[7] for shift in today_shifts)

    # Сумма за предыдущие дни
    prev_shifts = await get_all_previous_shifts(user_id)
    prev_total_salary = sum(shift[8] for shift in prev_shifts)
    prev_total_tips = sum(shift[7] for shift in prev_shifts)

    # Сумма за месяц
    now = datetime.now()
    month_shifts = await get_month_shifts(user_id, now.year, now.month)
    month_total_salary = sum(shift[8] for shift in month_shifts)
    month_total_tips = sum(shift[7] for shift in month_shifts)

    date_obj = datetime.strptime(date_str, '%Y-%m-%d')
    date_formatted = date_obj.strftime('%d.%m.%Y')

    # Считаем детали для отображения
    hourly_pay = hours * rate
    revenue_share = revenue * percent / 100
    salary_without_tips = hourly_pay + revenue_share

    text = (
        f"✅ Смена сохранена на {date_formatted}!\n\n"
        f"📊 <b>Данные смены:</b>\n"
        f"⏱ Часы: {hours} ч × {rate} ₽/ч = <b>{hourly_pay:.2f} ₽</b>\n"
        f"📈 Выручка: {revenue:.2f} ₽ × {percent}% = <b>{revenue_share:.2f} ₽</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"💰 Итого ЗП: <b>{salary_without_tips:.2f} ₽</b>\n"
        f"💝 Чаевые: <b>{tips:.2f} ₽</b>\n\n"
    )

    if date_str == today:
        text += (
            f"📊 <b>За сегодня:</b>\n"
            f"💰 Итого ЗП: <b>{today_total_salary:.2f} ₽</b>\n"
            f"💝 Итого чаевые: <b>{today_total_tips:.2f} ₽</b>\n\n"
        )

    text += (
        f"📅 <b>Предыдущие дни (суммарно):</b>\n"
        f"💰 Итого ЗП: <b>{prev_total_salary:.2f} ₽</b>\n"
        f"💝 Итого чаевые: <b>{prev_total_tips:.2f} ₽</b>\n\n"
        f"📆 <b>За текущий месяц:</b>\n"
        f"💰 Итого ЗП: <b>{month_total_salary:.2f} ₽</b>\n"
        f"💝 Итого чаевые: <b>{month_total_tips:.2f} ₽</b>"
    )

    await message.answer(text, reply_markup=get_main_menu(await is_admin(user_id)), parse_mode="HTML")


async def cancel_calc(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Действие отменено.", reply_markup=get_main_menu(await is_admin(message.from_user.id)))