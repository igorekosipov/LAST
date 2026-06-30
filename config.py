import os

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS", "").split(","))) if os.getenv("ADMIN_IDS") else []

SUBSCRIPTION_PRICES = {
    "monthly": 100,
    "half_year": 599
}

PAYMENT_DETAILS = "Номер карты: 1234 5678 9012 3456 (Сбербанк)\nИли по номеру телефона +79001234567"
CHAT_INVITE_LINK = "https://t.me/+abcdefgh"

PROXY_URL = os.getenv("PROXY_URL", None)
