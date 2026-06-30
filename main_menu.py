from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

def get_main_menu(is_admin=False):
    buttons = [
        [KeyboardButton(text="🧮 Калькулятор"), KeyboardButton(text="📊 Моя статистика")],
        [KeyboardButton(text="📅 Календарь смен"), KeyboardButton(text="💬 Чат подписчиков")],
        [KeyboardButton(text="💳 Моя подписка"), KeyboardButton(text="🆘 Поддержка")]
    ]
    if is_admin:
        buttons.append([KeyboardButton(text="🔧 Админ-панель")])
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)