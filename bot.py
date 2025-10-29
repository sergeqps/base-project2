import os
import sqlite3
import logging
from datetime import datetime, timedelta
from PIL import Image, ImageDraw, ImageFont
import io
from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackContext, MessageHandler, filters

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# ⚠️ ДАННЫЕ ИЗ ПЕРЕМЕННЫХ ОКРУЖЕНИЯ
BOT_TOKEN = os.getenv('BOT_TOKEN')
YOUR_USER_ID = int(os.getenv('YOUR_USER_ID', '123456789'))

if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN не установлен! Добавьте его в переменные окружения.")

print("🛡️ Бот базы скамеров запускается...")
print(f"✅ YOUR_USER_ID: {YOUR_USER_ID}")

conn = sqlite3.connect('scammers.db', check_same_thread=False)
cursor = conn.cursor()

def init_db():
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS scammers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE NOT NULL,
            username TEXT,
            proof TEXT NOT NULL,
            added_by INTEGER NOT NULL,
            added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            scam_type TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS admins (
            admin_id INTEGER PRIMARY KEY,
            username TEXT,
            role TEXT NOT NULL DEFAULT 'admin'
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            username TEXT,
            reason TEXT NOT NULL,
            banned_by INTEGER NOT NULL,
            ban_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            chat_id INTEGER
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS warns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            username TEXT,
            reason TEXT NOT NULL,
            warned_by INTEGER NOT NULL,
            warn_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            chat_id INTEGER
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS mutes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            username TEXT,
            reason TEXT NOT NULL,
            muted_by INTEGER NOT NULL,
            mute_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            unmute_date TIMESTAMP,
            chat_id INTEGER
        )
    ''')
    cursor.execute("INSERT OR IGNORE INTO admins (admin_id, role) VALUES (?, 'owner')", (YOUR_USER_ID,))
    conn.commit()
    print("✅ База данных инициализирована")

def is_owner(user_id):
    cursor.execute("SELECT 1 FROM admins WHERE admin_id = ? AND role = 'owner'", (user_id,))
    return cursor.fetchone() is not None

def is_admin(user_id):
    cursor.execute("SELECT 1 FROM admins WHERE admin_id = ?", (user_id,))
    return cursor.fetchone() is not None

def get_user_role(user_id):
    cursor.execute("SELECT role FROM admins WHERE admin_id = ?", (user_id,))
    result = cursor.fetchone()
    return result[0] if result else 'user'

def is_target_owner(target_username):
    cursor.execute("SELECT 1 FROM admins WHERE username = ? AND role = 'owner'", (target_username,))
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
    user_id = update.effective_user.id
    username = update.effective_user.username
    full_name = update.effective_user.full_name
    chat_title = update.effective_chat.title
    
    if is_admin(user_id) and username:
        cursor.execute("UPDATE admins SET username = ? WHERE admin_id = ?", (username, user_id))
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
        text += "• /add_scammer user_id|пруфы|тип - Добавить скамера\n"
    
    if is_owner(user_id):
        text += "\n👑 Команды владельца:\n"
        text += "• /add_admin @username - Добавить администратора\n"
        text += "• /add_owner @username - Добавить владельца\n"
        text += "• /list_admins - Список администраторов\n"
    
    await update.message.reply_text(text)

@only_in_chats
async def help_command(update: Update, context: CallbackContext):
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
            "• /add_scammer user_id|пруфы|тип - Добавить скамера\n\n"
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
            "• /add_admin @username - Добавить администратора\n"
            "• /add_owner @username - Добавить владельца\n"
            "• /list_admins - Список администраторов\n"
        )
    
    await update.message.reply_text(text)

@only_in_chats
async def check_user(update: Update, context: CallbackContext):
    if not context.args:
        await update.message.reply_text("❌ Использование: /check @username или /check 123456789")
        return
    
    search_query = context.args[0]

    # Сначала проверяем базу скамеров
    if search_query.isdigit():
        cursor.execute("SELECT user_id, username, proof, scam_type FROM scammers WHERE user_id = ?", (int(search_query),))
        scammer_data = cursor.fetchone()
        
        if scammer_data:
            user_id, username, proof, scam_type = scammer_data
            user_info = f"ID: {user_id}" + (f" | @{username}" if username else "")
            image_bytes = create_status_image('скамер', user_info)
            
            text = f"🚨 НАЙДЕН В БАЗЕ СКАМЕРОВ!\n\n👤 ID: `{user_id}`\n"
            if username:
                text += f"📱 Username: @{username}\n"
            if scam_type:
                text += f"🎯 Тип скама: {scam_type}\n"
            text += f"📝 Пруфы: {proof}"
            
            await update.message.reply_photo(
                photo=image_bytes,
                caption=text,
                parse_mode='Markdown'
            )
            return

    elif search_query.startswith('@'):
        username = search_query[1:].lower()
        cursor.execute("SELECT user_id, username, proof, scam_type FROM scammers WHERE LOWER(username) = ?", (username,))
        scammer_data = cursor.fetchone()
        
        if scammer_data:
            user_id, username, proof, scam_type = scammer_data
            user_info = f"ID: {user_id} | @{username}"
            image_bytes = create_status_image('скамер', user_info)
            
            text = f"🚨 НАЙДЕН В БАЗЕ СКАМЕРОВ!\n\n👤 ID: `{user_id}`\n📱 Username: @{username}\n"
            if scam_type:
                text += f"🎯 Тип скама: {scam_type}\n"
            text += f"📝 Пруфы: {proof}"
            
            await update.message.reply_photo(
                photo=image_bytes,
                caption=text,
                parse_mode='Markdown'
            )
            return

    # Если не найден в скамерах, проверяем админов
    if search_query.isdigit():
        cursor.execute("SELECT admin_id, username, role FROM admins WHERE admin_id = ?", (int(search_query),))
        admin_data = cursor.fetchone()
        
        if admin_data:
            admin_id, username, role = admin_data
            user_info = f"ID: {admin_id}" + (f" | @{username}" if username else "")
            image_bytes = create_status_image('владелец' if role == 'owner' else 'администратор', user_info)
            
            role_text = "👑 ВЛАДЕЛЕЦ" if role == 'owner' else "👮 АДМИНИСТРАТОР"
            text = f"{role_text}\n\n👤 ID: `{admin_id}`\n"
            if username:
                text += f"📱 Username: @{username}\n"
            text += f"💼 Роль: {role}"
            
            await update.message.reply_photo(
                photo=image_bytes,
                caption=text,
                parse_mode='Markdown'
            )
            return

    elif search_query.startswith('@'):
        username = search_query[1:].lower()
        cursor.execute("SELECT admin_id, username, role FROM admins WHERE LOWER(username) = ?", (username,))
        admin_data = cursor.fetchone()
        
        if admin_data:
            admin_id, username, role = admin_data
            user_info = f"ID: {admin_id} | @{username}"
            image_bytes = create_status_image('владелец' if role == 'owner' else 'администратор', user_info)
            
            role_text = "👑 ВЛАДЕЛЕЦ" if role == 'owner' else "👮 АДМИНИСТРАТОР"
            text = f"{role_text}\n\n👤 ID: `{admin_id}`\n📱 Username: @{username}\n"
            text += f"💼 Роль: {role}"
            
            await update.message.reply_photo(
                photo=image_bytes,
                caption=text,
                parse_mode='Markdown'
            )
            return

    # Если не найден нигде - обычный пользователь
    user_info = f"Запрос: {search_query}"
    image_bytes = create_status_image('обычный пользователь', user_info)
    
    text = "✅ ОБЫЧНЫЙ ПОЛЬЗОВАТЕЛЬ\n\nНе найден в базе скамеров и не является администратором."
    
    await update.message.reply_photo(
        photo=image_bytes,
        caption=text,
        parse_mode='Markdown'
    )

@only_in_chats
async def add_scammer(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        await update.message.reply_text("❌ Только администраторы могут добавлять скамеров!")
        return
    
    if not context.args:
        await update.message.reply_text(
            "❌ Использование: /add_scammer user_id|пруфы|тип\n\n"
            "Примеры:\n"
            "/add_scammer 123456789|Кинул на 1000р|Невывод средств\n"
            "/add_scammer @scammer|Обман при обмене|Фейковый обменник"
        )
        return
    
    data = ' '.join(context.args)
    
    try:
        parts = data.split('|')
        if len(parts) < 2:
            await update.message.reply_text("❌ Неверный формат. Нужно: user_id|пруфы|тип")
            return
        
        user_id_part = parts[0].strip()
        proof = parts[1].strip()
        scam_type = parts[2].strip() if len(parts) > 3 else "Не указан"
        
        if user_id_part.isdigit():
            scammer_id = int(user_id_part)
            username = None
        elif user_id_part.startswith('@'):
            username = user_id_part[1:].lower()
            scammer_id = None
            await update.message.reply_text("❌ Для добавления скамера нужен User ID, а не username.")
            return
        else:
            await update.message.reply_text("❌ User ID должен быть числом или username начинаться с @")
            return
        
        if scammer_id is None:
            return
        
        cursor.execute("SELECT 1 FROM scammers WHERE user_id = ?", (scammer_id,))
        if cursor.fetchone():
            await update.message.reply_text("❌ Этот пользователь уже есть в базе скамеров.")
            return
        
        cursor.execute("INSERT INTO scammers (user_id, username, proof, added_by, scam_type) VALUES (?, ?, ?, ?, ?)",
                      (scammer_id, username, proof, user_id, scam_type))
        conn.commit()
        
        await update.message.reply_text("✅ Скамер успешно добавлен в базу!")
        
    except ValueError:
        await update.message.reply_text("❌ User ID должен быть числом")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка при добавлении: {str(e)}")

@only_in_chats
async def ban_user(update: Update, context: CallbackContext):
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
    
    # Проверяем, не является ли целевой пользователь владельцем
    if is_target_owner(target_username):
        await update.message.reply_text("❌ Невозможно забанить владельца!")
        return
    
    try:
        cursor.execute("INSERT INTO bans (user_id, username, reason, banned_by, chat_id) VALUES (?, ?, ?, ?, ?)",
                      (0, target_username, reason, user_id, chat_id))
        conn.commit()
        
        await update.message.reply_text(f"✅ Пользователь @{target_username} забанен!\nПричина: {reason}")
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка при бане: {str(e)}")

@only_in_chats
async def unban_user(update: Update, context: CallbackContext):
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
        cursor.execute("DELETE FROM bans WHERE username = ?", (target_username,))
        conn.commit()
        
        if cursor.rowcount > 0:
            await update.message.reply_text(f"✅ Пользователь @{target_username} разбанен!")
        else:
            await update.message.reply_text(f"❌ Пользователь @{target_username} не найден в списке банов.")
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка при разбане: {str(e)}")

@only_in_chats
async def warn_user(update: Update, context: CallbackContext):
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
    
    # Проверяем, не является ли целевой пользователь владельцем
    if is_target_owner(target_username):
        await update.message.reply_text("❌ Невозможно выдать варн владельцу!")
        return
    
    try:
        cursor.execute("INSERT INTO warns (user_id, username, reason, warned_by, chat_id) VALUES (?, ?, ?, ?, ?)",
                      (0, target_username, reason, user_id, chat_id))
        conn.commit()
        
        cursor.execute("SELECT COUNT(*) FROM warns WHERE username = ?", (target_username,))
        warn_count = cursor.fetchone()[0]
        
        await update.message.reply_text(
            f"⚠️ Пользователь @{target_username} получил варн!\n"
            f"Причина: {reason}\n"
            f"Всего варнов: {warn_count}/3"
        )
        
        if warn_count >= 3:
            cursor.execute("INSERT INTO bans (user_id, username, reason, banned_by, chat_id) VALUES (?, ?, ?, ?, ?)",
                          (0, target_username, f"Автобан за 3 варна (последний: {reason})", user_id, chat_id))
            cursor.execute("DELETE FROM warns WHERE username = ?", (target_username,))
            conn.commit()
            
            await update.message.reply_text(
                f"🚨 АВТОМАТИЧЕСКИЙ БАН!\n"
                f"Пользователь @{target_username} получил бан за 3 варна.\n"
                f"Причина последнего варна: {reason}"
            )
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка при выдаче варна: {str(e)}")

@only_in_chats
async def mute_user(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    if not is_admin(user_id):
        await update.message.reply_text("❌ Только администраторы могут мутить пользователей!")
        return
    
    if not context.args or len(context.args) < 3:
        await update.message.reply_text("❌ Использование: /mute @username время причина\n\nПримеры:\n/mute @username 1h Флуд\n/mute @username 30m Реклама")
        return
    
    target_username = context.args[0]
    time_str = context.args[1]
    reason = ' '.join(context.args[2:])
    
    if not target_username.startswith('@'):
        await update.message.reply_text("❌ Укажите username пользователя (начинается с @)")
        return
    
    target_username = target_username[1:]
    
    # Проверяем, не является ли целевой пользователь владельцем
    if is_target_owner(target_username):
        await update.message.reply_text("❌ Невозможно замутить владельца!")
        return
    
    try:
        if time_str.endswith('m'):
            minutes = int(time_str[:-1])
            mute_duration = timedelta(minutes=minutes)
        elif time_str.endswith('h'):
            hours = int(time_str[:-1])
            mute_duration = timedelta(hours=hours)
        elif time_str.endswith('d'):
            days = int(time_str[:-1])
            mute_duration = timedelta(days=days)
        else:
            await update.message.reply_text("❌ Неверный формат времени. Используйте: 30m, 1h, 1d")
            return
        
        unmute_date = datetime.now() + mute_duration
        
        cursor.execute("INSERT INTO mutes (user_id, username, reason, muted_by, unmute_date, chat_id) VALUES (?, ?, ?, ?, ?, ?)",
                      (0, target_username, reason, user_id, unmute_date, chat_id))
        conn.commit()
        
        await update.message.reply_text(
            f"🔇 Пользователь @{target_username} замьючен!\n"
            f"Время: {time_str}\n"
            f"Причина: {reason}\n"
            f"Размут: {unmute_date.strftime('%d.%m.%Y %H:%M')}"
        )
        
    except ValueError:
        await update.message.reply_text("❌ Неверный формат времени. Используйте: 30m, 1h, 1d")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка при муте: {str(e)}")

@only_in_chats
async def unmute_user(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        await update.message.reply_text("❌ Только администраторы могут размучивать пользователей!")
        return
    
    if not context.args:
        await update.message.reply_text("❌ Использование: /unmute @username")
        return
    
    target_username = context.args[0]
    
    if not target_username.startswith('@'):
        await update.message.reply_text("❌ Укажите username пользователя (начинается с @)")
        return
    
    target_username = target_username[1:]
    
    try:
        cursor.execute("DELETE FROM mutes WHERE username = ?", (target_username,))
        conn.commit()
        
        if cursor.rowcount > 0:
            await update.message.reply_text(f"🔊 Пользователь @{target_username} размьючен!")
        else:
            await update.message.reply_text(f"❌ Пользователь @{target_username} не найден в списке мутов.")
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка при размуте: {str(e)}")

@only_in_chats
async def check_warns(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        await update.message.reply_text("❌ Только администраторы могут просматривать варны!")
        return
    
    if not context.args:
        await update.message.reply_text("❌ Использование: /warns @username")
        return
    
    target_username = context.args[0]
    
    if not target_username.startswith('@'):
        await update.message.reply_text("❌ Укажите username пользователя (начинается с @)")
        return
    
    target_username = target_username[1:]
    
    try:
        cursor.execute("SELECT reason, warned_by, warn_date FROM warns WHERE username = ? ORDER BY warn_date DESC", (target_username,))
        warns = cursor.fetchall()
        
        cursor.execute("SELECT COUNT(*) FROM warns WHERE username = ?", (target_username,))
        warn_count = cursor.fetchone()[0]
        
        if not warns:
            await update.message.reply_text(f"✅ У @{target_username} нет варнов.")
            return
        
        text = f"⚠️ Варны пользователя @{target_username} ({warn_count}/3):\n\n"
        
        for i, (reason, warned_by, warn_date) in enumerate(warns, 1):
            text += f"{i}. {reason}\n"
            text += f"   Выдал: {warned_by} | {warn_date[:16]}\n\n"
        
        await update.message.reply_text(text)
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка при проверке варнов: {str(e)}")

@only_in_chats
async def ban_list(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        await update.message.reply_text("❌ Только администраторы могут просматривать список банов!")
        return
    
    try:
        cursor.execute("SELECT username, reason, banned_by, ban_date FROM bans ORDER BY ban_date DESC")
        bans = cursor.fetchall()
        
        if not bans:
            await update.message.reply_text("📭 Список банов пуст.")
            return
        
        text = "🚨 Список забаненных пользователей:\n\n"
        
        for username, reason, banned_by, ban_date in bans:
            text += f"👤 @{username}\n"
            text += f"📝 Причина: {reason}\n"
            text += f"👮 Забанен: {banned_by}\n"
            text += f"📅 Дата: {ban_date[:16]}\n"
            text += "─" * 30 + "\n"
        
        await update.message.reply_text(text)
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка при получении списка банов: {str(e)}")

@only_in_chats
async def add_admin(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    
    if not is_owner(user_id):
        await update.message.reply_text("❌ Только владелец может добавлять администраторов!")
        return
    
    if not context.args:
        await update.message.reply_text("❌ Использование: /add_admin @username или /add_admin 123456789")
        return
    
    target = context.args[0]
    
    try:
        if target.isdigit():
            admin_id = int(target)
            cursor.execute("INSERT OR REPLACE INTO admins (admin_id, role) VALUES (?, 'admin')", (admin_id,))
            conn.commit()
            await update.message.reply_text(f"✅ Администратор добавлен! ID: {admin_id}")
            
        elif target.startswith('@'):
            username = target[1:]
            await update.message.reply_text(
                f"❌ Для добавления администратора нужен User ID.\n\n"
                f"Попросите пользователя @{username} отправить свой ID (можно узнать через @userinfobot)"
            )
        else:
            await update.message.reply_text("❌ Неверный формат. Используйте: /add_admin @username или /add_admin 123456789")
            
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

@only_in_chats
async def add_owner(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    
    if not is_owner(user_id):
        await update.message.reply_text("❌ Только владелец может добавлять других владельцев!")
        return
    
    if not context.args:
        await update.message.reply_text("❌ Использование: /add_owner @username или /add_owner 123456789")
        return
    
    target = context.args[0]
    
    try:
        if target.isdigit():
            owner_id = int(target)
            cursor.execute("INSERT OR REPLACE INTO admins (admin_id, role) VALUES (?, 'owner')", (owner_id,))
            conn.commit()
            await update.message.reply_text(f"✅ Владелец добавлен! ID: {owner_id}")
            
        elif target.startswith('@'):
            username = target[1:]
            await update.message.reply_text(
                f"❌ Для добавления владельца нужен User ID.\n\n"
                f"Попросите пользователя @{username} отправить свой ID (можно узнать через @userinfobot)"
            )
        else:
            await update.message.reply_text("❌ Неверный формат. Используйте: /add_owner @username или /add_owner 123456789")
            
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

@only_in_chats
async def list_admins(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    
    if not is_owner(user_id):
        await update.message.reply_text("❌ Только владелец может просматривать список администраторов!")
        return
    
    cursor.execute("SELECT admin_id, username, role FROM admins ORDER BY role DESC, admin_id")
    admins = cursor.fetchall()
    
    if not admins:
        await update.message.reply_text("📭 В базе нет администраторов.")
        return
    
    text = "👥 Список администраторов:\n\n"
    for admin in admins:
        admin_id, username, role = admin
        role_icon = "👑" if role == 'owner' else "👮"
        username_display = f"@{username}" if username else f"ID: {admin_id}"
        text += f"{role_icon} {username_display} ({role})\n"
    
    await update.message.reply_text(text)

@only_in_chats
async def stats(update: Update, context: CallbackContext):
    cursor.execute("SELECT COUNT(*) FROM scammers")
    total_scammers = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM scammers WHERE date(added_date) = date('now')")
    today_scammers = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM admins")
    total_admins = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM admins WHERE role = 'owner'")
    total_owners = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM bans")
    total_bans = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM warns")
    total_warns = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM mutes")
    total_mutes = cursor.fetchone()[0]
    
    text = (
        "📊 СТАТИСТИКА БАЗЫ СКАМЕРОВ\n\n"
        f"• 🚨 Всего скамеров: {total_scammers}\n"
    )

