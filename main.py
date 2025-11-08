import os
import sys
import telebot
from telebot import types
from flask import Flask, request

# ==========================
# BOT TOKEN
# ==========================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN not set in environment variables!")

telebot.logger.setLevel("INFO")
bot = telebot.TeleBot(BOT_TOKEN)

# ==========================
# SESSION
# ==========================
user_sessions = {}  # {chat_id: {"rate": float, "weekday": float, "weekend": float, "ph": float, "waiting_for": str|None}}
PRESET_WEEKDAY = {"OT1": 3, "OT2": 4, "OT3": 5}

# ==========================
# OT FORMULA
# ==========================
def kira_ot(rate, jam, jenis):
    rate = float(rate)
    jam = float(jam)

    if jenis == "weekday":
        return round(rate * 1.5 * jam, 2)

    elif jenis == "weekend":
        if jam <= 4:
            return round(rate * 0.5 * jam, 2)
        elif jam <= 8:
            return round(rate * jam, 2)
        else:
            return round((rate * 8) + (rate * 2 * (jam - 8)), 2)

    elif jenis == "public holiday":
        if jam <= 8:
            return round(rate * 2 * jam, 2)
        else:
            return round((rate * 2 * 8) + (rate * 3 * (jam - 8)), 2)

    return 0

# ==========================
# INLINE BUTTONS
# ==========================
def send_main_buttons(chat_id):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🏢 Weekday", callback_data="weekday"),
        types.InlineKeyboardButton("📅 Weekend", callback_data="weekend"),
        types.InlineKeyboardButton("🎉 Public Holiday", callback_data="ph"),
        types.InlineKeyboardButton("💰 Total", callback_data="total"),
    )
    bot.send_message(chat_id, "Sila pilih jenis OT:", reply_markup=markup)

# ==========================
# /start
# ==========================
@bot.message_handler(commands=["start"])
def start(message):
    user_sessions[message.chat.id] = {
        "rate": None,
        "weekday": 0.0,
        "weekend": 0.0,
        "ph": 0.0,
        "waiting_for": None,
    }
    bot.send_message(
        message.chat.id,
        "👋 Hai! Ini *DBSB OT Calculator*.\n"
        "Masukkan kadar OT sejam (contoh: 10.5)\n\n"
        "Bantuan: /help | Reset: /reset\n"
        "Administrator: @syafiqqsuhaimii",
        parse_mode="Markdown"
    )

# ==========================
# /help
# ==========================
@bot.message_handler(commands=["help"])
def help_cmd(message):
    bot.send_message(
        message.chat.id,
        "📘 *Cara guna:*\n"
        "1) /start → masukkan *rate sejam* (cth: `12.5`).\n"
        "2) Pilih butang:\n"
        "   • 🏢 *Weekday* → balas `OT1 OT2 OT3` (cth: `2 1 0`) di mana OT1=3j, OT2=4j, OT3=5j.\n"
        "   • 📅 *Weekend* → balas *bilangan hari* (1 hari = 8 jam), cth: `2`.\n"
        "   • 🎉 *Public Holiday* → balas *jumlah jam*, cth: `9`.\n"
        "   • 💰 *Total* → lihat ringkasan kiraan.\n\n"
        "🔁 /reset untuk kosongkan data & masukkan rate baru.\n"
        "👨‍💼 Administrator: @syafiqqsuhaimii",
        parse_mode="Markdown"
    )

# ==========================
# /reset
# ==========================
@bot.message_handler(commands=["reset"])
def reset_cmd(message):
    user_sessions[message.chat.id] = {
        "rate": None,
        "weekday": 0.0,
        "weekend": 0.0,
        "ph": 0.0,
        "waiting_for": None,
    }
    bot.send_message(
        message.chat.id,
        "♻️ Data anda telah direset.\n"
        "Sila masukkan semula *rate sejam* (cth: `10.5`).\n"
        "Administrator: @syafiqqsuhaimii",
        parse_mode="Markdown"
    )

# ==========================
# SET RATE (sekali sahaja)
# ==========================
@bot.message_handler(func=lambda m: m.text.replace(".", "", 1).isdigit()
                     and (user_sessions.get(m.chat.id, {}).get("rate") is None))
def set_rate(message):
    rate = float(message.text)
    user_sessions[message.chat.id]["rate"] = rate
    bot.send_message(message.chat.id, f"✅ Rate OT diset: RM {rate:.2f}/jam")
    send_main_buttons(message.chat.id)

# ==========================
# CALLBACK HANDLER (inline buttons)
# ==========================
@bot.callback_query_handler(func=lambda call: True)
def callback(call):
    chat_id = call.message.chat.id
    session = user_sessions.get(chat_id)

    if not session or session["rate"] is None:
        bot.send_message(chat_id, "⚠️ Sila set rate dulu (contoh: 10.5)")
        return

    jenis = call.data
    session["waiting_for"] = jenis

    if jenis == "weekday":
        bot.send_message(
            chat_id,
            "Masukkan hari untuk OT1, OT2, OT3.\n"
            "Contoh: `2 1 0`\n"
            "Format: OT1 OT2 OT3",
            parse_mode="Markdown"
        )

    elif jenis == "weekend":
        bot.send_message(
            chat_id,
            "Masukkan *bilangan hari* weekend.\n"
            "1 hari = 8 jam.\n"
            "Contoh: `2`",
            parse_mode="Markdown"
        )

    elif jenis == "ph":
        bot.send_message(
            chat_id,
            "Masukkan *jumlah jam* OT Public Holiday.\n"
            "Contoh: `10`",
            parse_mode="Markdown"
        )

    elif jenis == "total":
        msg = (
            f"📊 Ringkasan OT:\n"
            f"🏢 Weekday: RM {session['weekday']:.2f}\n"
            f"📅 Weekend: RM {session['weekend']:.2f}\n"
            f"🎉 Public Holiday: RM {session['ph']:.2f}\n\n"
            f"💰 Total: RM {session['weekday'] + session['weekend'] + session['ph']:.2f}"
        )
        bot.send_message(chat_id, msg)

# ==========================
# USER INPUT (selepas tekan button)
# ==========================
@bot.message_handler(func=lambda m: True)
def handle_user_input(message):
    chat_id = message.chat.id
    session = user_sessions.get(chat_id)

    if not session or not session["waiting_for"]:
        return

    jenis = session["waiting_for"]
    rate = session["rate"]

    try:
        if jenis == "weekday":
            parts = list(map(int, message.text.split()))
            if len(parts) != 3:
                bot.send_message(chat_id, "❌ Format salah. Contoh: 2 1 0")
                return

            total = 0.0
            reply = "💰 Weekday:\n"
            for i, key in enumerate(["OT1", "OT2", "OT3"]):
                jam = PRESET_WEEKDAY[key]
                hari = parts[i]
                subtotal = kira_ot(rate, jam, "weekday") * hari
                reply += f"{key} ({jam}j × {hari}h): RM {subtotal:.2f}\n"
                total += subtotal

            session["weekday"] += total
            bot.send_message(chat_id, reply + f"\n✅ Total Weekday: RM {total:.2f}")

        elif jenis == "weekend":
            hari = int(message.text)
            subtotal = kira_ot(rate, 8, "weekend") * hari
            session["weekend"] += subtotal
            bot.send_message(chat_id, f"💰 Weekend: {hari} hari × 8j = RM {subtotal:.2f}")

        elif jenis == "ph":
            jam = float(message.text)
            subtotal = kira_ot(rate, jam, "public holiday")
            session["ph"] += subtotal
            bot.send_message(chat_id, f"💰 Public Holiday: RM {subtotal:.2f}")

    except Exception as e:
        bot.send_message(
            chat_id,
            "❌ Format salah. Masukkan nombor sahaja.\n"
            "Jika perlukan bantuan, hubungi admin: @syafiqqsuhaimii"
        )
        print("Error:", e, file=sys.stderr)

    finally:
        session["waiting_for"] = None
        send_main_buttons(chat_id)

# ==========================
# FLASK WEBHOOK
# ==========================
app = Flask(__name__)

@app.get("/")
def home():
    return "Bot is running!"

@app.post("/webhook")
def webhook():
    raw = request.data.decode("utf-8")
    print("✅ /webhook received:", raw[:400], file=sys.stdout, flush=True)
    try:
        update = telebot.types.Update.de_json(raw)
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
