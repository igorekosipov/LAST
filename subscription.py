from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def get_subscription_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 100₽ - месяц", callback_data="sub_plan:monthly")],
        [InlineKeyboardButton(text="💳 599₽ - полгода", callback_data="sub_plan:half_year")],
        [InlineKeyboardButton(text="⏳ Проверить подписку", callback_data="sub_check")]
    ])

def get_payment_actions():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 Я оплатил", callback_data="pay_upload")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="sub_back")]
    ])

def get_admin_check_keyboard(check_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"admin_confirm:{check_id}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"admin_decline:{check_id}")
        ]
    ])