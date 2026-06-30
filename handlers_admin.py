from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from datetime import datetime, timedelta
from database import (get_pending_checks, update_check_status, get_check_by_id,
                       update_subscription, get_user, is_admin)
from keyboards_admin_panel import get_admin_panel_keyboard
from keyboards_subscription import get_admin_check_keyboard
from keyboards_main_menu import get_main_menu
import aiosqlite
from database import DB_NAME

admin_router = Router()

class ResetSubscriptionState(StatesGroup):
    waiting_for_user_id = State()
    waiting_for_confirm = State()

@admin_router.message(lambda m: m.text == "🔧 Админ-панель")
async def admin_panel(message: types.Message):
    if not await is_admin(message.from_user.id):
        await message.answer("⛔ У вас нет прав администратора.")
        return
    await message.answer("🔧 Админ-панель:", reply_markup=get_admin_panel_keyboard())

@admin_router.message(lambda m: m.text == "📋 Непроверенные чеки")
async def show_pending_checks(message: types.Message):
    if not await is_admin(message.from_user.id): return
    checks = await get_pending_checks()
    if not checks:
        await message.answer("Нет ожидающих проверки чеков.")
        return
    for check in checks:
        check_id, user_id, file_id, amount, plan, status, _ = check
        user = await get_user(user_id)
        user_info = f"{user['first_name']} (@{user['username']})" if user else str(user_id)
        caption = f"Чек #{check_id}\nОт: {user_info}\nСумма: {amount}₽\nТариф: {plan}"
        try:
            await message.answer_photo(file_id, caption=caption, reply_markup=get_admin_check_keyboard(check_id))
        except:
            await message.answer(f"{caption}\n(Фото не найдено)")

@admin_router.callback_query(F.data.startswith("admin_confirm:"))
async def confirm_payment(callback: types.CallbackQuery):
    if not await is_admin(callback.from_user.id): return await callback.answer("Нет прав", show_alert=True)
    check_id = int(callback.data.split(":")[1])
    check = await get_check_by_id(check_id)
    if not check: return await callback.answer("Чек не найден.")
    user_id, plan = check[1], check[4]
    days = 30 if plan == "monthly" else 180
    now = datetime.now()
    user = await get_user(user_id)
    if user and user["subscription_end"]:
        try:
            current_end = datetime.fromisoformat(user["subscription_end"])
            new_end = (current_end + timedelta(days=days)) if current_end > now else (now + timedelta(days=days))
        except:
            new_end = now + timedelta(days=days)
    else:
        new_end = now + timedelta(days=days)
    await update_subscription(user_id, new_end.isoformat())
    await update_check_status(check_id, "confirmed")
    try:
        await callback.bot.send_message(user_id, f"✅ Подписка подтверждена! Действует до: {new_end.strftime('%d.%m.%Y')}")
    except: pass
    await callback.message.edit_caption(caption=callback.message.caption + f"\n\n✅ ПОДТВЕРЖДЕНО\nДо: {new_end.strftime('%d.%m.%Y')}")
    await callback.answer("✅ Подписка подтверждена")

@admin_router.callback_query(F.data.startswith("admin_decline:"))
async def decline_payment(callback: types.CallbackQuery):
    if not await is_admin(callback.from_user.id): return await callback.answer("Нет прав", show_alert=True)
    check_id = int(callback.data.split(":")[1])
    check = await get_check_by_id(check_id)
    if not check: return await callback.answer("Чек не найден.")
    user_id = check[1]
    await update_check_status(check_id, "declined")
    try:
        await callback.bot.send_message(user_id, "❌ Ваш платёж не подтверждён.")
    except: pass
    await callback.message.edit_caption(caption=callback.message.caption + "\n\n❌ ОТКЛОНЕНО")
    await callback.answer("❌ Платёж отклонён")

@admin_router.message(lambda m: m.text == "👤 Управление подписками")
async def manage_subscriptions(message: types.Message):
    if not await is_admin(message.from_user.id): return
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="📋 Список пользователей", callback_data="admin_list_users")],
        [types.InlineKeyboardButton(text="🔄 Сбросить подписку", callback_data="admin_reset_sub")],
        [types.InlineKeyboardButton(text="🗑 Сбросить ВСЕ подписки", callback_data="admin_reset_all_subs")],
        [types.InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back_to_panel")]
    ])
    await message.answer("👤 Управление подписками:", reply_markup=keyboard)

@admin_router.callback_query(F.data == "admin_list_users")
async def list_users(callback: types.CallbackQuery):
    if not await is_admin(callback.from_user.id): return await callback.answer("Нет прав", show_alert=True)
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT telegram_id, first_name, username, subscription_end, is_admin FROM users ORDER BY is_admin DESC, first_name")
        users = await cursor.fetchall()
    if not users: await callback.message.edit_text("Нет пользователей."); return
    text = "📋 Пользователи:\n\n"
    for uid, first_name, username, sub_end, adm in users:
        status = "👑" if adm else "👤"
        username_str = f"@{username}" if username else "нет"
        sub_status = "❌ Нет"
        if sub_end:
            try:
                end_date = datetime.fromisoformat(sub_end)
                if end_date > datetime.now(): sub_status = f"✅ {end_date.strftime('%d.%m.%Y')}"
                else: sub_status = "❌ Истекла"
            except: pass
        text += f"{status} <code>{uid}</code> {first_name} ({username_str}) - {sub_status}\n"
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back_to_subs")]
    ]))

@admin_router.callback_query(F.data == "admin_reset_sub")
async def reset_sub_start(callback: types.CallbackQuery, state: FSMContext):
    if not await is_admin(callback.from_user.id): return await callback.answer("Нет прав", show_alert=True)
    await callback.message.edit_text("Введите Telegram ID пользователя для сброса подписки:")
    await state.set_state(ResetSubscriptionState.waiting_for_user_id)

@admin_router.message(ResetSubscriptionState.waiting_for_user_id)
async def process_reset_user_id(message: types.Message, state: FSMContext):
    if not await is_admin(message.from_user.id): return await state.clear()
    try: user_id = int(message.text.strip())
    except: await message.answer("Введите число."); return
    user = await get_user(user_id)
    if not user: await message.answer("Пользователь не найден."); await state.clear(); return
    await state.update_data(reset_user_id=user_id)
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="✅ Да, сбросить", callback_data="admin_confirm_reset"),
         types.InlineKeyboardButton(text="❌ Отмена", callback_data="admin_cancel_reset")]
    ])
    await message.answer(f"Сбросить подписку у {user['first_name']} (ID: {user_id})?", reply_markup=keyboard)
    await state.set_state(ResetSubscriptionState.waiting_for_confirm)

@admin_router.callback_query(ResetSubscriptionState.waiting_for_confirm, F.data == "admin_confirm_reset")
async def do_reset(callback: types.CallbackQuery, state: FSMContext):
    if not await is_admin(callback.from_user.id): return
    data = await state.get_data()
    user_id = data['reset_user_id']
    await update_subscription(user_id, None)
    user = await get_user(user_id)
    await callback.message.edit_text(f"✅ Подписка пользователя {user['first_name']} (ID: {user_id}) сброшена.")
    try: await callback.bot.send_message(user_id, "⚠️ Ваша подписка сброшена администратором.")
    except: pass
    await state.clear()

@admin_router.callback_query(ResetSubscriptionState.waiting_for_confirm, F.data == "admin_cancel_reset")
async def cancel_reset(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("❌ Отменено.")
    await state.clear()

@admin_router.callback_query(F.data == "admin_reset_all_subs")
async def reset_all_subs_confirm(callback: types.CallbackQuery):
    if not await is_admin(callback.from_user.id): return
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="⚠️ Да, сбросить ВСЕ", callback_data="admin_do_reset_all"),
         types.InlineKeyboardButton(text="❌ Отмена", callback_data="admin_cancel_reset_all")]
    ])
    await callback.message.edit_text("⚠️ Сбросить подписки ВСЕХ пользователей?", reply_markup=keyboard)

@admin_router.callback_query(F.data == "admin_do_reset_all")
async def do_reset_all(callback: types.CallbackQuery):
    if not await is_admin(callback.from_user.id): return
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE users SET subscription_end = NULL WHERE is_admin = 0")
        await db.execute("DELETE FROM payment_checks")
        await db.commit()
    await callback.message.edit_text("✅ Все подписки сброшены.")

@admin_router.callback_query(F.data == "admin_cancel_reset_all")
async def cancel_reset_all(callback: types.CallbackQuery):
    await callback.message.edit_text("❌ Отменено.")

@admin_router.callback_query(F.data == "admin_back_to_panel")
async def back_to_panel(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.delete()
    await callback.bot.send_message(callback.from_user.id, "Админ-панель:", reply_markup=get_admin_panel_keyboard())

@admin_router.callback_query(F.data == "admin_back_to_subs")
async def back_to_subs(callback: types.CallbackQuery):
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="📋 Список пользователей", callback_data="admin_list_users")],
        [types.InlineKeyboardButton(text="🔄 Сбросить подписку", callback_data="admin_reset_sub")],
        [types.InlineKeyboardButton(text="🗑 Сбросить ВСЕ подписки", callback_data="admin_reset_all_subs")],
        [types.InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back_to_panel")]
    ])
    await callback.message.edit_text("👤 Управление подписками:", reply_markup=keyboard)

@admin_router.message(lambda m: m.text == "🔙 Главное меню")
async def back_to_menu(message: types.Message):
    await message.answer("Главное меню", reply_markup=get_main_menu(await is_admin(message.from_user.id)))
