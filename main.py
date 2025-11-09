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
bot = telebot.TeleBot(BOT_TOKEN, parse_mode=None)  # tiada global Markdown

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
        "📘 Cara guna:\n"
        "1) Taip rate sejam (cth: 12.5).\n"
        "2) Butang:\n"
        "   • Weekday → balas 'OT1 OT2 OT3' (cth: 2 1 0) — 3j/4j/5j.\n"
        "   • Weekend → balas bilangan hari (1 hari = 8 jam), cth: 2.\n"
        "   • Public Holiday → balas jumlah jam, cth: 9.\n"
        "   • Total → ringkasan kiraan.\n"
        "Admin: @syafiqqsuhaimii",
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
    bot.send_message(message.chat.id, "pong")

# ==========================
# UNIVERSAL HANDLER (teks biasa)
# ==========================
@bot.message_handler(func=lambda m: True)
def handle_all(message):
    chat_id = message.chat.id
    text_raw = (message.text or "")
    text = text_raw.strip()
    print(f"🔎 handle_all text='{text}' chat_id={chat_id}", file=sys.stdout, flush=True)

    # Fallback commands
    if text.startswith("/"):
        cmd = text.split()[0].lower()
        if cmd == "/start":
            do_reset(chat_id, ask_rate=True);  return
        if cmd == "/help":
            return send_help(chat_id)
        if cmd == "/reset":
            return do_reset(chat_id, ask_rate=True)
        if cmd == "/ping":
            return ping(message)

    # Session
    session = user_sessions.get(chat_id)
    if not session:
        do_reset(chat_id, ask_rate=True);  return

    waiting = session.get("waiting_for")

    # Tiada state khusus
    if not waiting:
        # Jika rate dah ada & user hantar apa-apa teks → paparkan menu
        if session.get("rate") is not None:
            return send_main_buttons(chat_id)
        # Jika tiada rate, minta rate semula
        session["waiting_for"] = "rate"
        bot.send_message(chat_id, "Masukkan kadar OT sejam (contoh: 10.5)")
        return

    # ===== STATE MACHINE =====
    # 1) RATE (di webhook juga diproses, tapi kita ulang di sini supaya confirm)
    if waiting == "rate":
        if not is_number(text):
            bot.send_message(chat_id, "❌ Sila masukkan nombor rate sejam (cth: 10.5)")
            return
        rate = float(text.replace(",", "."))
        session["rate"] = rate
        session["waiting_for"] = None
        bot.send_message(chat_id, f"✅ Rate OT diset: RM {rate:.2f}/jam")
        return send_main_buttons(chat_id)

    # 2) WEEKDAY / WEEKEND / PH
    rate = session["rate"]
    try:
        if waiting == "weekday":
            bot.send_message(chat_id, f"📥 Diterima (weekday): '{text}'")  # debug visible
            parts = [p for p in text.split() if p]
            if len(parts) != 3 or not all(p.lstrip("+-").isdigit() for p in parts):
                bot.send_message(chat_id, "❌ Format salah. Contoh betul: 2 1 0")
                return
            nums = list(map(int, parts))
            print(f"🧪 weekday parts={nums}", file=sys.stdout, flush=True)

            total = 0.0
            lines = []
            for i, key in enumerate(["OT1", "OT2", "OT3"]):
                jam = PRESET_WEEKDAY[key]
                hari = nums[i]
                subtotal = kira_ot(rate, jam, "weekday") * hari
                lines.append(f"{key} ({jam}j × {hari}h): RM {subtotal:.2f}")
                total += subtotal

            session["weekday"] += total
            reply = "💰 Weekday:\n" + "\n".join(lines) + f"\n\n✅ Total Weekday: RM {total:.2f}"
            bot.send_message(chat_id, reply, reply_markup=main_menu())

        elif waiting == "weekend":
            bot.send_message(chat_id, f"📥 Diterima (weekend): '{text}'")  # debug visible
            if not text.lstrip("+-").isdigit():
                bot.send_message(chat_id, "❌ Sila masukkan bilangan hari (cth: 2)")
                return
            hari = int(text)
            subtotal = kira_ot(rate, 8, "weekend") * hari
            session["weekend"] += subtotal
            bot.send_message(chat_id, f"💰 Weekend: {hari} hari × 8j = RM {subtotal:.2f}", reply_markup=main_menu())

        elif waiting == "ph":
            bot.send_message(chat_id, f"📥 Diterima (public holiday): '{text}'")  # debug visible
            if not is_number(text):
                bot.send_message(chat_id, "❌ Sila masukkan jumlah jam (cth: 9.5)")
                return
            jam = float(text.replace(",", "."))
            subtotal = kira_ot(rate, jam, "public holiday")
            session["ph"] += subtotal
            bot.send_message(chat_id, f"💰 Public Holiday: RM {subtotal:.2f}", reply_markup=main_menu())

    except Exception as e:
        bot.send_message(
            chat_id,
            "❌ Ralat tidak dijangka. Cuba lagi.\n(Jika berulang, tekan ♻️ Reset)",
            reply_markup=main_menu()
        )
        print("❌ Handle OT input error:", repr(e), file=sys.stderr, flush=True)
    finally:
        session["waiting_for"] = None

# ==========================
# FLASK WEBHOOK — direct handle /start, RATE & CALLBACK
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

        if update:

            # ---- CALLBACK: terus di sini ----
            if getattr(update, "callback_query", None):
                cq = update.callback_query
                chat_id = cq.message.chat.id
                data = cq.data
                print(f"🔔 callback_query data='{data}' from chat={chat_id}", file=sys.stdout, flush=True)

                try:
                    bot.answer_callback_query(cq.id)
                except Exception as e:
                    print("❌ answer_callback_query failed:", repr(e), file=sys.stderr, flush=True)

                # Pastikan sesi
                session = user_sessions.get(chat_id)
                if data == "help":
                    send_help(chat_id);  return "OK", 200
                if data == "reset":
                    do_reset(chat_id, ask_rate=True);  return "OK", 200

                if not session or session.get("rate") is None:
                    user_sessions.setdefault(chat_id, {"rate": None, "weekday": 0.0, "weekend": 0.0, "ph": 0.0, "waiting_for": None})
                    user_sessions[chat_id]["waiting_for"] = "rate"
                    bot.send_message(chat_id, "⚠️ Sila masukkan rate sejam dahulu (cth: 10.5).")
                    return "OK", 200

                # Set state & minta input
                session["waiting_for"] = data
                if data == "weekday":
                    bot.send_message(chat_id, "Masukkan hari untuk OT1, OT2, OT3.\nContoh: 2 1 0\nFormat: OT1 OT2 OT3")
                elif data == "weekend":
                    bot.send_message(chat_id, "Masukkan bilangan hari weekend (1 hari = 8 jam).\nContoh: 2")
                elif data == "ph":
                    bot.send_message(chat_id, "Masukkan jumlah jam OT Public Holiday.\nContoh: 10")
                elif data == "total":
                    msg = (
                        f"📊 Ringkasan OT:\n"
                        f"🏢 Weekday: RM {session['weekday']:.2f}\n"
                        f"📅 Weekend: RM {session['weekend']:.2f}\n"
                        f"🎉 Public Holiday: RM {session['ph']:.2f}\n\n"
                        f"💰 Total: RM {session['weekday'] + session['weekend'] + session['ph']:.2f}"
                    )
                    bot.send_message(chat_id, msg, reply_markup=main_menu())
                return "OK", 200

            # ---- MESSAGE: /start, /ping & RATE direct ----
            if getattr(update, "message", None):
                t_raw = (update.message.text or "").strip()
                t = t_raw.lower()
                cid = update.message.chat.id

                if cid not in user_sessions:
                    user_sessions[cid] = {"rate": None, "weekday": 0.0, "weekend": 0.0, "ph": 0.0, "waiting_for": None}

                if t == "/start":
                    user_sessions[cid] = {"rate": None, "weekday": 0.0, "weekend": 0.0, "ph": 0.0, "waiting_for": "rate"}
                    bot.send_message(cid, "Masukkan kadar OT sejam (contoh: 10.5)")
                    print("✅ Direct /start → ask rate", file=sys.stdout, flush=True)
                    return "OK", 200

                if t == "/ping":
                    bot.send_message(cid, "pong ✅ direct")
                    print("✅ Direct /ping reply sent", file=sys.stdout, flush=True)
                    return "OK", 200

                # RATE direct
                sess = user_sessions.get(cid, {})
                waiting = sess.get("waiting_for")
                if (waiting == "rate" or sess.get("rate") is None) and is_number(t_raw):
                    rate = float(t_raw.replace(",", "."))
                    sess["rate"] = rate
                    sess["waiting_for"] = None
                    bot.send_message(cid, f"✅ Rate OT diset: RM {rate:.2f}/jam")
                    send_main_buttons(cid)
                    print(f"✅ Direct rate set to {rate} for {cid}", file=sys.stdout, flush=True)
                    return "OK", 200

        # Fallback: pass ke handlers biasa
        bot.process_new_updates([update])
        print("✅ Update processed OK (fallback handlers)", file=sys.stdout, flush=True)
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
