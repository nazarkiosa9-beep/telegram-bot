import asyncio
import re
import sqlite3
from datetime import datetime
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

BOT_TOKEN = "7940416086:AAEZQX6nogPQ8BVDqt-W2jHRd0_01KCxxFA"  # впиши свій токен від BotFather
ADMIN_IDS = {1029644905}  # впиши свій Telegram ID

# Пакети UC. Ціну ти виставиш сам: UAH/PLN можна зберігати окремо
UC_PACKS = [60, 325, 660, 1800, 3850, 8100, 16200]
PRICES_UA = {60: 50, 325: 210, 660: 420, 1800: 1050, 3850: 2100, 8100: 4200, 16200: 8400}

CARD_PAYMENT_TEXT_UA =(
"💳 Оплата переказом на карту\n\n"
"Реквізити:\n"
"• Номер карти: 4149 4390 2793 9093\n\n"
"📝 Важливо: у коментарі вкажи код замовлення: {order_id}\n"
"Після оплати надішли сюди *скрін/квитанцію* (фото або файл)."
)

SUPPORT_TEXT = "Підтримка: напиши @CHILI_pubg якщо виникла проблема."

DB_PATH = "bot.db"

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = db()
    cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tg_id INTEGER UNIQUE,
        username TEXT,
        created_at TEXT
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS orders(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tg_id INTEGER,
        uc_pack INTEGER,
        country TEXT,
        currency TEXT,
        amount REAL,
        player_id TEXT,
        status TEXT,
        created_at TEXT
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS payments(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id INTEGER,
        method TEXT,
        proof_file_id TEXT,
        created_at TEXT
    )""")
    conn.commit()
    conn.close()

def upsert_user(tg_id: int, username: str | None):
    conn = db()
    cur = conn.cursor()
    cur.execute(
        "INSERT OR IGNORE INTO users(tg_id, username, created_at) VALUES(?,?,?)",
        (tg_id, username, datetime.utcnow().isoformat())
    )
    conn.commit()
    conn.close()

def create_order(tg_id: int, uc_pack: int, country: str, currency: str, amount: float, player_id: str) -> int:
    conn = db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO orders(tg_id, uc_pack, country, currency, amount, player_id, status, created_at) "
        "VALUES(?,?,?,?,?,?,?,?)",
        (tg_id, uc_pack, country, currency, amount, player_id, "WAIT_PAY", datetime.utcnow().isoformat())
    )
    order_id = cur.lastrowid
    conn.commit()
    conn.close()
    return order_id

def set_order_status(order_id: int, status: str):
    conn = db()
    cur = conn.cursor()
    cur.execute("UPDATE orders SET status=? WHERE id=?", (status, order_id))
    conn.commit()
    conn.close()

def add_payment_proof(order_id: int, method: str, file_id: str):
    conn = db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO payments(order_id, method, proof_file_id, created_at) VALUES(?,?,?,?)",
        (order_id, method, file_id, datetime.utcnow().isoformat())
    )
    # статус на перевірку
    cur.execute("UPDATE orders SET status=? WHERE id=?", ("PAID_CHECK", order_id))
    conn.commit()
    conn.close()

def get_user_orders(tg_id: int, limit: int = 10):
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM orders WHERE tg_id=? ORDER BY id DESC LIMIT ?", (tg_id, limit))
    rows = cur.fetchall()
    conn.close()
    return rows

def get_order(order_id: int):
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM orders WHERE id=?", (order_id,))
    row = cur.fetchone()
    conn.close()
    return row

def admin_new_orders(limit: int = 20):
    conn = db()
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM orders WHERE status IN ('WAIT_PAY','PAID_CHECK','IN_PROGRESS') ORDER BY id DESC LIMIT ?",
        (limit,)
    )
    rows = cur.fetchall()
    conn.close()
    return rows

    async def start(message: Message):
        await message.answer(
            "Привіт! Я готовий до роботи.",
            reply_markup=main_menu_kb()
        )
# --- Клавіатури ---
def main_menu_kb():
    kb = ReplyKeyboardBuilder()
    kb.button(text="🛒 Купити UC")
    kb.button(text="📦 Мої замовлення")
    kb.button(text="❓ Підтримка")
    kb.button(text="📜 Правила")
    kb.adjust(2, 2)
    return kb.as_markup(resize_keyboard=True)

def uc_packs_kb():
    kb = InlineKeyboardBuilder()
    for pack in UC_PACKS:
        kb.button(text=f"{pack} UC", callback_data=f"pack:{pack}")
    kb.adjust(2)
    return kb.as_markup()

def country_kb(pack: int):
    kb = InlineKeyboardBuilder()
    kb.button(text="🇺🇦 Україна (UAH)", callback_data=f"country:UA:{pack}")
    kb.adjust(1)
    return kb.as_markup()

def pay_method_kb(order_id: int):
    kb = InlineKeyboardBuilder()
    kb.button(text="💳 Переказ на карту", callback_data=f"pay:card:{order_id}")
    kb.button(text="🍏 Apple Pay (скоро)", callback_data=f"pay:applepay:{order_id}")
    kb.adjust(1)
    return kb.as_markup()

def admin_order_kb(order_id: int):
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Оплачено", callback_data=f"adm:PAID_CHECK:{order_id}")
    kb.button(text="🚚 В обробці", callback_data=f"adm:IN_PROGRESS:{order_id}")
    kb.button(text="🎉 Виконано", callback_data=f"adm:DONE:{order_id}")
    kb.button(text="❌ Скасувати", callback_data=f"adm:CANCELLED:{order_id}")
    kb.adjust(2, 2)
    return kb.as_markup()

# --- Валідація ---
PLAYER_ID_RE = re.compile(r"^\d{6,20}$")  # підлаштуєш під свій формат

# Тимчасове сховище стану без FSM (для старту)
PENDING_PLAYER_ID = {}   # tg_id -> (pack, country, currency, amount)
PENDING_PROOF_FOR_ORDER = {}  # tg_id -> order_id

# --- Хендлери ---
async def start(m: Message):
    upsert_user(m.from_user.id, m.from_user.username)
    await m.answer("Привіт! Обери дію 👇", reply_markup=main_menu_kb())

async def buy(m: Message):
    await m.answer("Обери пакет UC:", reply_markup=uc_packs_kb())

async def my_orders(m: Message):
    rows = get_user_orders(m.from_user.id, limit=10)
    if not rows:
        await m.answer("У тебе поки немає замовлень.")
        return
    lines = ["📦 Твої замовлення (останні 10):\n"]
    for r in rows:
        lines.append(
            f"#{r['id']} • {r['uc_pack']} UC • {r['amount']} {r['currency']} • {r['status']} • PlayerID: {r['player_id']}"
        )
    await m.answer("\n".join(lines))

async def rules(m: Message):
    await m.answer(
        "📜 Правила:\n"
        "1) Вводь правильний Player ID.\n"
        "2) Після оплати надішли квитанцію.\n"
        "3) Час виконання: зазвичай 5–60 хв.\n"
        "4) Повернення можливе, якщо поповнення ще не виконано.\n"
    )

async def support(m: Message):
    await m.answer(SUPPORT_TEXT)

async def on_pack(c: CallbackQuery):
    pack = int(c.data.split(":")[1])
    price = PRICES_UA.get(pack)  # заглушка: заміни на реальний прайс
        
    if price is None:
        await c.answer("Помилка ціни для цього пакета. Спробуй інший.", show_alert=True)
        return
        
    await c.message.edit_text(
            f"📦 Пакет {pack} UC\n"
            f"Ціна: {price} UAH\n\n"
            f"обери країну/валюту:",
            reply_markup=country_kb(pack)
    )
    await c.answer()

    await c.message.edit_text("Обери країну/валюту:", reply_markup=country_kb(pack))
    await c.answer()

async def on_country(c: CallbackQuery):
    _, country, pack_s = c.data.split(":")
    pack = int(pack_s)

    # TODO: тут підстав свої реальні ціни:
    if country == "UA":
        currency = "UAH"
        amount = float(PRICES_UA.get(pack, 0))  # заглушка: заміни на прайс
    else:
        currency = "PLN"
        amount = PRICES_UA.get(pack)  # заглушка: заміни на прайс

    PENDING_PLAYER_ID[c.from_user.id] = (pack, country, currency, amount)
    await c.message.edit_text(
        f"Введи Player ID (тільки цифри).\n\nОбрано: {pack} UC • {amount} {currency}"
    )
    await c.answer()

async def on_player_id(m: Message):
    print("TEXT:", m.text, "USER:", m.from_user.id)
    print("PENDING keys:", list(PENDING_PLAYER_ID.keys())[:10])

    if m.from_user.id not in PENDING_PLAYER_ID:
        return

    player_id = m.text.strip()
    if not PLAYER_ID_RE.match(player_id):
        await m.answer("❌ Player ID виглядає некоректно. Спробуй ще раз (6–20 цифр).")
        return

    pack, country, currency, amount = PENDING_PLAYER_ID.pop(m.from_user.id)
    order_id = create_order(m.from_user.id, pack, country, currency, amount, player_id)

    await m.answer(
        f"✅ Замовлення створено: #{order_id}\n"
        f"{pack} UC • {amount} {currency}\n"
        f"Player ID: {player_id}\n\n"
        "Обери спосіб оплати:",
        reply_markup=pay_method_kb(order_id)
    )

async def on_pay_method(c: CallbackQuery):
    _, method, order_id_s = c.data.split(":")
    order_id = int(order_id_s)

    order = get_order(order_id)
    if not order or order["tg_id"] != c.from_user.id:
        await c.answer("Замовлення не знайдено.", show_alert=True)
        return

    if method == "card":
        PENDING_PROOF_FOR_ORDER[c.from_user.id] = order_id
        await c.message.edit_text(CARD_PAYMENT_TEXT_UA.format(order_id=order_id), parse_mode="Markdown")
        await c.answer()
        return

    # Apple Pay: на старті як “скоро”
    await c.answer("Apple Pay підключимо наступним кроком ✅", show_alert=True)

async def on_proof(m: Message, bot: Bot):
    """Приймаємо фото або документ як підтвердження оплати."""
    if m.from_user.id not in PENDING_PROOF_FOR_ORDER:
        return

    order_id = PENDING_PROOF_FOR_ORDER.pop(m.from_user.id)

    file_id = None
    if m.photo:
        file_id = m.photo[-1].file_id
    elif m.document:
        file_id = m.document.file_id

    if not file_id:
        await m.answer("Надішли, будь ласка, фото або файл квитанції.")
        return

    add_payment_proof(order_id, "card_transfer", file_id)
    await m.answer("✅ Дякую! Оплату отримано на перевірку. Я підтверджу і виконаю поповнення.")
    # Пінг адмінам
    order = get_order(order_id)
    for admin_id in ADMIN_IDS:
        await bot.send_message(
            admin_id,
            f"🆕 Квитанція по замовленню #{order_id}\n"
            f"{order['uc_pack']} UC • {order['amount']} {order['currency']}\n"
            f"Player ID: {order['player_id']}\n"
            f"User: @{m.from_user.username} (id {m.from_user.id})",
            reply_markup=admin_order_kb(order_id)
        )
        await bot.send_photo(admin_id, file_id)

async def admin_list(m: Message):
    if m.from_user.id not in ADMIN_IDS:
        return
    rows = admin_new_orders(limit=20)
    if not rows:
        await m.answer("Немає активних замовлень.")
        return
    lines = ["🧾 Активні замовлення:\n"]
    for r in rows:
        lines.append(f"#{r['id']} • {r['uc_pack']} UC • {r['amount']} {r['currency']} • {r['status']} • PlayerID {r['player_id']}")
    await m.answer("\n".join(lines))

async def admin_set_status(c: CallbackQuery, bot: Bot):
    if c.from_user.id not in ADMIN_IDS:
        await c.answer("Нема доступу.", show_alert=True)
        return
    _, status, order_id_s = c.data.split(":")
    order_id = int(order_id_s)
    order = get_order(order_id)
    if not order:
        await c.answer("Замовлення не знайдено.", show_alert=True)
        return

    set_order_status(order_id, status)
    await c.answer("Ок ✅")

    # Нотифікація юзеру
    status_text = {
        "PAID_CHECK": "✅ Оплату підтверджено. Починаю виконання.",
        "IN_PROGRESS": "🚚 В обробці. Скоро поповню.",
        "DONE": "🎉 Виконано! UC має надійти на акаунт. Дякую!",
        "CANCELLED": "❌ Замовлення скасовано. Напиши в підтримку, якщо є питання."
    }.get(status, f"Статус оновлено: {status}")

    await bot.send_message(order["tg_id"], f"Замовлення #{order_id}: {status_text}")

    # Оновимо повідомлення адміна
    await c.message.edit_text(
        f"Замовлення #{order_id}\n"
        f"{order['uc_pack']} UC • {order['amount']} {order['currency']}\n"
        f"Player ID: {order['player_id']}\n"
        f"Новий статус: {status}"
    )

async def main():
    init_db()
    print("Db ok")

    bot = Bot(BOT_TOKEN)
    print("Bot ok")

    dp = Dispatcher()
    print("Dispatcher ok")

    # ... реєстрація хендлерів
    
    dp.message.register(start, CommandStart())
    dp.message.register(buy, F.text == "🛒 Купити UC")
    dp.message.register(my_orders, F.text == "📦 Мої замовлення")
    dp.message.register(support, F.text == "❓ Підтримка")
    dp.message.register(rules, F.text == "📜 Правила")

    dp.callback_query.register(on_pack, F.data.startswith("pack:"))
    dp.callback_query.register(on_country, F.data.startswith("country:"))
    dp.callback_query.register(on_pay_method, F.data.startswith("pay:"))
    dp.callback_query.register(admin_set_status, F.data.startswith("adm:"))

    dp.message.register(admin_list, F.text == "/admin")
    dp.message.register(on_proof, F.photo | F.document)
    dp.message.register(on_player_id, F.text)  # після вибору пакета і країни
    
    print("start polling...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
