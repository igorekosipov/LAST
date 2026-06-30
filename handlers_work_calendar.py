from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from datetime import datetime
from database import add_day_off, get_days_off, is_admin
from keyboards_main_menu import get_main_menu
from utils_subscription_check import check_subscription
import aiosqlite
from database import DB_NAME
from calendar import monthcalendar

cal_router = Router()

MONTHS_RU = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"]
DAYS_RU = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]

async def build_calendar(year: int, month: int) -> types.InlineKeyboardMarkup:
    markup = types.InlineKeyboardMarkup(inline_keyboard=[])
    markup.inline_keyboard.append([types.InlineKeyboardButton(text=f"{MONTHS_RU[month-1]} {year}", callback_data="cal_ignore")])
    markup.inline_keyboard.append([
        types.InlineKeyboardButton(text="◀️", callback_data=f"cal_nav:prev:{year}:{month}"),
        types.InlineKeyboardButton(text="▶️", callback_data=f"cal_nav:next:{year}:{month}")
    ])
    markup.inline_keyboard.append([types.InlineKeyboardButton(text=day, callback_data="cal_ignore") for day in DAYS_RU])
    weeks = monthcalendar(year, month)
    today = datetime.now()
    for week in weeks:
        row = []
        for day in week:
            if day == 0:
                row.append(types.InlineKeyboardButton(text=" ", callback_data="cal_ignore"))
            else:
                date_str = f"{year}-{month:02d}-{day:02d}"
                if datetime(year, month, day).date() > today.date():
                    row.append(types.InlineKeyboardButton(text=f"❌{day}", callback_data="cal_ignore"))
                else:
                    row.append(types.InlineKeyboardButton(text=str(day), callback_data=f"cal_day:{date_str}"))
        markup.inline_keyboard.append(row)
    markup.inline_keyboard.append([types.InlineKeyboardButton(text="🔙 Назад", callback_data="cal_back")])
    return markup

@cal_router.message(lambda m: m.text == "📅 Календарь смен")
async def show_calendar(message: types.Message):
    if not await check_subscription(message.from_user.id):
        await message.answer("⚠️ У вас нет активной подписки.")
        return
    now = datetime.now()
    await message.answer("📅 Выберите дату:", reply_markup=await build_calendar(now.year, now.month))

@cal_router.callback_query(F.data.startswith("cal_nav:"))
async def cal_nav(callback: types.CallbackQuery):
    if not await check_subscription(callback.from_user.id): return await callback.answer("Нет подписки", show_alert=True)
    parts = callback.data.split(":")
    direction, year, month = parts[1], int(parts[2]), int(parts[3])
    if direction == "prev":
        month -= 1
        if month == 0: month = 12; year -= 1
    else:
        month += 1
        if month == 13: month = 1; year += 1
    await callback.message.edit_reply_markup(reply_markup=await build_calendar(year, month))
    await callback.answer()

@cal_router.callback_query(F.data.startswith("cal_day:"))
async def cal_day_selected(callback: types.CallbackQuery):
    if not await check_subscription(callback.from_user.id): return await callback.answer("Нет подписки", show_alert=True)
    date_str = callback.data.split(":")[1]
    date_obj = datetime.strptime(date_str, "%Y-%m-%d")
    date_formatted = date_obj.strftime("%d.%m.%Y")
    days = await get_days_off(callback.from_user.id)
    current_status = None
    for d, t in days:
        if d == date_str: current_status = t; break
    status_text = ""
    if current_status == "work": status_text = "\n📌 Сейчас: Рабочий день"
    elif current_status == "dayoff": status_text = "\n📌 Сейчас: Выходной день"
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="🔵 Рабочий день", callback_data=f"cal_set:work:{date_str}")],
        [types.InlineKeyboardButton(text="🔴 Выходной", callback_data=f"cal_set:dayoff:{date_str}")],
        [types.InlineKeyboardButton(text="📋 Все дни", callback_data="cal_list")],
        [types.InlineKeyboardButton(text="🔙 Назад", callback_data="cal_show")]
    ])
    await callback.message.edit_text(f"📅 {date_formatted}{status_text}", reply_markup=keyboard)
    await callback.answer()

@cal_router.callback_query(F.data.startswith("cal_set:"))
async def cal_set_day(callback: types.CallbackQuery):
    if not await check_subscription(callback.from_user.id): return await callback.answer("Нет подписки", show_alert=True)
    parts = callback.data.split(":")
    day_type, date_str = parts[1], parts[2]
    date_obj = datetime.strptime(date_str, "%Y-%m-%d")
    date_formatted = date_obj.strftime("%d.%m.%Y")
    await add_day_off(callback.from_user.id, date_str, day_type)
    type_text = "рабочий день" if day_type == "work" else "выходной"
    emoji = "🔵" if day_type == "work" else "🔴"
    await callback.message.edit_text(f"{emoji} {date_formatted} — {type_text}", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="📅 Календарь", callback_data="cal_show")],
        [types.InlineKeyboardButton(text="📋 Все дни", callback_data="cal_list")],
        [types.InlineKeyboardButton(text="🔙 Меню", callback_data="cal_back")]
    ]))
    await callback.answer("Сохранено ✅")

@cal_router.callback_query(F.data == "cal_show")
async def cal_show(callback: types.CallbackQuery):
    if not await check_subscription(callback.from_user.id): return await callback.answer("Нет подписки", show_alert=True)
    now = datetime.now()
    await callback.message.edit_text("📅 Выберите дату:", reply_markup=await build_calendar(now.year, now.month))
    await callback.answer()

@cal_router.callback_query(F.data == "cal_list")
async def cal_list(callback: types.CallbackQuery):
    if not await check_subscription(callback.from_user.id): return await callback.answer("Нет подписки", show_alert=True)
    days = await get_days_off(callback.from_user.id)
    if not days: text = "Нет отмеченных дней."
    else:
        text = "📅 Отмеченные дни:\n\n"
        for date, typ in sorted(days):
            emoji = "🔵" if typ == "work" else "🔴"
            text += f"{emoji} {date} — {'Рабочий' if typ == 'work' else 'Выходной'}\n"
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="🗑 Очистить", callback_data="cal_clear")],
        [types.InlineKeyboardButton(text="📅 Календарь", callback_data="cal_show")],
        [types.InlineKeyboardButton(text="🔙 Меню", callback_data="cal_back")]
    ])
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()

@cal_router.callback_query(F.data == "cal_clear")
async def cal_clear(callback: types.CallbackQuery):
    if not await check_subscription(callback.from_user.id): return await callback.answer("Нет подписки", show_alert=True)
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM days_off WHERE user_id=?", (callback.from_user.id,))
        await db.commit()
    await callback.message.edit_text("🗑 Все дни очищены.", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="📅 Календарь", callback_data="cal_show")],
        [types.InlineKeyboardButton(text="🔙 Меню", callback_data="cal_back")]
    ]))
    await callback.answer()

@cal_router.callback_query(F.data == "cal_ignore")
async def cal_ignore(callback: types.CallbackQuery): await callback.answer()

@cal_router.callback_query(F.data == "cal_back")
async def cal_back(callback: types.CallbackQuery):
    await callback.message.delete()
    await callback.bot.send_message(callback.from_user.id, "Главное меню", reply_markup=get_main_menu(await is_admin(callback.from_user.id)))
    await callback.answer()
