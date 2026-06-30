from aiogram import Router, types
from config import CHAT_INVITE_LINK
from utils.subscription_check import check_subscription

router = Router()


@router.message(lambda m: m.text == "💬 Чат подписчиков")
async def chat_link(message: types.Message):
    if not await check_subscription(message.from_user.id):
        await message.answer("⚠️ У вас нет активной подписки. Перейдите в раздел «💳 Моя подписка» для оплаты.")
        return

    await message.answer(f"Вот ссылка на закрытый чат подписчиков:\n{CHAT_INVITE_LINK}\n\nПрисоединяйтесь!")
