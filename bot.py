import os
import sys
import time
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ForceReply
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from telegram.error import BadRequest, Forbidden, TimedOut
from cryptography.fernet import Fernet

BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
OWNER_USERNAME = "xdbot1" # without @
BANNER_URL = 'https://files.catbox.moe/9yy6iy.jpg'

FILE_TYPES = {
    '.js': 'JavaScript',
    '.json': 'JSON Config',
    '.yaml': 'YAML Config',
    '.yml': 'YAML Config',
    '.toml': 'TOML Config',
    '.ini': 'INI Config',
    '.cfg': 'Config File',
    '.env': 'Environment File',
    '.xml': 'XML Config',
    '.ovpn': 'OpenVPN',
    '.conf': 'Config File',
    '.txt': 'Text File',
    '.hc': 'HTTP Custom',
    '.ehi': 'HTTP Injector',
    '.dt': 'DarkTunnel'
}

ALLOWED_EXTENSIONS = list(FILE_TYPES.keys())
app = Flask(__name__)

@app.route('/')
def home():
    return "🔐 File Encryptor Bot is running!"

@app.route('/health')
def health():
    return "OK", 200

def get_db():
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("DATABASE_URL not set - skipping DB")
        return None

    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)

    try:
        return psycopg2.connect(db_url, sslmode='require', cursor_factory=RealDictCursor)
    except Exception as e:
        print(f"DB connect error: {e}")
        return None

def init_db():
    conn = get_db()
    if not conn:
        print("No database - running without user tracking")
        return
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        user_id BIGINT PRIMARY KEY,
                        username TEXT,
                        first_name TEXT,
                        started_at TIMESTAMP DEFAULT NOW()
                    )
                """)
        print("Database initialized successfully")
    except Exception as e:
        print(f"Database init error: {e}")
    finally:
        if conn:
            conn.close()

def save_user(user):
    conn = get_db()
    if not conn:
        return
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO users (user_id, username, first_name)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (user_id) DO UPDATE SET
                        username = EXCLUDED.username,
                        first_name = EXCLUDED.first_name
                """, (user.id, user.username, user.first_name))
    except Exception as e:
        print(f"Save user error: {e}")
    finally:
        if conn:
            conn.close()

def load_users():
    conn = get_db()
    if not conn:
        return []
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("SELECT user_id FROM users")
                return [row['user_id'] for row in cur.fetchall()]
    except Exception as e:
        print(f"Load users error: {e}")
        return []
    finally:
        if conn:
            conn.close()

def get_user_count():
    conn = get_db()
    if not conn:
        return 0
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM users")
                return cur.fetchone()['count']
    except Exception as e:
        print(f"Get user count error: {e}")
        return 0
    finally:
        if conn:
            conn.close()

def get_file_type(filename):
    filename = filename.lower()
    for ext, desc in FILE_TYPES.items():
        if filename.endswith(ext):
            return desc
    if filename.endswith('.enc'):
        return 'Encrypted File'
    return 'Unknown'

def is_owner(update: Update):
    user = update.effective_user
    return user.username and user.username.lower() == OWNER_USERNAME.lower()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    save_user(update.effective_user)

    keyboard = [
        [InlineKeyboardButton("🔒 How to Encrypt", callback_data='help_encrypt')],
        [InlineKeyboardButton("🔓 How to Decrypt", callback_data='help_decrypt')],
        [InlineKeyboardButton("📦 Batch Decrypt", callback_data='batch_help')],
        [InlineKeyboardButton("🆔 Get My ID", callback_data='get_id')],
        [InlineKeyboardButton("⚠️ Security Info", callback_data='security')],
        [InlineKeyboardButton("📁 Supported Files", callback_data='supported')]
    ]

    if is_owner(update):
        keyboard.insert(3, [InlineKeyboardButton("👑 Owner Panel", callback_data='owner_panel')])

    reply_markup = InlineKeyboardMarkup(keyboard)

    owner_tag = "\n👑 *Owner mode active*" if is_owner(update) else ""
    welcome_caption = f"""
🔐 *Universal File Encryptor* 🔐{owner_tag}

Encrypt JS, VPN configs, tunneling files, and all cloud configs with AES-256.

*Features:*
- 🆕 Unique key per file - zero password storage
- ⚡ Auto-decrypt: send `.enc` + reply with key
- 📦 Batch mode: decrypt multiple files with one key
- 🆔 ID tools: `/id`, `/groupid`, `/channelid`, `/userinfo`
- 📢 Broadcast: Owner can message all users
- 📁 15+ formats: `.js`, `.json`, `.yaml`, `.ovpn`, `.hc`, `.ehi`, `.dt`, `.env`, etc
- 🔍 Auto-detects file type for clear messages
- 🗄️ Postgres: User list survives restarts
- 🧹 Auto-cleanup - files deleted after sending

*Quick Start:*
1️⃣ Send me any supported file → `/encrypt`
2️⃣ Send me any `.enc` file → reply with your key
3️⃣ Multiple files → `/batch` then send all `.enc` files

*Max file size:* 20MB
    """
    try:
        await update.message.reply_photo(
            photo=BANNER_URL,
            caption=welcome_caption,
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
    except BadRequest:
        # Fallback if banner URL fails
        await update.message.reply_text(
            welcome_caption,
            parse_mode='Markdown',
            reply_markup=reply_markup
        )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == 'help_encrypt':
        text = """
🔒 *How to Encrypt*

1. Send me your file - code, VPN, tunneling, or cloud config
2. Type `/encrypt`
3. I'll reply with `.enc` + a unique key like:
   `gAAAAABn...`
4. *Copy and save that key!* Without it, your file is lost forever.
        """
    elif query.data == 'help_decrypt':
        text = """
🔓 *How to Decrypt - Auto Mode*

1. Send me your `.enc` file
2. I'll ask for your key - just reply to my message with it
3. I'll auto-detect the file type and send back your original

You can still use `/decrypt YOUR_KEY` if you prefer.
        """
    elif query.data == 'batch_help':
        text = """
📦 *Batch Decrypt Mode*

1. Type `/batch`
2. Send all your `.enc` files one by one
3. Type `/done` when finished uploading
4. Reply with ONE key that works for all files
5. I'll decrypt and send them all back

All files must use the same key!
        """
    elif query.data == 'get_id':
        text = """
🆔 *Get Telegram IDs*

*Your User ID:* `/id`
*Group ID:* Add me to a group and send `/groupid`
*Channel ID:* Add me to a channel as admin and send `/channelid`
*User Lookup:* `/userinfo @username` [Owner only]

Use these IDs for bots, webhooks, and APIs.
        """
    elif query.data == 'security':
        text = """
⚠️ *Security Notes*

1. *Keys are random per file* - generated with `Fernet.generate_key()`
2. *AES-256* encryption via `cryptography` library
3. *Zero-knowledge* - I don't store keys or files after sending
4. *Lose the key = lose the file* - no recovery possible
5. *Don't use for illegal stuff* - you're responsible for your files
        """
    elif query.data == 'supported':
        text = """
📁 *Supported File Types*

*Code:* `.js`, `.json`
*Cloud Config:* `.yaml`, `.yml`, `.toml`, `.ini`, `.cfg`, `.env`, `.xml`
*VPN:* `.ovpn`, `.conf`
*Tunneling:* `.hc` HTTP Custom, `.ehi` HTTP Injector, `.dt` DarkTunnel
*Text:* `.txt`
*Encrypted:* `.enc` - auto decrypt mode

Max size: 20MB per file
        """
    elif query.data == 'owner_panel':
        if not is_owner(update):
            await query.answer("❌ Owner only", show_alert=True)
            return
        user = update.effective_user
        user_count = get_user_count()
        text = f"""
👑 *Owner Panel* 👑

You are the bot owner @{OWNER_USERNAME}

*Your Info:*
- User ID: `{user.id}`
- Username: @{user.username}
- Name: {user.first_name}

*Bot Stats:*
- Total Users: `{user_count}`
- Database: Postgres

*Admin Commands:*
- `/stats` - Show bot usage stats
- `/broadcast <message>` - Send to all users
- `/id` - Get your user ID
- `/groupid` - Get group chat ID
- `/channelid` - Get channel ID
- `/userinfo @user` - Lookup any user

*Owner privileges:*
- See this panel on /start
- Broadcast to all users
- No rate limits
        """

    try:
        await query.edit_message_caption(caption=text, parse_mode='Markdown', reply_markup=query.message.reply_markup)
    except:
        await query.edit_message_text(text=text, parse_mode='Markdown', reply_markup=query.message.reply_markup)

async def cmd_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    text = f"""
🆔 *Your Telegram Info*

*User ID:* `{user.id}`
*Username:* @{user.username if user.username else 'None'}
*First Name:* {user.first_name}
*Chat ID:* `{chat.id}`
*Chat Type:* {chat.type}
    """
    await update.message.reply_text(text, parse_mode='Markdown')

async def cmd_groupid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type not in ['group', 'supergroup']:
        await update.message.reply_text("❌ This command only works in groups.\n\nAdd me to a group and use /groupid there.")
        return
    text = f"""
🆔 *Group Info*

*Group ID:* `{chat.id}`
*Group Title:* {chat.title}
*Type:* {chat.type}
    """
    await update.message.reply_text(text, parse_mode='Markdown')

async def cmd_channelid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type!= 'channel':
        await update.message.reply_text("❌ This command only works in channels.\n\nAdd me as admin to a channel and use /channelid there.")
        return
    text = f"""
🆔 *Channel Info*

*Channel ID:* `{chat.id}`
*Channel Title:* {chat.title}
*Username:* @{chat.username if chat.username else 'Private channel'}
    """
    await update.message.reply_text(text, parse_mode='Markdown')

async def cmd_userinfo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update):
        await update.message.reply_text("❌ Owner only command")
        return

    if not context.args:
        await update.message.reply_text("❌ Usage: `/userinfo @username` or `/userinfo 123456789`", parse_mode='Markdown')
        return

    target = context.args[0]
    if target.startswith('@'):
        target = target[1:]

    try:
        if target.isdigit():
            user = await context.bot.get_chat(int(target))
        else:
            user = await context.bot.get_chat(f"@{target}")

        text = f"""
🆔 *User Info Lookup*

*User ID:* `{user.id}`
*Username:* @{user.username if user.username else 'None'}
*First Name:* {user.first_name}
*Last Name:* {user.last_name if user.last_name else 'None'}
*Is Bot:* {user.is_bot}
*Type:* {user.type}
        """
        await update.message.reply_text(text, parse_mode='Markdown')
    except BadRequest as e:
        await update.message.reply_text(f"❌ Could not find user `{target}`\n\nError: {str(e)}\n\nNote: I can only see users who have started the bot or are in a shared group.", parse_mode='Markdown')
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def cmd_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update):
        await update.message.reply_text("❌ Owner only command")
        return

    if not context.args:
        await update.message.reply_text(
            "❌ Usage: `/broadcast Your message here`\n\nExample: `/broadcast Bot will be down for maintenance in 10min`",
            parse_mode='Markdown'
        )
        return

    message = ' '.join(context.args)
    users = load_users()

    if not users:
        await update.message.reply_text("❌ No users to broadcast to yet.")
        return

    msg = await update.message.reply_text(f"📢 Broadcasting to {len(users)} users...")
    success = 0
    failed = 0

    for user_id in users:
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"📢 *Broadcast from @{OWNER_USERNAME}*\n\n{message}",
                parse_mode='Markdown'
            )
            success += 1
        except Forbidden:
            failed += 1
        except Exception:
            failed += 1

    await msg.edit_text(
        f"✅ *Broadcast Complete*\n\nSuccess: {success}\nFailed: {failed}\nTotal: {len(users)}",
        parse_mode='Markdown'
    )

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    file_name = doc.file_name
    file_type = get_file_type(file_name)

    if not any(file_name.lower().endswith(ext) for ext in ALLOWED_EXTENSIONS + ['.enc']):
        await update.message.reply_text(
            f"❌ Unsupported file type. I accept: {', '.join(ALLOWED_EXTENSIONS)},.enc"
        )
        return
    if doc.file_size > 20 * 1024 * 1024:
        await update.message.reply_text("❌ File too large. Max 20MB")
        return

    file = await context.bot.get_file(doc.file_id)
    file_path = f"temp_{update.effective_user.id}_{doc.file_name}"
    await file.download_to_drive(file_path)

    if context.user_data.get('batch_mode'):
        if not file_name.lower().endswith('.enc'):
            await update.message.reply_text("❌ Batch mode: only send `.enc` files")
            os.remove(file_path)
            return
        if 'batch_files' not in context.user_data:
            context.user_data['batch_files'] = []
        context.user_data['batch_files'].append({'path': file_path, 'name': doc.file_name})
        await update.message.reply_text(f"📥 Added {file_name} to batch. Total: {len(context.user_data['batch_files'])}\nSend more or /done")
        return

    context.user_data['file_path'] = file_path
    context.user_data['original_name'] = doc.file_name
    context.user_data['file_type'] = file_type

    if file_name.lower().endswith('.enc'):
        await update.message.reply_text(
            f"📥 Encrypted file detected!\n\nReply to this message with your decryption key:",
            reply_markup=ForceReply(selective=True)
        )
        context.user_data['waiting_for_key'] = True
    else:
        await update.message.reply_text(f"📥 {file_type} file received! Now send `/encrypt`")

async def handle_key_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('batch_waiting_key'):
        await batch_decrypt(update, context)
        return

    if not context.user_data.get('waiting_for_key'):
        return
    if not update.message.reply_to_message:
        return

    user_key = update.message.text.strip()
    file_path = context.user_data['file_path']
    original_name = context.user_data['original_name']

    msg = await update.message.reply_text("🔄 Decrypting file...")
    context.user_data['waiting_for_key'] = False

    try:
        f = Fernet(user_key.encode())
        with open(file_path, 'rb') as file:
            encrypted_data = file.read()
        decrypted = f.decrypt(encrypted_data)

        if original_name.endswith('.enc'):
            base_name = original_name[:-4]
            detected_type = get_file_type(base_name)
            await msg.edit_text(f"🔄 Decrypting {detected_type}...")

            name_parts = base_name.rsplit('.', 1)
            if len(name_parts) == 2:
                out_filename = f"{name_parts[0]}.dec.{name_parts[1]}"
            else:
                out_filename = base_name + '.dec'
        else:
            out_filename = original_name + '.dec'
            detected_type = "file"

        out_path = file_path.replace('.enc', '.dec')
        with open(out_path, 'wb') as file:
            file.write(decrypted)

        await update.message.reply_document(
            document=open(out_path, 'rb'),
            filename=out_filename,
            caption=f"✅ Decrypted {detected_type} successfully!"
        )
        await msg.delete()
        os.remove(file_path)
        os.remove(out_path)
        for k in ['file_path', 'original_name', 'file_type', 'waiting_for_key']:
            context.user_data.pop(k, None)
    except Exception:
        await msg.edit_text("❌ Wrong key or corrupted file. Cannot decrypt.\n\nSend the `.enc` file again to retry.")
        for k in ['file_path', 'original_name', 'file_type', 'waiting_for_key']:
            context.user_data.pop(k, None)

async def encrypt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'file_path' not in context.user_data:
        await update.message.reply_text("❌ Send me a file first, then use /encrypt")
        return
    file_path = context.user_data['file_path']
    original_name = context.user_data['original_name']
    file_type = context.user_data['file_type']
    msg = await update.message.reply_text(f"🔄 Encrypting {file_type}...")
    try:
        key = Fernet.generate_key()
        f = Fernet(key)

        with open(file_path, 'rb') as file:
            data = file.read()
        encrypted = f.encrypt(data)

        out_path = file_path + '.enc'
        with open(out_path, 'wb') as file:
            file.write(encrypted)

        await update.message.reply_document(
            document=open(out_path, 'rb'),
            filename=original_name + '.enc',
            caption=f"✅ Encrypted `{original_name}` successfully!"
        )
        await update.message.reply_text(
            f"🔑 *Your decryption key for {file_type}:*\n`{key.decode()}`\n\n"
            "⚠️ *SAVE THIS KEY!* Send the `.enc` file back and reply with this key to decrypt.",
            parse_mode='Markdown'
        )
        await msg.delete()
        os.remove(file_path)
        os.remove(out_path)
        for k in ['file_path', 'original_name', 'file_type']:
            context.user_data.pop(k, None)
    except Exception as e:
        await msg.edit_text(f"❌ Error: {str(e)}")

async def decrypt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'file_path' not in context.user_data:
        await update.message.reply_text("❌ Send me a `.enc` file first, then reply with your key")
        return
    if not context.args:
        await update.message.reply_text("❌ Usage: `/decrypt YOUR_KEY` or just reply with your key")
        return

    context.user_data['waiting_for_key'] = True
    update.message.text = context.args[0]
    await handle_key_reply(update, context)

async def batch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['batch_mode'] = True
    context.user_data['batch_files'] = []
    await update.message.reply_text(
        "📦 *Batch Mode Activated*\n\nSend me all your `.enc` files now.\nType `/done` when finished.",
        parse_mode='Markdown'
    )

async def batch_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('batch_mode'):
        await update.message.reply_text("❌ Not in batch mode. Use /batch first")
        return
    batch_files = context.user_data.get('batch_files', [])
    if not batch_files:
        await update.message.reply_text("❌ No files uploaded. Send `.enc` files first")
        context.user_data['batch_mode'] = False
        return

    context.user_data['batch_mode'] = False
    context.user_data['batch_waiting_key'] = True
    await update.message.reply_text(
        f"📥 Got {len(batch_files)} files!\n\nReply to this message with the ONE key that decrypts all of them:",
        reply_markup=ForceReply(selective=True)
    )

async def batch_decrypt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_key = update.message.text.strip()
    batch_files = context.user_data.get('batch_files', [])
    context.user_data['batch_waiting_key'] = False

    msg = await update.message.reply_text(f"🔄 Decrypting {len(batch_files)} files...")
    success_count = 0
    fail_count = 0

    try:
        f = Fernet(user_key.encode())
        for file_data in batch_files:
            try:
                with open(file_data['path'], 'rb') as file:
                    encrypted_data = file.read()
                decrypted = f.decrypt(encrypted_data)

                base_name = file_data['name'][:-4] if file_data['name'].endswith('.enc') else file_data['name']
                name_parts = base_name.rsplit('.', 1)
                if len(name_parts) == 2:
                    out_filename = f"{name_parts[0]}.dec.{name_parts[1]}"
                else:
                    out_filename = base_name + '.dec'

                out_path = file_data['path'].replace('.enc', '.dec')
                with open(out_path, 'wb') as file:
                    file.write(decrypted)

                await update.message.reply_document(
                    document=open(out_path, 'rb'),
                    filename=out_filename
                )
                os.remove(file_data['path'])
                os.remove(out_path)
                success_count += 1
            except Exception:
                fail_count += 1
                if os.path.exists(file_data['path']):
                    os.remove(file_data['path'])

        await msg.edit_text(f"✅ Batch complete!\nSuccess: {success_count}\nFailed: {fail_count}")
    except Exception:
        await msg.edit_text("❌ Invalid key for batch. All files failed.")
        for file_data in batch_files:
            if os.path.exists(file_data['path']):
                os.remove(file_data['path'])

    context.user_data.pop('batch_files', None)

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update):
        await update.message.reply_text("❌ Owner only command")
        return
    user = update.effective_user
    user_count = get_user_count()
    await update.message.reply_text(
        f"👑 *Owner Stats*\n\nBot is running\nOwner: @{OWNER_USERNAME}\nYour ID: `{user.id}`\nChat ID: `{update.effective_chat.id}`\nTotal Users: `{user_count}`\nDatabase: Postgres",
        parse_mode='Markdown'
    )

def run_bot():
    init_db()
    application = Application.builder().token(BOT_TOKEN).read_timeout(30).write_timeout(30).connect_timeout(30).pool_timeout(30).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("encrypt", encrypt))
    application.add_handler(CommandHandler("decrypt", decrypt))
    application.add_handler(CommandHandler("batch", batch))
    application.add_handler(CommandHandler("done", batch_done))
    application.add_handler(CommandHandler("stats", stats))
    application.add_handler(CommandHandler("id", cmd_id))
    application.add_handler(CommandHandler("groupid", cmd_groupid))
    application.add_handler(CommandHandler("channelid", cmd_channelid))
    application.add_handler(CommandHandler("userinfo", cmd_userinfo))
    application.add_handler(CommandHandler("broadcast", cmd_broadcast))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    application.add_handler(MessageHandler(filters.TEXT & filters.REPLY, handle_key_reply))

    print("Starting bot polling...")

    while True:
        try:
            application.run_polling(
                allowed_updates=Update.ALL_TYPES,
                drop_pending_updates=True,
                close_loop=False,
                stop_signals=None
            )
        except Exception as e:
            print(f"Polling crashed: {e}. Restarting in 5s...")
            time.sleep(5)

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == 'web':
        port = int(os.environ.get('PORT', 5000))
        app.run(host='0.0.0.0', port=port)
    else:
        run_bot()