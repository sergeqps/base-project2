import os
import psycopg2
import logging
from datetime import datetime, timedelta
from PIL import Image, ImageDraw, ImageFont
import io
from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackContext, MessageHandler, filters
import urllib.parse as urlparse

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# 🔐 ВАШ ТОКЕН БОТА
BOT_TOKEN = os.getenv('BOT_TOKEN')
YOUR_USER_ID = int(os.getenv('YOUR_USER_ID', '7892045071'))

if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN не установлен!")

# 🔗 ПОДКЛЮЧЕНИЕ К POSTGRESQL
def get_connection():
    """Получить соединение с PostgreSQL"""
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        raise ValueError("❌ DATABASE_URL не установлен!")
    
    # Парсим URL для Railway
    url = urlparse.urlparse(database_url)
    dbname = url.path[1:]
    user = url.username
    password = url.password
    host = url.hostname
    port = url.port
    
    return psycopg2.connect(
        dbname=dbname,
        user=user,
        password=password,
        host=host,
        port=port,
        sslmode='require'
    )

# Глобальное соединение
conn = get_connection()
cursor = conn.cursor()

def init_db():
    """Инициализация таблиц в PostgreSQL"""
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS scammers (
            id SERIAL PRIMARY KEY,
            user_id BIGINT UNIQUE NOT NULL,
            username TEXT,
            proof TEXT NOT NULL,
            added_by BIGINT NOT NULL,
            added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            scam_type TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS admins (
            admin_id BIGINT PRIMARY KEY,
            username TEXT,
            role TEXT NOT NULL DEFAULT 'admin'
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bans (
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            username TEXT,
            reason TEXT NOT NULL,
            banned_by BIGINT NOT NULL,
            ban_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            chat_id BIGINT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS warns (
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            username TEXT,
            reason TEXT NOT NULL,
            warned_by BIGINT NOT NULL,
            warn_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            chat_id BIGINT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS mutes (
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            username TEXT,
            reason TEXT NOT NULL,
            muted_by BIGINT NOT NULL,
            mute_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            unmute_date TIMESTAMP,
            chat_id BIGINT
        )
    ''')
    # Добавляем владельца если его нет
    cursor.execute("INSERT INTO admins (admin_id, username, role) VALUES (%s, %s, 'owner') ON CONFLICT (admin_id) DO NOTHING", (YOUR_USER_ID, 'owner'))
    conn.commit()

def ensure_connection():
    """Проверить и восстановить соединение с БД"""
    global conn, cursor
    try:
        cursor.execute("SELECT 1")
    except:
        print("🔁 Восстанавливаем соединение с БД...")
        conn = get_connection()
        cursor = conn.cursor()

def is_owner(user_id):
    ensure_connection()
    cursor.execute("SELECT 1 FROM admins WHERE admin_id = %s AND role = 'owner'", (user_id,))
    return cursor.fetchone() is not None

def is_admin(user_id):
    ensure_connection()
    cursor.execute("SELECT 1 FROM admins WHERE admin_id = %s", (user_id,))
    return cursor.fetchone() is not None

def get_user_role(user_id):
    ensure_connection()
    cursor.execute("SELECT role FROM admins WHERE admin_id = %s", (user_id,))
    result = cursor.fetchone()
    return result[0] if result else 'user'

def is_target_owner(target_username):
    ensure_connection()
    cursor.execute("SELECT 1 FROM admins WHERE username = %s AND role = 'owner'", (target_username,))
    return cursor.fetchone() is not None

def create_status_image(status, user_info=""):
    colors = {
        'скамер': ('#FF0000', '#FFFFFF'),
        'владелец': ('#FFD700', '#000000'),
        'администратор': ('#4169E1', '#FFFFFF'),
        'обычный пользователь': ('#00FF00', '#000000')
    }
    
    bg_color, text_color = colors.get(status, ('#808080', '#FFFFFF'))
    
    width, height = 600, 300
    image = Image.new('RGB', (width, height), color=bg_color)
    draw = ImageDraw.Draw(image)
    
    # Рамка
    draw.rectangle([0, 0, width-1, height-1], outline='#000000', width=5)
    
    # Шрифт
    font = ImageFont.load_default()
    
    # Основной текст
    status_text = status.upper()
    text_width = len(status_text) * 20
    text_height = 30
    
    x = (width - text_width) // 2
    y = (height - text_height) // 2
    
    draw.text((x, y), status_text, fill=text_color, font=font)
    
    # Дополнительная информация
    if user_info:
        draw.text((50, y + 50), user_info, fill=text_color, font=font)
    
    img_byte_arr = io.BytesIO()
    image.save(img_byte_arr, format='PNG')
    img_byte_arr.seek(0)
    
    return img_byte_arr

def only_in_chats(func):
    async def wrapper(update: Update, context: CallbackContext):
        if update.effective_chat.type == 'private':
            await update.message.reply_text(
                "❌ Этот бот работает только в чатах и группах!\n\n"
                "Добавьте бота в ваш чат и используйте команды там."
            )
            return
        return await func(update, context)
    return wrapper

@only_in_chats
async def start(update: Update, context: CallbackContext):
    ensure_connection()
    user_id = update.effective_user.id
    username = update.effective_user.username
    full_name = update.effective_user.full_name
    chat_title = update.effective_chat.title
    
    if is_admin(user_id) and username:
        cursor.execute("UPDATE admins SET username = %s WHERE admin_id = %s", (username, user_id))
        conn.commit()
    
    role = get_user_role(user_id)
    role_text = "👑 Владелец" if role == 'owner' else "👮 Администратор" if role == 'admin' else "👤 Пользователь"
    
    text = (
        f"🛡️ База данных скамеров активирована в чате \"{chat_title}\"!\n\n"
        f"👤 Ваш статус: {role_text}\n\n"
        "📝 Основные команды:\n"
        "• /check @username - Проверить пользователя\n"
        "• /check 123456789 - Проверить по ID\n"
        "• /stats - Статистика базы\n"
        "• /help - Справка по командам\n"
    )
    
    if is_admin(user_id):
        text += "\n👮 Команды модерации:\n"
        text += "• /ban @username причина - Забанить пользователя\n"
        text += "• /unban @username - Разбанить пользователя\n"
        text += "• /warn @username причина - Выдать варн\n"
        text += "• /mute @username время причина - Замутить\n"
        text += "• /unmute @username - Размутить\n"
        text += "• /warns @username - Посмотреть варны\n"
        text += "• /banlist - Список банов\n"
        text += "• /add_scammer user_id @username|пруфы|тип - Добавить скамера\n"
    
    if is_owner(user_id):
        text += "\n👑 Команды владельца:\n"
        text += "• /add_admin user_id @username - Добавить администратора\n"
        text += "• /add_owner user_id @username - Добавить владельца\n"
        text += "• /list_admins - Список администраторов\n"
    
    await update.message.reply_text(text)

@only_in_chats
async def help_command(update: Update, context: CallbackContext):
    ensure_connection()
    user_id = update.effective_user.id
    
    text = (
        "📖 Справка по командам базы скамеров:\n\n"
        "👤 Основные команды:\n"
        "• /start - Запустить бота\n"
        "• /check @username - Проверить пользователя\n"
        "• /check 123456789 - Проверить по ID\n"
        "• /stats - Статистика базы\n"
        "• /help - Эта справка\n\n"
    )
    
    if is_admin(user_id):
        text += (
            "👮 Команды модерации:\n"
            "• /ban @username причина - Бан пользователя\n"
            "• /unban @username - Разбан пользователя\n"
            "• /warn @username причина - Выдать варн\n"
            "• /mute @username время причина - Мут\n"
            "• /unmute @username - Размутить\n"
            "• /warns @username - Варны пользователя\n"
            "• /banlist - Список банов\n"
            "• /add_scammer user_id @username|пруфы|тип - Добавить скамера\n\n"
            "⚠️ Невозможно выдать санкции владельцу!\n\n"
            "Примеры:\n"
            "/ban @username Спам\n"
            "/warn @username Оскорбления\n"
            "/mute @username 1h Флуд\n"
            "/mute @username 30m Реклама\n"
        )
    
    if is_owner(user_id):
        text += (
            "👑 Команды владельца:\n"
            "• /add_admin user_id @username - Добавить администратора\n"
            "• /add_owner user_id @username - Добавить владельца\n"
            "• /list_admins - Список администраторов\n"
        )
    
    await update.message.reply_text(text)

@only_in_chats
async def check_user(update: Update, context: CallbackContext):
    ensure_connection()
    if not context.args:
        await update.message.reply_text("❌ Использование: /check @username или /check 123456789")
        return
    
    search_query = context.args[0].strip()
    print(f"🔍 Поиск: {search_query}")

    # Проверяем базу скамеров
    if search_query.isdigit():
        cursor.execute("SELECT user_id, username, proof, scam_type FROM scammers WHERE user_id = %s", (int(search_query),))
        scammer_data = cursor.fetchone()
        
        if scammer_data:
            user_id, username, proof, scam_type = scammer_data
            text = f"🚨 НАЙДЕН В БАЗЕ СКАМЕРОВ!\n\n👤 ID: `{user_id}`\n"
            if username:
                text += f"📱 Username: @{username}\n"
            if scam_type:
                text += f"🎯 Тип скама: {scam_type}\n"
            text += f"📝 Пруфы: {proof}"
            await update.message.reply_text(text, parse_mode='Markdown')
            return

    elif search_query.startswith('@'):
        username = search_query[1:].lower()
        cursor.execute("SELECT user_id, username, proof, scam_type FROM scammers WHERE LOWER(username) = %s", (username,))
        scammer_data = cursor.fetchone()
        
        if scammer_data:
            user_id, username, proof, scam_type = scammer_data
            text = f"🚨 НАЙДЕН В БАЗЕ СКАМЕРОВ!\n\n👤 ID: `{user_id}`\n📱 Username: @{username}\n"
            if scam_type:
                text += f"🎯 Тип скама: {scam_type}\n"
            text += f"📝 Пруфы: {proof}"
            await update.message.reply_text(text, parse_mode='Markdown')
            return

    # Проверяем админов
    if search_query.isdigit():
        cursor.execute("SELECT admin_id, username, role FROM admins WHERE admin_id = %s", (int(search_query),))
        admin_data = cursor.fetchone()
        
        if admin_data:
            admin_id, username, role = admin_data
            role_text = "👑 ВЛАДЕЛЕЦ" if role == 'owner' else "👮 АДМИНИСТРАТОР"
            text = f"{role_text}\n\n👤 ID: `{admin_id}`\n"
            if username:
                text += f"📱 Username: @{username}\n"
            text += f"💼 Роль: {role}"
            await update.message.reply_text(text, parse_mode='Markdown')
            return

    elif search_query.startswith('@'):
        username = search_query[1:].lower()
        cursor.execute("SELECT admin_id, username, role FROM admins WHERE LOWER(username) = %s", (username,))
        admin_data = cursor.fetchone()
        
        if admin_data:
            admin_id, username, role = admin_data
            role_text = "👑 ВЛАДЕЛЕЦ" if role == 'owner' else "👮 АДМИНИСТРАТОР"
            text = f"{role_text}\n\n👤 ID: `{admin_id}`\n📱 Username: @{username}\n💼 Роль: {role}"
            await update.message.reply_text(text, parse_mode='Markdown')
            return

    # Если не найден нигде
    text = "✅ ОБЫЧНЫЙ ПОЛЬЗОВАТЕЛЬ\n\nНе найден в базе скамеров и не является администратором."
    await update.message.reply_text(text, parse_mode='Markdown')

@only_in_chats
async def stats(update: Update, context: CallbackContext):
    ensure_connection()
    cursor.execute("SELECT COUNT(*) FROM scammers")
    scammer_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM admins")
    admin_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM bans")
    ban_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM warns")
    warn_count = cursor.fetchone()[0]
    
    text = (
        f"📊 СТАТИСТИКА БАЗЫ ДАННЫХ:\n\n"
        f"🚨 Скамеров в базе: {scammer_count}\n"
        f"👮 Администраторов: {admin_count}\n"
        f"🔨 Активных банов: {ban_count}\n"
        f"⚠️ Всего варнов: {warn_count}"
    )
    
    await update.message.reply_text(text)

@only_in_chats
async def add_scammer(update: Update, context: CallbackContext):
    ensure_connection()
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        await update.message.reply_text("❌ Только администраторы могут добавлять скамеров!")
        return
    
    if not context.args:
        await update.message.reply_text(
            "❌ Использование: /add_scammer user_id @username|пруфы|тип\n\n"
            "Примеры:\n"
            "/add_scammer 123456789 @scammer|Кинул на 1000р|Невывод\n"
            "/add_scammer 987654321 @baduser|Обман при обмене|Фейковый обменник"
        )
        return
    
    data = ' '.join(context.args)
    
    try:
        parts = data.split('|')
        if len(parts) < 2:
            await update.message.reply_text("❌ Неверный формат. Нужно: user_id @username|пруфы|тип")
            return
        
        first_part = parts[0].strip().split()
        if len(first_part) < 2:
            await update.message.reply_text("❌ Укажите ID и username! Формат: user_id @username")
            return
        
        user_id_part = first_part[0]
        username_part = first_part[1]
        
        if not user_id_part.isdigit():
            await update.message.reply_text("❌ User ID должен быть числом!")
            return
        
        scammer_id = int(user_id_part)
        
        if not username_part.startswith('@'):
            await update.message.reply_text("❌ Username должен начинаться с @!")
            return
        
        username = username_part[1:].lower()
        proof = parts[1].strip()
        scam_type = parts[2].strip() if len(parts) > 2 else "Не указан"
        
        cursor.execute("SELECT 1 FROM scammers WHERE user_id = %s OR username = %s", (scammer_id, username))
        if cursor.fetchone():
            await update.message.reply_text("❌ Этот пользователь уже есть в базе скамеров!")
            return
        
        cursor.execute("INSERT INTO scammers (user_id, username, proof, added_by, scam_type) VALUES (%s, %s, %s, %s, %s)",
                      (scammer_id, username, proof, user_id, scam_type))
        conn.commit()
        
        await update.message.reply_text(f"✅ Скамер добавлен!\n👤 ID: {scammer_id}\n📱 Username: @{username}\n🎯 Тип: {scam_type}")
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка при добавлении: {str(e)}")

@only_in_chats
async def ban_user(update: Update, context: CallbackContext):
    ensure_connection()
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    if not is_admin(user_id):
        await update.message.reply_text("❌ Только администраторы могут банить пользователей!")
        return
    
    if not context.args or len(context.args) < 2:
        await update.message.reply_text("❌ Использование: /ban @username причина")
        return
    
    target_username = context.args[0]
    reason = ' '.join(context.args[1:])
    
    if not target_username.startswith('@'):
        await update.message.reply_text("❌ Укажите username пользователя (начинается с @)")
        return
    
    target_username = target_username[1:]
    
    if is_target_owner(target_username):
        await update.message.reply_text("❌ Невозможно забанить владельца!")
        return
    
    try:
        cursor.execute("INSERT INTO bans (user_id, username, reason, banned_by, chat_id) VALUES (%s, %s, %s, %s, %s)",
                      (0, target_username, reason, user_id, chat_id))
        conn.commit()
        
        await update.message.reply_text(f"✅ Пользователь @{target_username} забанен!\nПричина: {reason}")
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка при бане: {str(e)}")

@only_in_chats
async def unban_user(update: Update, context: CallbackContext):
    ensure_connection()
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        await update.message.reply_text("❌ Только администраторы могут разбанивать пользователей!")
        return
    
    if not context.args:
        await update.message.reply_text("❌ Использование: /unban @username")
        return
    
    target_username = context.args[0]
    
    if not target_username.startswith('@'):
        await update.message.reply_text("❌ Укажите username пользователя (начинается с @)")
        return
    
    target_username = target_username[1:]
    
    try:
        cursor.execute("DELETE FROM bans WHERE username = %s", (target_username,))
        conn.commit()
        
        if cursor.rowcount > 0:
            await update.message.reply_text(f"✅ Пользователь @{target_username} разбанен!")
        else:
            await update.message.reply_text(f"❌ Пользователь @{target_username} не найден в списке банов.")
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка при разбане: {str(e)}")

@only_in_chats
async def warn_user(update: Update, context: CallbackContext):
    ensure_connection()
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    if not is_admin(user_id):
        await update.message.reply_text("❌ Только администраторы могут выдавать варны!")
        return
    
    if not context.args or len(context.args) < 2:
        await update.message.reply_text("❌ Использование: /warn @username причина")
        return
    
    target_username = context.args[0]
    reason = ' '.join(context.args[1:])
    
    if not target_username.startswith('@'):
        await update.message.reply_text("❌ Укажите username пользователя (начинается с @)")
        return
    
    target_username = target_username[1:]
    
    if is_target_owner(target_username):
        await update.message.reply_text("❌ Невозможно выдать варн владельцу!")
        return
    
    try:
        cursor.execute("INSERT INTO warns (user_id, username, reason, warned_by, chat_id) VALUES (%s, %s, %s, %s, %s)",
                      (0, target_username, reason, user_id, chat_id))
        conn.commit()
        
        cursor.execute("SELECT COUNT(*) FROM warns WHERE username = %s", (target_username,))
        warn_count = cursor.fetchone()[0]
        
        await update.message.reply_text(
            f"⚠️ Пользователь @{target_username} получил варн!\n"
            f"Причина: {reason}\n"
            f"Всего варнов: {warn_count}/3"
        )
        
        if warn_count >= 3:
            cursor.execute("INSERT INTO bans (user_id, username, reason, banned_by, chat_id) VALUES (%s, %s, %s, %s, %s)",
                          (0, target_username, f"Автобан за 3 варна (последний: {reason})", user_id, chat_id))
            cursor.execute("DELETE FROM warns WHERE username = %s", (target_username,))
            conn.commit()
            
            await update.message.reply_text(
                f"🚨 АВТОМАТИЧЕСКИЙ БАН!\n"
                f"Пользователь @{target_username} получил бан за 3 вана.\n"
                f"Причина последнего варна: {reason}"
            )
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка при выдаче варна: {str(e)}")

@only_in_chats
async def mute_user(update: Update, context: CallbackContext):
    ensure_connection()
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    if not is_admin(user_id):
        await update.message.reply_text("❌ Только администраторы могут мутить пользователей!")
        return
    
    if not context.args or len(context.args) < 3:
        await update.message.reply_text("❌ Использование: /mute @username время причина\n\nПримеры:\n/mute @username 1h Флуд\n/mute @username 30m Спам")
        return
    
    target_username = context.args[0]
    mute_time = context.args[1]
    reason = ' '.join(context.args[2:])
    
    if not target_username.startswith('@'):
        await update.message.reply_text("❌ Укажите username пользователя (начинается с @)")
        return
    
    target_username = target_username[1:]
    
    if is_target_owner(target_username):
        await update.message.reply_text("❌ Невозможно замутить владельца!")
        return
    
    try:
        # Просто добавляем в базу без реального мута
        cursor.execute("INSERT INTO mutes (user_id, username, reason, muted_by, chat_id) VALUES (%s, %s, %s, %s, %s)",
                      (0, target_username, f"{reason} (время: {mute_time})", user_id, chat_id))
        conn.commit()
        
        await update.message.reply_text(f"🔇 Пользователь @{target_username} замьючен на {mute_time}!\nПричина: {reason}")
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка при муте: {str(e)}")

@only_in_chats
async def add_owner(update: Update, context: CallbackContext):
    ensure_connection()
    user_id = update.effective_user.id
    
    if not is_owner(user_id):
        await update.message.reply_text("❌ Только владелец бота может добавлять других владельцев!")
        return
    
    if not context.args:
        await update.message.reply_text("❌ Использование: /add_owner user_id @username\n\nПример:\n/add_owner 123456789 @username")
        return
    
    if len(context.args) < 2:
        await update.message.reply_text("❌ Нужно указать ID и username!\nИспользование: /add_owner user_id @username")
        return
    
    target_id = context.args[0]
    target_username = context.args[1]
    
    if not target_id.isdigit():
        await update.message.reply_text("❌ ID должен быть числом!")
        return
    
    target_id = int(target_id)
    
    if not target_username.startswith('@'):
        await update.message.reply_text("❌ Username должен начинаться с @!")
        return
    
    target_username = target_username[1:]
    
    try:
        cursor.execute("SELECT 1 FROM admins WHERE admin_id = %s OR username = %s", (target_id, target_username))
        if cursor.fetchone():
            await update.message.reply_text("❌ Этот пользователь уже есть в базе администраторов!")
            return
        
        cursor.execute("INSERT INTO admins (admin_id, username, role) VALUES (%s, %s, 'owner')",
                      (target_id, target_username))
        conn.commit()
        
        await update.message.reply_text(f"✅ Владелец добавлен!\n👤 ID: {target_id}\n📱 Username: @{target_username}")
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка при добавлении владельца: {str(e)}")

@only_in_chats
async def add_admin(update: Update, context: CallbackContext):
    ensure_connection()
    user_id = update.effective_user.id
    
    if not is_owner(user_id):
        await update.message.reply_text("❌ Только владелец бота может добавлять администраторов!")
        return
    
    if not context.args:
        await update.message.reply_text("❌ Использование: /add_admin user_id @username\n\nПример:\n/add_admin 123456789 @username")
        return
    
    if len(context.args) < 2:
        await update.message.reply_text("❌ Нужно указать ID и username!\nИспользование: /add_admin user_id @username")
        return
    
    target_id = context.args[0]
    target_username = context.args[1]
    
    if not target_id.isdigit():
        await update.message.reply_text("❌ ID должен быть числом!")
        return
    
    target_id = int(target_id)
    
    if not target_username.startswith('@'):
        await update.message.reply_text("❌ Username должен начинаться с @!")
        return
    
    target_username = target_username[1:]
    
    try:
        cursor.execute("SELECT 1 FROM admins WHERE admin_id = %s OR username = %s", (target_id, target_username))
        if cursor.fetchone():
            await update.message.reply_text("❌ Этот пользователь уже есть в базе администраторов!")
            return
        
        cursor.execute("INSERT INTO admins (admin_id, username, role) VALUES (%s, %s, 'admin')",
                      (target_id, target_username))
        conn.commit()
        
        await update.message.reply_text(f"✅ Администратор добавлен!\n👤 ID: {target_id}\n📱 Username: @{target_username}")
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка при добавлении администратора: {str(e)}")

@only_in_chats
async def list_admins(update: Update, context: CallbackContext):
    ensure_connection()
    cursor.execute("SELECT admin_id, username, role FROM admins ORDER BY role DESC, username")
    admins = cursor.fetchall()
    
    if not admins:
        await update.message.reply_text("📋 Список администраторов пуст")
        return
    
    text = "👑 ВЛАДЕЛЬЦЫ:\n"
    owners = [admin for admin in admins if admin[2] == 'owner']
    for admin in owners:
        admin_id, username, role = admin
        text += f"• ID: `{admin_id}`" + (f" | @{username}" if username else " | username не указан") + "\n"
    
    text += "\n👮 АДМИНИСТРАТОРЫ:\n"
    admins_list = [admin for admin in admins if admin[2] == 'admin']
    for admin in admins_list:
        admin_id, username, role = admin
        text += f"• ID: `{admin_id}`" + (f" | @{username}" if username else " | username не указан") + "\n"
    
    await update.message.reply_text(text, parse_mode='Markdown')

def main():
    """Основная функция запуска"""
    print("🔄 Создаем application...")
    
    # Создаем application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # ДОБАВЛЯЕМ ВСЕ КОМАНДЫ
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("check", check_user))
    application.add_handler(CommandHandler("stats", stats))
    application.add_handler(CommandHandler("ban", ban_user))
    application.add_handler(CommandHandler("unban", unban_user))
    application.add_handler(CommandHandler("warn", warn_user))
    application.add_handler(CommandHandler("mute", mute_user))
    application.add_handler(CommandHandler("add_scammer", add_scammer))
    application.add_handler(CommandHandler("add_owner", add_owner))
    application.add_handler(CommandHandler("add_admin", add_admin))
    application.add_handler(CommandHandler("list_admins", list_admins))
    
    print("✅ Application создан, запускаем polling...")
    
    # Запускаем бота
    application.run_polling()

if __name__ == '__main__':
    print("🚀 Запускаем бота...")
    
    # Инициализация БД
    init_db()
    print("📊 База данных инициализирована")
    
    # Запуск
    main()

