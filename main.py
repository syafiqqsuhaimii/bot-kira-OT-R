import os
import telebot
from telebot import types
from flask import Flask, request

BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN not set")

bot = telebot.TeleBot(BOT_TOKEN)

user_sessions = {}
PRESET_WEEKDAY = {"OT1": 3, "OT2": 4, "OT3": 5}

def kira_ot(rate, jam, jenis):
    rate = float(rate); jam = float(jam)
    if jenis == "weekday":
        return round(rate * 1.5 * jam, 2)
    elif jenis == "weekend":
        if jam <= 4: return round(rate * 0.5 * jam, 2)
        if jam <= 8: return round(rate * jam, 2)
        return round((rate*8) + (rate*2*(jam-8)), 2)
    elif jenis == "public holiday":
        if jam <= 8: return round(rate * 2 * jam, 2)
        return round((rate*2*8) + (rate*3*(jam-8)), 2)
    return 0

def send_main_buttons_inline(chat_id):
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("🏢 Weekday", callback_data="weekday"),
        types.InlineKeyboardButton("📅 Weekend", callback_data="weekend"),
        types.InlineKeyboardButton("🎉 Public Holiday", callback_data="ph"),
        types.InlineKeyboardButton("💰 Total", callback_data="total"),
    )
    bot.send_message(chat_id, "Sila pilih jenis OT:", reply_markup=kb)

@bot.message_handler(commands=["start"])
def start(m):
    user_sessions[m.chat.id] = {
        "rate": None,
        "weekday": 0.0,
        "weekend": 0.0,
        "ph": 0.0,
        "waiting_for": None
    }
    bot.send_message(m.chat.id, "👋 Hai! Masukkan kadar OT sejam (contoh: 10.5)")

@bot.message_handler(func=lambda msg: msg.text.replace(".", "", 1).isdigit() and user_sessions.get(msg.chat.id, {}).get("rate") is None)
def set_rate(m):
    rate = float(m.text)
    user_sessions[m.chat.id]["rate"] = rate
    bot.send_message(m.chat.id, f"✅ Rate diset: RM {rate:.2f}/jam")
    send_main_buttons_inline(m.chat.id)

@bot.callback_query_handler(func=lambda c: True)
def on_button(c):
    chat_id = c.message.chat.id
    s = user_sessions.get(chat_id)

    if not s or s["rate"] is None:
        bot.send_message(chat_id, "⚠️ Sila set rate dulu.")
        return

    if c.data == "weekday":
        s["waiting_for"] = "weekday"
     bot.send_message(chat_id,
    "Masukkan hari untuk OT1, OT2, OT3.\n"
    "Contoh: `2 1 0`\nFormat: OT1 OT2 OT3",
    parse_mode="Markdown"
)

    elif c.data == "weekend":
        s["waiting_for"] = "weekend"
        bot.send_message(chat_id, "Masukkan bilangan hari weekend (1 hari = 8 jam). Contoh: `2`")

    elif c.data == "ph":
        s["waiting_for"] = "ph"
        bot.send_message(chat_id, "Masukkan jumlah jam OT Public Holiday. Contoh: `10`")

    elif c.data == "total":
        total_all = s["weekday"] + s["weekend"] + s["ph"]
        bot.send_message(
            chat_id,
            f"📊 Ringkasan OT:
"
            f"🏢 Weekday: RM {s['weekday']:.2f}
"
            f"📅 Weekend: RM {s['weekend']:.2f}
"
            f"🎉 Public Holiday: RM {s['ph']:.2f}

"
            f"💰 Total Keseluruhan: RM {total_all:.2f}"
        )

@bot.message_handler(func=lambda m: True)
def handle_inputs(m):
    chat_id = m.chat.id
    s = user_sessions.get(chat_id)
    if not s or not s["waiting_for"]:
        return

    rate = s["rate"]

    try:
        if s["waiting_for"] == "weekday":
            vals = list(map(int, m.text.strip().split()))
            if len(vals) != 3:
                bot.send_message(chat_id, "❌ Format salah. Contoh: 2 1 0")
                return
            total = 0
            msg = "💰 Weekday:
"
            for i, key in enumerate(["OT1", "OT2", "OT3"]):
                jam = PRESET_WEEKDAY[key]
                hari = vals[i]
                sub = kira_ot(rate, jam, "weekday") * hari
                msg += f"{key} ({jam}j × {hari}h): RM {sub:.2f}
"
                total += sub
            s["weekday"] += total
            bot.send_message(chat_id, msg + f"
✅ Total Weekday: RM {total:.2f}")

        elif s["waiting_for"] == "weekend":
            hari = int(m.text.strip())
            sub = kira_ot(rate, 8, "weekend") * hari
            s["weekend"] += sub
            bot.send_message(chat_id, f"💰 Weekend: {hari} hari × 8j = RM {sub:.2f}")

        elif s["waiting_for"] == "ph":
            jam = float(m.text.strip())
            sub = kira_ot(rate, jam, "public holiday")
            s["ph"] += sub
            bot.send_message(chat_id, f"💰 Public Holiday: RM {sub:.2f}")

    except Exception:
        bot.send_message(chat_id, "❌ Format salah. Masukkan nombor.")
        return
    finally:
        s["waiting_for"] = None
        send_main_buttons_inline(chat_id)

app = Flask(__name__)

@app.get("/")
def index():
    return "Bot is running!"

@app.post("/webhook")
def webhook():
    update = telebot.types.Update.de_json(request.data.decode("utf-8"))
    bot.process_new_updates([update])
    return "OK", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    print("✅ Flask running on port", port)
    app.run(host="0.0.0.0", port=port)
