import os
import logging
import sqlite3
import time
import random
import string
from threading import Thread
from flask import Flask
from telebot import TeleBot, types
from dotenv import load_dotenv

# ==================== КОНФІГУРАЦІЯ ====================
load_dotenv()

# Виправляємо отримання змінних оточення
BOT_TOKEN = os.getenv("BOT_TOKEN", "7933326437:AAHoqJ91uRle8l4KhNlyGjaMURo1JdP2Ssk")
ADMIN_ID = int(os.getenv("ADMIN_ID", "984209612"))
FLASK_PORT = int(os.getenv("PORT", 8080))

# Налаштування логування
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Ініціалізація бота
bot = TeleBot(BOT_TOKEN, parse_mode="HTML")

# ==================== БАЗА ДАНИХ ====================
def init_db():
    """Ініціалізація бази даних SQLite"""
    with sqlite3.connect('users.db', check_same_thread=False) as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS users
                     (user_id INTEGER PRIMARY KEY,
                     username TEXT,
                     first_name TEXT,
                     last_name TEXT,
                     registration_date TEXT)''')

        conn.execute('''CREATE TABLE IF NOT EXISTS messages
                     (message_id INTEGER PRIMARY KEY AUTOINCREMENT,
                     user_id INTEGER,
                     anon_id TEXT,
                     content_type TEXT,
                     content TEXT,
                     admin_response TEXT,
                     status TEXT DEFAULT 'pending',
                     timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                     FOREIGN KEY(user_id) REFERENCES users(user_id))''')

        conn.execute('''CREATE TABLE IF NOT EXISTS banned_users
                     (user_id INTEGER PRIMARY KEY,
                     reason TEXT,
                     timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')

# ==================== ДОПОМІЖНІ ФУНКЦІЇ ====================
def generate_anon_id():
    """Генерація унікального анонімного ID"""
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))

def is_user_banned(user_id):
    """Перевірка чи користувач заблокований"""
    with sqlite3.connect('users.db') as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM banned_users WHERE user_id=?", (user_id,))
        return cursor.fetchone() is not None

def register_user(user):
    """Реєстрація нового користувача"""
    with sqlite3.connect('users.db') as conn:
        conn.execute(
            "INSERT OR IGNORE INTO users VALUES (?, ?, ?, ?, ?)",
            (user.id, user.username, user.first_name, user.last_name, time.strftime('%Y-%m-%d %H:%M:%S'))
        )

# ==================== ОБРОБКА ПОВІДОМЛЕНЬ ====================
def send_to_admin(message, anon_id):
    """Надсилання повідомлення адміну"""
    try:
        user = message.from_user
        user_info = (
            f"👤 <b>Користувач</b>:\n"
            f"🆔 ID: {user.id}\n"
            f"👤 Ім'я: {user.first_name or 'Немає'}\n"
            f"📛 Прізвище: {user.last_name or 'Немає'}\n"
            f"🔗 @{user.username or 'Немає'}\n"
            f"📅 Час: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"🆔 Анонімний ID: <code>#{anon_id}</code>"
        )

        # Обробка різних типів контенту
        content_handlers = {
            'text': lambda: bot.send_message(ADMIN_ID, f"📄 <b>Текст:</b>\n{message.text}\n\n{user_info}"),
            'photo': lambda: bot.send_photo(ADMIN_ID, message.photo[-1].file_id, 
                                         caption=f"📷 <b>Фото</b>\n\n{user_info}" + 
                                         (f"\n\n✏️ <b>Підпис:</b> {message.caption}" if message.caption else "")),
            'video': lambda: bot.send_video(ADMIN_ID, message.video.file_id,
                                         caption=f"🎬 <b>Відео</b>\n\n{user_info}" + 
                                         (f"\n\n✏️ <b>Підпис:</b> {message.caption}" if message.caption else "")),
            'document': lambda: bot.send_document(ADMIN_ID, message.document.file_id,
                                               caption=f"📎 <b>Файл:</b> {message.document.file_name}\n\n{user_info}")
        }

        if message.content_type in content_handlers:
            content_handlers[message.content_type]()
        else:
            bot.send_message(ADMIN_ID, f"❌ Невідомий тип контенту: {message.content_type}\n\n{user_info}")

        # Кнопки дій для адміна
        markup = types.InlineKeyboardMarkup()
        markup.row(
            types.InlineKeyboardButton("💬 Відповісти", callback_data=f"reply_{anon_id}"),
            types.InlineKeyboardButton("⛔ Заблокувати", callback_data=f"ban_{user.id}")
        )
        markup.row(
            types.InlineKeyboardButton("✅ Позначити як оброблене", callback_data=f"done_{anon_id}")
        )
        bot.send_message(ADMIN_ID, "🔹 Оберіть дію:", reply_markup=markup)

    except Exception as e:
        logger.error(f"Помилка send_to_admin: {e}")
        bot.send_message(ADMIN_ID, f"❌ Помилка: {str(e)[:200]}")

# ==================== КОМАНДИ БОТА ====================
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    """Обробка команди /start"""
    register_user(message.from_user)

    if is_user_banned(message.from_user.id):
        bot.send_message(message.chat.id, "🚫 Ви заблоковані у цьому боті!")
        return

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(
        types.KeyboardButton('📢 Написати анонімно'),
        types.KeyboardButton('📩 Зв\'язатись з адміном'),
        types.KeyboardButton('ℹ️ Допомога')
    )

    bot.send_message(
        message.chat.id,
        "🔒 <b>Анонімний чат-бот</b>\n\n"
        "Ви можете надіслати повідомлення адміністратору анонімно або зв'язатись напряму.\n\n"
        "Оберіть опцію з меню нижче:",
        reply_markup=markup
    )

@bot.message_handler(func=lambda m: m.text == 'ℹ️ Допомога')
def show_help(message):
    """Показати довідку"""
    bot.send_message(
        message.chat.id,
        "ℹ️ <b>Довідка по боту</b>\n\n"
        "📢 <b>Написати анонімно</b> - надіслати повідомлення, яке побачить тільки адміністратор\n"
        "📩 <b>Зв'язатись з адміном</b> - надіслати повідомлення від вашого імені\n\n"
        "Адміністратор може відповісти на ваше повідомлення, і ви отримаєте сповіщення."
    )

@bot.message_handler(func=lambda m: m.text == '📢 Написати анонімно')
def request_anonymous_message(message):
    """Запит анонімного повідомлення"""
    if is_user_banned(message.from_user.id):
        bot.send_message(message.chat.id, "🚫 Ви заблоковані!")
        return

    msg = bot.send_message(
        message.chat.id,
        "✏️ <b>Надішліть ваше анонімне повідомлення:</b>\n\n"
        "Можна надсилати:\n"
        "- Текст\n"
        "- Фото\n"
        "- Відео\n"
        "- Документи\n\n"
        "❗ Ваша особиста інформація не буде видна адміністратору",
        reply_markup=types.ReplyKeyboardRemove()
    )
    bot.register_next_step_handler(msg, process_anonymous_message)

def process_anonymous_message(message):
    """Обробка анонімного повідомлення"""
    try:
        if is_user_banned(message.from_user.id):
            bot.send_message(message.chat.id, "🚫 Ви заблоковані!")
            return

        anon_id = generate_anon_id()

        with sqlite3.connect('users.db') as conn:
            # Зберігаємо повідомлення в базу даних
            conn.execute(
                '''INSERT INTO messages 
                (user_id, anon_id, content_type, content) 
                VALUES (?, ?, ?, ?)''',
                (message.from_user.id, anon_id, message.content_type, 
                 message.text or message.caption or message.document.file_name if hasattr(message, 'document') else '')
            )

            # Надсилаємо адміну
            send_to_admin(message, anon_id)

            # Підтвердження користувачу
            bot.send_message(
                message.chat.id,
                "✅ <b>Ваше повідомлення відправлено адміністратору!</b>\n\n"
                f"🆔 Ваш анонімний ID: <code>#{anon_id}</code>\n"
                "Ви отримаєте сповіщення, коли адміністратор відповість.",
                reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add(
                    types.KeyboardButton('📢 Написати анонімно'),
                    types.KeyboardButton('📩 Зв\'язатись з адміном')
                )
            )

    except Exception as e:
        logger.error(f"Помилка process_anonymous_message: {e}")
        bot.send_message(
            message.chat.id,
            "❌ <b>Сталася помилка при обробці вашого повідомлення</b>\n"
            "Будь ласка, спробуйте ще раз пізніше."
        )

# ==================== CALLBACK ОБРОБНИКИ ====================
@bot.callback_query_handler(func=lambda call: call.data.startswith('reply_'))
def handle_reply(call):
    """Обробка кнопки відповіді"""
    anon_id = call.data.split('_')[1]
    bot.answer_callback_query(call.id, f"Відповідь для #{anon_id}")

    msg = bot.send_message(
        ADMIN_ID,
        f"✍️ <b>Напишіть відповідь для аноніма #{anon_id}:</b>\n\n"
        "Ви можете використовувати текст, фото або інші типи повідомлень."
    )
    bot.register_next_step_handler(msg, lambda m: send_reply(m, anon_id))

def send_reply(message, anon_id):
    """Надсилання відповіді користувачу"""
    try:
        with sqlite3.connect('users.db') as conn:
            # Отримуємо інформацію про оригінальне повідомлення
            cursor = conn.cursor()
            cursor.execute(
                '''SELECT user_id FROM messages 
                WHERE anon_id=? AND status='pending' 
                ORDER BY timestamp DESC LIMIT 1''',
                (anon_id,)
            )
            result = cursor.fetchone()

            if result:
                user_id = result[0]

                # Відправляємо відповідь користувачу
                reply_text = (
                    f"📩 <b>Ви отримали відповідь від адміністратора!</b>\n\n"
                    f"🆔 Анонімний ID: <code>#{anon_id}</code>\n\n"
                )

                if message.content_type == 'text':
                    bot.send_message(user_id, reply_text + message.text)
                elif message.content_type == 'photo':
                    bot.send_photo(user_id, message.photo[-1].file_id, 
                                 caption=reply_text + (message.caption or ""))
                elif message.content_type == 'document':
                    bot.send_document(user_id, message.document.file_id, 
                                    caption=reply_text + (message.caption or ""))

                # Оновлюємо статус повідомлення
                conn.execute(
                    "UPDATE messages SET status='replied', admin_response=? WHERE anon_id=?",
                    (message.text or message.caption or "", anon_id)
                )

                bot.send_message(ADMIN_ID, f"✅ Відповідь для #{anon_id} успішно відправлена!")
            else:
                bot.send_message(ADMIN_ID, f"❌ Не знайдено активного повідомлення з ID #{anon_id}")

    except Exception as e:
        logger.error(f"Помилка send_reply: {e}")
        bot.send_message(ADMIN_ID, f"❌ Помилка при відправці відповіді: {str(e)[:200]}")

@bot.callback_query_handler(func=lambda call: call.data.startswith('ban_'))
def handle_ban(call):
    """Обробка бана користувача"""
    user_id = int(call.data.split('_')[1])

    try:
        with sqlite3.connect('users.db') as conn:
            # Додаємо користувача до чорного списку
            conn.execute(
                "INSERT OR IGNORE INTO banned_users (user_id, reason) VALUES (?, ?)",
                (user_id, "Бан через адмін-панель")
            )

            # Позначаємо всі його повідомлення як заблоковані
            conn.execute(
                "UPDATE messages SET status='banned' WHERE user_id=?",
                (user_id,)
            )

            bot.answer_callback_query(call.id, "Користувача заблоковано!")
            bot.send_message(
                ADMIN_ID,
                f"⛔ <b>Користувач {user_id} був заблокований</b>\n\n"
                "Всі його повідомлення позначені як заблоковані."
            )

    except Exception as e:
        logger.error(f"Помилка handle_ban: {e}")
        bot.answer_callback_query(call.id, "❌ Помилка при блокуванні!")

@bot.callback_query_handler(func=lambda call: call.data.startswith('done_'))
def handle_done(call):
    """Позначення повідомлення як обробленого"""
    anon_id = call.data.split('_')[1]

    try:
        with sqlite3.connect('users.db') as conn:
            conn.execute(
                "UPDATE messages SET status='done' WHERE anon_id=?",
                (anon_id,)
            )

            bot.answer_callback_query(call.id, "Позначено як оброблене!")
            bot.send_message(
                ADMIN_ID,
                f"✅ Повідомлення #{anon_id} позначено як оброблене"
            )

    except Exception as e:
        logger.error(f"Помилка handle_done: {e}")
        bot.answer_callback_query(call.id, "❌ Помилка при обробці!")

# ==================== FLASK ДЛЯ ЖИВУЧОСТІ ====================
app = Flask(__name__)

@app.route('/')
def home():
    return "Telegram Bot is Alive and Running! 🤖"

@app.route('/health')
def health():
    return "OK", 200

def run_flask():
    app.run(host='0.0.0.0', port=FLASK_PORT)

def keep_alive():
    Thread(target=run_flask, daemon=True).start()

# ==================== ЗАПУСК БОТА ====================
if __name__ == '__main__':
    # Ініціалізація бази даних
    init_db()

    # Запуск Flask у фоновому режимі
    keep_alive()

    logger.info("Бот запускається...")
    
    try:
        bot.send_message(ADMIN_ID, "🤖 Бот успішно запущений!")
    except Exception as e:
        logger.warning(f"Не вдалося надіслати повідомлення адміну: {e}")

    # Основний цикл роботи бота
    while True:
        try:
            logger.info("Початок polling...")
            bot.polling(none_stop=True, interval=2, timeout=60)
        except Exception as e:
            logger.error(f"Помилка polling: {e}")
            time.sleep(15)  # Збільшено інтервал перезапуску
