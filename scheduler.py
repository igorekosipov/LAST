import asyncio
from datetime import datetime, time
from database import is_admin
from utils.subscription_check import check_subscription


async def send_daily_reminder(bot):
    """Отправляет уведомление всем пользователям с активной подпиской"""
    from database import DB_NAME
    import aiosqlite

    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT telegram_id, first_name FROM users")
        users = await cursor.fetchall()

    now = datetime.now()
    today_str = now.strftime("%d.%m.%Y")

    for user in users:
        user_id = user[0]
        first_name = user[1]

        # Проверяем, есть ли активная подписка
        if await check_subscription(user_id):
            try:
                await bot.send_message(
                    user_id,
                    f"🌙 Доброй ночи, {first_name}!\n\n"
                    f"📅 {today_str}\n\n"
                    f"Не забудьте заполнить смену за сегодня! 📝\n"
                    f"Перейдите в раздел «🧮 Калькулятор» чтобы добавить данные.",
                    reply_markup=None
                )
            except Exception as e:
                print(f"Не удалось отправить уведомление пользователю {user_id}: {e}")

        # Небольшая задержка чтобы не превысить лимиты Telegram
        await asyncio.sleep(0.05)


async def scheduler_loop(bot):
    """Основной цикл планировщика"""
    while True:
        now = datetime.now()

        # Проверяем, наступило ли время 1:30
        if now.hour == 1 and now.minute == 30:
            print(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] Отправка ежедневных уведомлений...")
            await send_daily_reminder(bot)
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Уведомления отправлены")

            # Ждём 2 минуты чтобы не отправить повторно
            await asyncio.sleep(120)

        # Проверяем каждые 30 секунд
        await asyncio.sleep(30)


async def start_scheduler(bot):
    """Запускает планировщик в фоновом режиме"""
    asyncio.create_task(scheduler_loop(bot))
    print("Планировщик уведомлений запущен (ежедневно в 1:30)")