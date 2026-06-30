from aiogram import Router, types, F
from aiogram_calendar import SimpleCalendar, SimpleCalendarCallback
from database import add_day_off, get_days_off, is_admin
from keyboards.main_menu import get_main_menu
from utils.subscription_check import check_subscription
import aiosqlite
from database import DB_NAME
from datetime import datetime

router = Router()

# Русские названия месяцев
MONTHS_RU = [
    "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"
]

# Дни недели на русском
DAYS_RU = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]


class RuSimpleCalendar(SimpleCalendar):
    """Календарь на русском языке"""

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
                callback_data="ignore"
            )
        ])

        # Кнопки навигации
        markup.inline_keyboard.append([
            types.InlineKeyboardButton(text="◀️", callback_data=f"cal_nav:prev:{year}:{month}"),
            types.InlineKeyboardButton(text="▶️", callback_data=f"cal_nav:next:{year}:{month}")
        ])

        # Дни недели
        markup.inline_keyboard.append([
            types.InlineKeyboardButton(text=day, callback_data="ignore") for day in DAYS_RU
        ])

        # Дни месяца
        from calendar import monthcalendar
        weeks = monthcalendar(year, month)

        for week in weeks:
            row = []
            for day in week:
                if day == 0:
                    row.append(types.InlineKeyboardButton(text=" ", callback_data="ignore"))
                else:
                    date_str = f"{year}-{month:02d}-{day:02d}"
                    row.append(types.InlineKeyboardButton(
                        text=str(day),
                        callback_data=f"cal_day:{date_str}"
                    ))
            markup.inline_keyboard.append(row)

        # Кнопка "Назад"
        markup.inline_keyboard.append([
            types.InlineKeyboardButton(text="🔙 Назад", callback_data="cal_back")
        ])

        return markup


@router.message(lambda m: m.text == "📅 Календарь смен")
async def show_calendar(message: types.Message):
    if not await check_subscription(message.from_user.id):
        await message.answer("⚠️ У вас нет активной подписки. Перейдите в раздел «💳 Моя подписка» для оплаты.")
        return

    calendar = RuSimpleCalendar()
    await message.answer(
        "📅 Выберите дату для отметки рабочего/выходного дня:",
        reply_markup=await calendar.start_calendar()
    )


@router.callback_query(F.data.startswith("cal_nav:"))
async def cal_nav(callback: types.CallbackQuery):
    """Навигация по календарю"""
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

    calendar = RuSimpleCalendar()
    await callback.message.edit_reply_markup(
        reply_markup=await calendar.start_calendar(year, month)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("cal_day:"))
async def cal_day_selected(callback: types.CallbackQuery):
    """Выбрана дата в календаре смен"""
    if not await check_subscription(callback.from_user.id):
        await callback.answer("Нет подписки", show_alert=True)
        return

    date_str = callback.data.split(":")[1]
    date_obj = datetime.strptime(date_str, "%Y-%m-%d")
    date_formatted = date_obj.strftime("%d.%m.%Y")

    # Получаем текущий статус дня
    days = await get_days_off(callback.from_user.id)
    current_status = None
    for d, t in days:
        if d == date_str:
            current_status = t
            break

    # Создаём кнопки в зависимости от статуса
    buttons = []

    if current_status == "work":
        buttons.append([types.InlineKeyboardButton(
            text="✅ Рабочий день (отмечен)",
            callback_data=f"day_toggle:{date_str}:work"
        )])
        buttons.append([types.InlineKeyboardButton(
            text="❌ Отметить выходным",
            callback_data=f"day_toggle:{date_str}:dayoff"
        )])
    elif current_status == "dayoff":
        buttons.append([types.InlineKeyboardButton(
            text="✅ Отметить рабочим",
            callback_data=f"day_toggle:{date_str}:work"
        )])
        buttons.append([types.InlineKeyboardButton(
            text="❌ Выходной день (отмечен)",
            callback_data=f"day_toggle:{date_str}:dayoff"
        )])
    else:
        buttons.append([types.InlineKeyboardButton(
            text="🔵 Отметить рабочим днём",
            callback_data=f"day_toggle:{date_str}:work"
        )])
        buttons.append([types.InlineKeyboardButton(
            text="🔴 Отметить выходным",
            callback_data=f"day_toggle:{date_str}:dayoff"
        )])

    buttons.append([types.InlineKeyboardButton(
        text="🔍 Посмотреть все отмеченные дни",
        callback_data="list_days"
    )])
    buttons.append([types.InlineKeyboardButton(
        text="🔙 Назад к календарю",
        callback_data="cal_show"
    )])

    keyboard = types.InlineKeyboardMarkup(inline_keyboard=buttons)

    status_text = ""
    if current_status == "work":
        status_text = "\n📌 Текущий статус: Рабочий день"
    elif current_status == "dayoff":
        status_text = "\n📌 Текущий статус: Выходной день"

    await callback.message.edit_text(
        f"📅 Выбрана дата: {date_formatted}{status_text}\nВыберите действие:",
        reply_markup=keyboard
    )
    await callback.answer()


@router.callback_query(F.data.startswith("day_toggle:"))
async def toggle_day_status(callback: types.CallbackQuery):
    """Переключение статуса дня"""
    if not await check_subscription(callback.from_user.id):
        await callback.answer("Нет подписки", show_alert=True)
        return

    parts = callback.data.split(":")
    date_str = parts[1]
    new_type = parts[2]

    date_obj = datetime.strptime(date_str, "%Y-%m-%d")
    date_formatted = date_obj.strftime("%d.%m.%Y")

    await add_day_off(callback.from_user.id, date_str, new_type)

    type_text = "рабочий день" if new_type == "work" else "выходной день"
    emoji = "🔵" if new_type == "work" else "🔴"

    await callback.message.edit_text(
        f"{emoji} {date_formatted} отмечен как {type_text}!",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="📅 Вернуться к календарю", callback_data="cal_show")],
            [types.InlineKeyboardButton(text="🔍 Все отмеченные дни", callback_data="list_days")],
            [types.InlineKeyboardButton(text="🔙 Главное меню", callback_data="cal_back")]
        ])
    )
    await callback.answer("Сохранено ✅")


@router.callback_query(F.data == "cal_show")
async def cal_show(callback: types.CallbackQuery):
    """Показать календарь снова"""
    if not await check_subscription(callback.from_user.id):
        await callback.answer("Нет подписки", show_alert=True)
        return

    calendar = RuSimpleCalendar()
    await callback.message.edit_text(
        "📅 Выберите дату для отметки рабочего/выходного дня:",
        reply_markup=await calendar.start_calendar()
    )
    await callback.answer()


@router.callback_query(F.data == "list_days")
async def list_marked_days(callback: types.CallbackQuery):
    if not await check_subscription(callback.from_user.id):
        await callback.answer("Нет подписки", show_alert=True)
        return

    days = await get_days_off(callback.from_user.id)
    if not days:
        await callback.message.edit_text(
            "У вас пока нет отмеченных дней.",
            reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(text="📅 Вернуться к календарю", callback_data="cal_show")],
                [types.InlineKeyboardButton(text="🔙 Главное меню", callback_data="cal_back")]
            ])
        )
    else:
        text = "📅 <b>Ваш календарь смен:</b>\n\n"
        for date, typ in sorted(days):
            date_obj = datetime.strptime(date, "%Y-%m-%d")
            date_formatted = date_obj.strftime("%d.%m.%Y")
            emoji = "🔵" if typ == "work" else "🔴"
            text += f"{emoji} {date_formatted} - {'Рабочий' if typ == 'work' else 'Выходной'}\n"

        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="🗑️ Очистить все отметки", callback_data="clear_days")],
            [types.InlineKeyboardButton(text="📅 Вернуться к календарю", callback_data="cal_show")],
            [types.InlineKeyboardButton(text="🔙 Главное меню", callback_data="cal_back")]
        ])
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "clear_days")
async def clear_all_days(callback: types.CallbackQuery):
    if not await check_subscription(callback.from_user.id):
        await callback.answer("Нет подписки", show_alert=True)
        return

    user_id = callback.from_user.id
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM days_off WHERE user_id=?", (user_id,))
        await db.commit()

    await callback.message.edit_text(
        "🗑️ Все отмеченные дни удалены.",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="📅 Вернуться к календарю", callback_data="cal_show")],
            [types.InlineKeyboardButton(text="🔙 Главное меню", callback_data="cal_back")]
        ])
    )
    await callback.answer()


@router.callback_query(F.data == "cal_back")
async def cal_back(callback: types.CallbackQuery):
    await callback.message.delete()
    await callback.bot.send_message(
        callback.from_user.id,
        "Главное меню",
        reply_markup=get_main_menu(await is_admin(callback.from_user.id))
    )
    await callback.answer()


@router.callback_query(F.data == "ignore")
async def ignore_callback(callback: types.CallbackQuery):
    """Игнорируем нажатия на неактивные кнопки"""
    await callback.answer()