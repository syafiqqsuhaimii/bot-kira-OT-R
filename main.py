import os
import sys
import logging
import telebot
from telebot import types
from flask import Flask, request

# ==========================
# BOT TOKEN
# ==========================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN not set in environment variables!")

telebot.logger.setLevel(logging.DEBUG)
bot = telebot.TeleBot(BOT_TOKEN)

# ==========================
# SESSION
# ==========================
# {chat_id: {"rate": float|None, "weekday": float, "weekend": float, "ph": float, "waiting_for": str|None}}
user_sessions = {}
PRESET_WEEKDAY = {"OT1": 3, "OT2": 4, "OT3": 5}

# ==========================
# UTIL
# ==========================
def is_number(s: str) -> bool:
    if not s:
        return False
    s = s.strip().replace(",", ".")
    try:
        float(s)
        return True
    except ValueError:
        return False

def kira_ot(rate, jam, jenis):
    rate = float(rate); jam = float(jam)
    if jenis == "weekday":
        return round(rate * 1.5 * jam, 2)
    if jenis == "weekend":
        if jam <= 4:  return round(rate * 0.5 * jam, 2)
        if jam <= 8:  return round(rate * jam, 2)
        return round((rate * 8) + (rate * 2 * (jam - 8)), 2)
    if jenis == "public holiday":
        if jam <= 8:  return round(rate * 2 * jam, 2)
        return round((rate * 2 * 8) + (rate * 3 * (jam - 8)), 2)
    return 0

# ==========================
# INLINE BUTTONS
# ==========================
def main_menu():
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("🏢 Weekday", callback_data="weekday"),
        types.InlineKeyboardButton("📅 Weekend", callback_data="weekend"),
        types.InlineKeyboardButton("🎉 Public Holiday", callback_data="ph"),
        types.InlineKeyboardButton("💰 Total", callback_data="total"),
    )
    kb.add(
        types.InlineKeyboardButton("📘 Help", callback_data="help"),
        types.InlineKeyboardButton("♻️ Reset", callback_data="reset"),
    )
    return kb

def send_main_buttons(chat_id, text="Sila pilih jenis OT:"):
    bot.send_message(chat_id, text, reply_markup=main_menu())

def send_help(chat_id):
    bot.send_message(
        chat_id,
        "📘 *Cara guna:*\n"
        "1) Taip *rate sejam* (cth: `12.5`).\n"
        "2) Guna butang:\n"
        "   • 🏢 *Weekday* → balas `OT1 OT2 OT3` (cth: `2 1 0`) — OT1=3j, OT2=4j, OT3=5j.\n"
        "   • 📅 *Weekend* → balas *bilangan hari* (1 hari = 8 jam), cth: `2`.\n"
        "   • 🎉 *Public Holiday* → balas *jumlah jam*, cth: `9`.\n"
        "   • 💰 *Total* → lihat ringkasan kiraan.\n\n"
        "👨‍💼 Administrator: @syafiqqsuhaimii",
        parse_mode="Markdown",
        reply_markup=main_menu()
    )

def do_reset(chat_id, ask_rate=True):
    user_sessions[chat_id] = {"rate": None, "weekday": 0.0, "weekend": 0.0, "ph": 0.0, "waiting_for": None}
    if ask_rate:
        user_sessions[chat_id]["waiting_for"] = "rate"
        bot.send_message(chat_id, "Masukkan kadar OT sejam (contoh: 10.5)")

# ==========================
# COMMANDS (help/reset/ping)
# ==========================
@bot.message_handler(commands=["help"])
def help_cmd(message):
    send_help(message.chat.id)

@bot.message_handler(commands=["reset"])
def reset_cmd(message):
    do_reset(message.chat.id, ask_rate=True)

@bot.message_handler(commands=["ping"])
def ping(message):
    try:
        bot.send_message(message.chat.id, "pong")
        print("✅ /ping replied", file=sys.stdout, flush=True)
    except Exception as e:
        print("❌ /ping failed:", repr(e), file=sys.stderr, flush=True)

# ==========================
# INLINE CALLBACKS
# ==========================
@bot.callback_query_handler(func=lambda call: True)
def callback(call):
    chat_id = call.message.chat.id
    data = call.data
    session = user_sessions.get(chat_id)

    if data == "help":
        return send_help(chat_id)
    if data == "reset":
        do_reset(chat_id, ask_rate=True)
        return

    if not session or session.get("rate") is None:
        user_sessions.setdefault(chat_id, {"rate": None, "weekday": 0.0, "weekend": 0.0, "ph": 0.0, "waiting_for": None})
        user_sessions[chat_id]["waiting_for"] = "rate"
        bot.send_message(chat_id, "⚠️ Sila masukkan rate sejam dahulu (cth: 10.5).")
        return

    session["waiting_for"] = data

    if data == "weekday":
        bot.send_message(
            chat_id,
            "Masukkan hari untuk OT1, OT2, OT3.\n"
            "Contoh: `2 1 0`\n"
            "Format: OT1 OT2 OT3",
            parse_mode="Markdown"
        )
    elif data == "weekend":
        bot.send_message(chat_id, "Masukkan *bilangan hari* weekend (1 hari = 8 jam). Contoh: `2`", parse_mode="Markdown")
    elif data == "ph":
        bot.send_message(chat_id, "Masukkan *jumlah jam* OT Public Holiday. Contoh: `10`", parse_mode="Markdown")
    elif data == "total":
        msg = (
            f"📊 Ringkasan OT:\n"
            f"🏢 Weekday: RM {session['weekday']:.2f}\n"
            f"📅 Weekend: RM {session['weekend']:.2f}\n"
            f"🎉 Public Holiday: RM {session['ph']:.2f}\n\n"
            f"💰 Total: RM {session['weekday'] + session['weekend'] + session['ph']:.2f}"
        )
        bot.send_message(chat_id, msg, reply_markup=main_menu())

# ==========================
# UNIVERSAL HANDLER (STATE MACHINE)
# ==========================
@bot.message_handler(func=lambda m: True)
def handle_all(message):
    chat_id = message.chat.id
    text = (message.text or "").strip()
    print(f"🔎 handle_all text='{text}' chat_id={chat_id}", file=sys.stdout, flush=True)

    # Commands fallback (pastikan /start sentiasa berfungsi)
    if text.startswith("/"):
        cmd = text.split()[0].lower()
        if cmd == "/start":
            do_reset(chat_id, ask_rate=True)
            return
        if cmd == "/help":
            return send_help(chat_id)
        if cmd == "/reset":
            return do_reset(chat_id, ask_rate=True)
        if cmd == "/ping":
            return ping(message)

    # Ensure session
    session = user_sessions.get(chat_id)
    if not session:
        do_reset(chat_id, ask_rate=True)
        return

    waiting = session.get("waiting_for")

    # 1) Waiting for rate
    if waiting == "rate":
        if not is_number(text):
            bot.send_message(chat_id, "❌ Tolong masukkan nombor rate sejam (cth: 10.5)")
            return
        rate = float(text.replace(",", "."))
        session["rate"] = rate
        session["waiting_for"] = None
        bot.send_message(chat_id, f"✅ Rate OT diset: RM {rate:.2f}/jam")
        return send_main_buttons(chat_id)  # <<< BUTANG MUNCUL DI SINI

    # 2) Not waiting anything specific
    if not waiting:
        # Jika user hantar teks raw & rate dah ada → papar menu
        if session.get("rate") is not None and not is_number(text):
            return send_main_buttons(chat_id)
        # Jika nombor tapi tiada context, abaikan (jam hanya diminta selepas tekan butang)
        return

    # 3) Waiting for specific OT inputs
    rate = session["rate"]
    try:
        if waiting == "weekday":
            parts = list(map(int, text.split()))
            if len(parts) != 3:
                bot.send_message(chat_id, "❌ Format salah. Contoh: 2 1 0")
                return
            total = 0.0
            reply = "💰 Weekday:\n"
            for i, key in enumerate(["OT1", "OT2", "OT3"]):
                jam = PRESET_WEEKDAY[key]; hari = parts[i]
                subtotal = kira_ot(rate, jam, "weekday") * hari
                reply += f"{key} ({jam}j × {hari}h): RM {subtotal:.2f}\n"
                total += subtotal
            session["weekday"] += total
            bot.send_message(chat_id, reply + f"\n✅ Total Weekday: RM {total:.2f}", reply_markup=main_menu())

        elif waiting == "weekend":
            hari = int(text)
            subtotal = kira_ot(rate, 8, "weekend") * hari
            session["weekend"] += subtotal
            bot.send_message(chat_id, f"💰 Weekend: {hari} hari × 8j = RM {subtotal:.2f}", reply_markup=main_menu())

        elif waiting == "ph":
            jam = float(text.replace(",", "."))
            subtotal = kira_ot(rate, jam, "public holiday")
            session["ph"] += subtotal
            bot.send_message(chat_id, f"💰 Public Holiday: RM {subtotal:.2f}", reply_markup=main_menu())

    except Exception as e:
        bot.send_message(
            chat_id,
            "❌ Format salah. Masukkan nombor sahaja.\n"
            "Jika perlukan bantuan, tekan 📘 Help.",
            reply_markup=main_menu()
        )
        print("❌ Handle OT input error:", repr(e), file=sys.stderr, flush=True)
    finally:
        session["waiting_for"] = None

# ==========================
# FLASK WEBHOOK
# ==========================
app = Flask(__name__)

@app.get("/")
def home():
    return "Bot is running!"

@app.post("/webhook")
def webhook():
    raw = request.get_data(as_text=True)
    print("✅ /webhook received:", raw[:400], file=sys.stdout, flush=True)
    try:
        update = telebot.types.Update.de_json(raw)

        # Direct debug for /ping & /start
        if update and update.message:
            t = (update.message.text or "").strip().lower()
            cid = update.message.chat.id
            if t == "/ping":
                try:
                    bot.send_message(cid, "pong ✅ direct")
                    print("✅ Direct /ping reply sent", file=sys.stdout, flush=True)
                except Exception as ee:
                    print("❌ Direct /ping failed:", repr(ee), file=sys.stderr, flush=True)
            if t == "/start":
                do_reset(cid, ask_rate=True)
                print("✅ Direct /start processed", file=sys.stdout, flush=True)

        bot.process_new_updates([update])
        print("✅ Update processed OK", file=sys.stdout, flush=True)
    except Exception as e:
        print("❌ Error processing update:", repr(e), file=sys.stderr, flush=True)
    return "OK", 200

# ==========================
# RUN (Render uses gunicorn)
# ==========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    print("✅ Flask running on", port)
    app.run(host="0.0.0.0", port=port)
