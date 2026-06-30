from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from datetime import datetime, timedelta
from database import (get_pending_checks, update_check_status, get_check_by_id,
                      update_subscription, get_user, is_admin)
from keyboards.admin_panel import get_admin_panel_keyboard
from keyboards.subscription import get_admin_check_keyboard
from keyboards.main_menu import get_main_menu
import aiosqlite
from database import DB_NAME

router = Router()


class ResetSubscriptionState(StatesGroup):
    waiting_for_user_id = State()
    waiting_for_confirm = State()


@router.message(lambda m: m.text == "🔧 Админ-панель")
async def admin_panel(message: types.Message):
    if not await is_admin(message.from_user.id):
        await message.answer("⛔ У вас нет прав администратора.")
        return

    await message.answer("🔧 Админ-панель:", reply_markup=get_admin_panel_keyboard())


@router.message(lambda m: m.text == "📋 Непроверенные чеки")
async def show_pending_checks(message: types.Message):
    if not await is_admin(message.from_user.id):
        await message.answer("⛔ У вас нет прав администратора.")
        return

    checks = await get_pending_checks()
    if not checks:
        await message.answer("Нет ожидающих проверки чеков.")
        return

    for check in checks:
        check_id = check[0]
        user_id = check[1]
        file_id = check[2]
        amount = check[3]
        plan = check[4]

        user = await get_user(user_id)
        if user:
            user_info = f"{user['first_name']}"
            if user['username']:
                user_info += f" (@{user['username']})"
        else:
            user_info = str(user_id)

        caption = f"Чек #{check_id}\nОт: {user_info}\nСумма: {amount}₽\nТариф: {plan}"

        try:
            await message.answer_photo(
                file_id,
                caption=caption,
                reply_markup=get_admin_check_keyboard(check_id)
            )
        except:
            await message.answer(f"{caption}\n(Фото не найдено)")


@router.callback_query(F.data.startswith("admin_confirm:"))
async def confirm_payment(callback: types.CallbackQuery):
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет прав администратора", show_alert=True)
        return

    check_id = int(callback.data.split(":")[1])
    check = await get_check_by_id(check_id)

    if not check:
        await callback.answer("Чек не найден.")
        return

    user_id = check[1]
    plan = check[4]

    # Определяем количество дней подписки
    if plan == "monthly":
        days_to_add = 30
    elif plan == "half_year":
        days_to_add = 180
    else:
        days_to_add = 30

    # Получаем текущую дату окончания подписки пользователя
    user = await get_user(user_id)
    now = datetime.now()

    if user and user["subscription_end"]:
        try:
            current_end = datetime.fromisoformat(user["subscription_end"])
            # Если подписка ещё активна - добавляем дни к концу подписки
            if current_end > now:
                new_end = current_end + timedelta(days=days_to_add)
            else:
                # Если подписка истекла - начинаем с текущей даты
                new_end = now + timedelta(days=days_to_add)
        except:
            new_end = now + timedelta(days=days_to_add)
    else:
        # Если подписки нет - начинаем с текущей даты
        new_end = now + timedelta(days=days_to_add)

    # Сохраняем новую дату
    await update_subscription(user_id, new_end.isoformat())

    # Обновляем статус чека
    await update_check_status(check_id, "confirmed")

    # Уведомляем пользователя
    try:
        await callback.bot.send_message(
            user_id,
            f"✅ Ваша подписка подтверждена!\n"
            f"Действует до: {new_end.strftime('%d.%m.%Y')}\n"
            f"Добавлено дней: {days_to_add}"
        )
    except:
        pass

    # Обновляем сообщение с чеком
    try:
        await callback.message.edit_caption(
            caption=callback.message.caption + f"\n\n✅ ПОДТВЕРЖДЕНО\nПодписка до: {new_end.strftime('%d.%m.%Y')}"
        )
    except:
        pass

    await callback.answer("✅ Подписка подтверждена")


@router.callback_query(F.data.startswith("admin_decline:"))
async def decline_payment(callback: types.CallbackQuery):
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет прав администратора", show_alert=True)
        return

    check_id = int(callback.data.split(":")[1])
    check = await get_check_by_id(check_id)

    if not check:
        await callback.answer("Чек не найден.")
        return

    user_id = check[1]

    # Обновляем статус чека
    await update_check_status(check_id, "declined")

    # Уведомляем пользователя
    try:
        await callback.bot.send_message(
            user_id,
            "❌ Ваш платёж не подтверждён. Свяжитесь с поддержкой."
        )
    except:
        pass

    # Обновляем сообщение с чеком
    try:
        await callback.message.edit_caption(
            caption=callback.message.caption + "\n\n❌ ОТКЛОНЕНО"
        )
    except:
        pass

    await callback.answer("❌ Платёж отклонён")


# ==================== Управление подписками ====================

@router.message(lambda m: m.text == "👤 Управление подписками")
async def manage_subscriptions_menu(message: types.Message):
    if not await is_admin(message.from_user.id):
        await message.answer("⛔ У вас нет прав администратора.")
        return

    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="📋 Список всех пользователей", callback_data="admin_list_users")],
        [types.InlineKeyboardButton(text="🔄 Сбросить подписку пользователю", callback_data="admin_reset_sub")],
        [types.InlineKeyboardButton(text="🗑 Сбросить ВСЕ подписки", callback_data="admin_reset_all_subs")],
        [types.InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back_to_panel")]
    ])
    await message.answer("👤 Управление подписками:", reply_markup=keyboard)


@router.callback_query(F.data == "admin_list_users")
async def list_all_users(callback: types.CallbackQuery):
    if not await is_admin(callback.from_user.id):
        await callback.answer("Нет прав", show_alert=True)
        return

    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute(
            "SELECT telegram_id, first_name, username, subscription_end, is_admin FROM users ORDER BY is_admin DESC, first_name")
        users = await cursor.fetchall()

    if not users:
        await callback.message.edit_text("Нет зарегистрированных пользователей.")
        return

    text = "📋 <b>Список пользователей:</b>\n\n"

    for user in users:
        telegram_id, first_name, username, sub_end, is_admin_flag = user
        admin_status = "👑" if is_admin_flag else "👤"
        username_str = f"@{username}" if username else "нет username"

        if sub_end:
            try:
                end_date = datetime.fromisoformat(sub_end)
                now = datetime.now()
                if end_date > now:
                    days_left = (end_date - now).days
                    sub_status = f"✅ Активна ({days_left} дн.)"
                else:
                    sub_status = "❌ Истекла"
            except:
                sub_status = "❌ Ошибка даты"
        else:
            sub_status = "❌ Нет подписки"

        text += f"{admin_status} <code>{telegram_id}</code> - {first_name} ({username_str})\n{sub_status}\n\n"

    # Разбиваем на части если слишком длинное
    if len(text) > 4000:
        parts = [text[i:i + 4000] for i in range(0, len(text), 4000)]
        for part in parts:
            await callback.message.answer(part, parse_mode="HTML")
        await callback.message.delete()
    else:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=get_back_to_admin_kb())

    await callback.answer()


@router.callback_query(F.data == "admin_reset_sub")
async def reset_sub_start(callback: types.CallbackQuery, state: FSMContext):
    if not await is_admin(callback.from_user.id):
        await callback.answer("Нет прав", show_alert=True)
        return

    await callback.message.edit_text(
        "Введите Telegram ID пользователя, которому нужно сбросить подписку:\n\n"
        "Для отмены нажмите /cancel",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="🔙 Отмена", callback_data="admin_back_to_panel")]
        ])
    )
    await state.set_state(ResetSubscriptionState.waiting_for_user_id)
    await callback.answer()


@router.message(ResetSubscriptionState.waiting_for_user_id)
async def process_user_id_for_reset(message: types.Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        await state.clear()
        return

    try:
        user_id = int(message.text.strip())
    except:
        await message.answer("❌ Введите корректный Telegram ID (число).")
        return

    user = await get_user(user_id)
    if not user:
        await message.answer(f"❌ Пользователь с ID {user_id} не найден.")
        await state.clear()
        return

    sub_status = "активна" if user["subscription_end"] else "отсутствует"

    await state.update_data(reset_user_id=user_id)

    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [
            types.InlineKeyboardButton(text="✅ Да, сбросить", callback_data="admin_confirm_reset"),
            types.InlineKeyboardButton(text="❌ Нет, отмена", callback_data="admin_cancel_reset")
        ]
    ])

    await message.answer(
        f"Пользователь: {user['first_name']} (@{user['username']})\n"
        f"ID: {user_id}\n"
        f"Текущая подписка: {sub_status}\n\n"
        f"Вы уверены, что хотите сбросить подписку?",
        reply_markup=keyboard
    )
    await state.set_state(ResetSubscriptionState.waiting_for_confirm)


@router.callback_query(ResetSubscriptionState.waiting_for_confirm, F.data == "admin_confirm_reset")
async def confirm_reset_sub(callback: types.CallbackQuery, state: FSMContext):
    if not await is_admin(callback.from_user.id):
        await callback.answer("Нет прав", show_alert=True)
        return

    data = await state.get_data()
    user_id = data['reset_user_id']

    # Сбрасываем подписку
    await update_subscription(user_id, None)

    user = await get_user(user_id)

    await callback.message.edit_text(
        f"✅ Подписка пользователя {user['first_name']} (ID: {user_id}) сброшена.",
        reply_markup=get_back_to_admin_kb()
    )

    # Уведомляем пользователя
    try:
        await callback.bot.send_message(
            user_id,
            "⚠️ Ваша подписка была сброшена администратором. Для возобновления доступа оплатите подписку в разделе «💳 Моя подписка»."
        )
    except:
        pass

    await state.clear()
    await callback.answer()


@router.callback_query(ResetSubscriptionState.waiting_for_confirm, F.data == "admin_cancel_reset")
async def cancel_reset_sub(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("❌ Сброс подписки отменён.", reply_markup=get_back_to_admin_kb())
    await state.clear()
    await callback.answer()


@router.callback_query(F.data == "admin_reset_all_subs")
async def reset_all_subscriptions(callback: types.CallbackQuery):
    if not await is_admin(callback.from_user.id):
        await callback.answer("Нет прав", show_alert=True)
        return

    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [
            types.InlineKeyboardButton(text="⚠️ Да, сбросить ВСЕ подписки", callback_data="admin_confirm_reset_all"),
            types.InlineKeyboardButton(text="❌ Отмена", callback_data="admin_cancel_reset_all")
        ]
    ])

    await callback.message.edit_text(
        "⚠️ <b>ВНИМАНИЕ!</b>\n\n"
        "Вы собираетесь сбросить подписки у ВСЕХ пользователей!\n"
        "Это действие нельзя отменить.\n\n"
        "Вы уверены?",
        parse_mode="HTML",
        reply_markup=keyboard
    )
    await callback.answer()


@router.callback_query(F.data == "admin_confirm_reset_all")
async def confirm_reset_all_subs(callback: types.CallbackQuery):
    if not await is_admin(callback.from_user.id):
        await callback.answer("Нет прав", show_alert=True)
        return

    async with aiosqlite.connect(DB_NAME) as db:
        # Сбрасываем подписки всем, кроме админов
        await db.execute("UPDATE users SET subscription_end = NULL WHERE is_admin = 0")
        # Очищаем историю платежей
        await db.execute("DELETE FROM payment_checks")
        await db.commit()

    await callback.message.edit_text(
        "✅ Все подписки пользователей сброшены.\n"
        "Подписки администраторов сохранены.\n"
        "История платежей очищена.",
        reply_markup=get_back_to_admin_kb()
    )
    await callback.answer("Готово ✅")


@router.callback_query(F.data == "admin_cancel_reset_all")
async def cancel_reset_all_subs(callback: types.CallbackQuery):
    await callback.message.edit_text("❌ Сброс всех подписок отменён.", reply_markup=get_back_to_admin_kb())
    await callback.answer()


@router.callback_query(F.data == "admin_back_to_panel")
async def back_to_panel(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.delete()
    await callback.bot.send_message(
        callback.from_user.id,
        "Админ-панель:",
        reply_markup=get_admin_panel_keyboard()
    )
    await callback.answer()


def get_back_to_admin_kb():
    return types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="🔙 Назад к управлению", callback_data="admin_back_to_subs_menu")],
        [types.InlineKeyboardButton(text="🔙 Админ-панель", callback_data="admin_back_to_panel")]
    ])


@router.callback_query(F.data == "admin_back_to_subs_menu")
async def back_to_subs_menu(callback: types.CallbackQuery):
    if not await is_admin(callback.from_user.id):
        await callback.answer("Нет прав", show_alert=True)
        return

    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="📋 Список всех пользователей", callback_data="admin_list_users")],
        [types.InlineKeyboardButton(text="🔄 Сбросить подписку пользователю", callback_data="admin_reset_sub")],
        [types.InlineKeyboardButton(text="🗑 Сбросить ВСЕ подписки", callback_data="admin_reset_all_subs")],
        [types.InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back_to_panel")]
    ])
    await callback.message.edit_text("👤 Управление подписками:", reply_markup=keyboard)
    await callback.answer()


@router.message(lambda m: m.text == "🔙 Главное меню")
async def back_to_menu(message: types.Message):
    await message.answer("Главное меню", reply_markup=get_main_menu(await is_admin(message.from_user.id)))
