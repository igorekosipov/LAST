from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

def get_admin_panel_keyboard():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="📋 Непроверенные чеки")],
        [KeyboardButton(text="👤 Управление подписками")],
        [KeyboardButton(text="🔙 Главное меню")]
    ], resize_keyboard=True)
