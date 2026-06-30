import aiosqlite
from datetime import datetime

DB_NAME = "bot_database.db"

async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                telegram_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                subscription_end TEXT,
                is_admin INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS shifts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                date TEXT,
                hours_worked REAL,
                hourly_rate REAL,
                revenue_base REAL,
                revenue_percent REAL,
                tips REAL,
                total_salary REAL,
                FOREIGN KEY (user_id) REFERENCES users(telegram_id)
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS payment_checks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                file_id TEXT,
                amount REAL,
                plan TEXT,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS days_off (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                date TEXT,
                type TEXT,
                FOREIGN KEY (user_id) REFERENCES users(telegram_id)
            )
        ''')
        await db.commit()

async def get_user(user_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM users WHERE telegram_id=?", (user_id,))
        return await cursor.fetchone()

async def add_user(user_id: int, username: str, first_name: str):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT OR IGNORE INTO users (telegram_id, username, first_name) VALUES (?,?,?)",
                         (user_id, username, first_name))
        await db.commit()

async def set_admin(user_id: int, is_admin_value: int = 1):
    """Установить или снять права администратора"""
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE users SET is_admin=? WHERE telegram_id=?", (is_admin_value, user_id))
        await db.commit()

async def update_subscription(user_id: int, new_end_date: str):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE users SET subscription_end=? WHERE telegram_id=?", (new_end_date, user_id))
        await db.commit()

async def is_admin(user_id: int) -> bool:
    user = await get_user(user_id)
    return user and user["is_admin"] == 1

async def add_shift(user_id: int, date: str, hours: float, rate: float, revenue: float, percent: float, tips: float, total: float):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('''
            INSERT INTO shifts (user_id, date, hours_worked, hourly_rate, revenue_base, revenue_percent, tips, total_salary)
            VALUES (?,?,?,?,?,?,?,?)
        ''', (user_id, date, hours, rate, revenue, percent, tips, total))
        await db.commit()

async def get_today_shifts(user_id: int):
    today = datetime.now().strftime("%Y-%m-%d")
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT * FROM shifts WHERE user_id=? AND date=?", (user_id, today))
        return await cursor.fetchall()

async def get_month_shifts(user_id: int, year: int, month: int):
    start_date = f"{year}-{month:02d}-01"
    if month == 12:
        end_date = f"{year+1}-01-01"
    else:
        end_date = f"{year}-{month+1:02d}-01"
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT * FROM shifts WHERE user_id=? AND date >= ? AND date < ?",
                                  (user_id, start_date, end_date))
        return await cursor.fetchall()

async def get_all_previous_shifts(user_id: int):
    today = datetime.now().strftime("%Y-%m-%d")
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT * FROM shifts WHERE user_id=? AND date < ?", (user_id, today))
        return await cursor.fetchall()

async def add_payment_check(user_id: int, file_id: str, amount: float, plan: str):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("INSERT INTO payment_checks (user_id, file_id, amount, plan) VALUES (?,?,?,?)",
                                 (user_id, file_id, amount, plan))
        await db.commit()
        return cursor.lastrowid

async def get_pending_checks():
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT * FROM payment_checks WHERE status='pending'")
        return await cursor.fetchall()

async def update_check_status(check_id: int, status: str):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE payment_checks SET status=? WHERE id=?", (status, check_id))
        await db.commit()

async def get_check_by_id(check_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT * FROM payment_checks WHERE id=?", (check_id,))
        return await cursor.fetchone()

async def add_day_off(user_id: int, date: str, type_: str):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT OR REPLACE INTO days_off (user_id, date, type) VALUES (?,?,?)", (user_id, date, type_))
        await db.commit()

async def get_days_off(user_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT date, type FROM days_off WHERE user_id=? ORDER BY date", (user_id,))
        return await cursor.fetchall()

async def delete_day_off(user_id: int, date: str):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM days_off WHERE user_id=? AND date=?", (user_id, date))
        await db.commit()