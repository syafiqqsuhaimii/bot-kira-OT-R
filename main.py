import os, sys, logging
import telebot
from telebot import types
from flask import Flask, request

BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN not set")

telebot.logger.setLevel(logging.DEBUG)
bot = telebot.TeleBot(BOT_TOKEN)

# ===== Session =====
# {chat_id: {"rate": float|None, "weekday": float, "weekend": float, "ph": float, "waiting_for": str|None}}
user_sessions = {}
PRESET_WEEKDAY = {"OT1": 3, "OT2": 4, "OT3": 5}

def is_number(s:str)->bool:
    if not s: return False
    s = s.strip().replace(",", ".")
    try: float(s); return True
    except: return False

def kira_ot(rate, jam, jenis):
    rate = float(rate); jam = float(jam)
    if jenis == "weekday":
        return round(rate * 1.5 * jam, 2)
    if jenis == "weekend":
        if jam <= 4: return round(rate*0.5*jam,2)
        if jam <= 8: return round(rate*jam,2)
        return round((rate*8)+(rate*2*(jam-8)),2)
    if jenis == "public holiday":
        if jam <= 8: return round(rate*2*jam,2)
        return round((rate*2*8)+(rate*3*(jam-8)),2)
    return 0

def main_menu():
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("🏢 Weekday","weekday"),
        types.InlineKeyboardButton("📅 Weekend","weekend"),
        types.InlineKeyboardButton("🎉 Public Holiday","ph"),
        types.InlineKeyboardButton("💰 Total","total"),
    )
    kb.add(
        types.InlineKeyboardButton("📘 Help","help"),
        types.InlineKeyboardButton("♻️ Reset","reset"),
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
        "   • Weekday → balas `OT1 OT2 OT3` (cth: 2 1 0) — 3j/4j/5j.\n"
        "   • Weekend → balas bilangan hari (1 hari = 8 jam), cth: 2.\n"
        "   • Public Holiday → balas jumlah jam, cth: 9.\n"
        "   • Total → ringkasan.\n"
        "Admin: @syafiqqsuhaimii",
        reply_markup=main_menu()
    )

def ensure_session(cid):
    if cid not in user_sessions:
        user_sessions[cid] = {"rate": None, "weekday": 0.0, "weekend": 0.0, "ph": 0.0, "waiting_for": None}
    return user_sessions[cid]

# ===== Optional commands =====
@bot.message_handler(commands=["help"])
def _h(m): send_help(m.chat.id)

@bot.message_handler(commands=["reset"])
def _r(m):
    ensure_session(m.chat.id)
    user_sessions[m.chat.id] = {"rate": None, "weekday": 0.0, "weekend": 0.0, "ph": 0.0, "waiting_for": "rate"}
    bot.send_message(m.chat.id,"Masukkan kadar OT sejam (contoh: 10.5)")

@bot.message_handler(commands=["ping"])
def _p(m): bot.send_message(m.chat.id,"pong")

# ===== Handle inline (SET STATE) =====
@bot.callback_query_handler(func=lambda c: True)
def callbacks(c):
    cid = c.message.chat.id
    sess = ensure_session(cid)
    try: bot.answer_callback_query(c.id)
    except Exception as e: print("answerCallback err:",e, file=sys.stderr, flush=True)

    data = c.data
    if data == "help": return send_help(cid)
    if data == "reset":
        user_sessions[cid] = {"rate": None, "weekday": 0.0, "weekend": 0.0, "ph": 0.0, "waiting_for": "rate"}
        return bot.send_message(cid,"Masukkan kadar OT sejam (contoh: 10.5)")

    if not sess.get("rate"):
        sess["waiting_for"] = "rate"
        return bot.send_message(cid,"⚠️ Masukkan rate sejam dulu (cth: 10.5).")

    sess["waiting_for"] = data
    if data == "weekday":
        bot.send_message(cid,"Masukkan hari untuk OT1, OT2, OT3.\nContoh: 2 1 0\nFormat: OT1 OT2 OT3")
    elif data == "weekend":
        bot.send_message(cid,"Masukkan bilangan hari weekend (1 hari = 8 jam).\nContoh: 2")
    elif data == "ph":
        bot.send_message(cid,"Masukkan jumlah jam OT Public Holiday.\nContoh: 10")
    elif data == "total":
        bot.send_message(
            cid,
            "📊 Ringkasan OT:\n"
            f"🏢 Weekday: RM {sess['weekday']:.2f}\n"
            f"📅 Weekend: RM {sess['weekend']:.2f}\n"
            f"🎉 Public Holiday: RM {sess['ph']:.2f}\n\n"
            f"💰 Total: RM {sess['weekday']+sess['weekend']+sess['ph']:.2f}",
            reply_markup=main_menu()
        )

# ===== Flask webhook with FULL inline + inputs handling =====
app = Flask(__name__)

@app.get("/")
def home(): return "Bot is running!"

@app.post("/webhook")
def webhook():
    raw = request.get_data(as_text=True)
    print("✅ /webhook received:", raw[:400], file=sys.stdout, flush=True)
    try:
        update = telebot.types.Update.de_json(raw)
        if not update:
            return "OK", 200

        # ---- CALLBACK: biar handler urus, tapi state dah set di atas ----
        if getattr(update, "callback_query", None):
            cq = update.callback_query
            print(f"🔔 callback_query data='{cq.data}' from chat={cq.message.chat.id}", file=sys.stdout, flush=True)
            # terus pass ke handlers supaya callbacks() jalan segera
            bot.process_new_updates([update])
            return "OK", 200

        # ---- MESSAGE: direct /start, /ping, rate, & OT inputs ----
        if getattr(update, "message", None):
            t_raw = (update.message.text or "").strip()
            t = t_raw.lower()
            cid = update.message.chat.id
            sess = ensure_session(cid)

            if t == "/start":
                user_sessions[cid] = {"rate": None, "weekday": 0.0, "weekend": 0.0, "ph": 0.0, "waiting_for": "rate"}
                bot.send_message(cid,"Masukkan kadar OT sejam (contoh: 10.5)")
                print("✅ Direct /start → ask rate", flush=True)
                return "OK", 200

            if t == "/ping":
                bot.send_message(cid,"pong ✅ direct")
                print("✅ Direct /ping", flush=True)
                return "OK", 200

            # 1) RATE
            if (sess.get("waiting_for") == "rate" or sess.get("rate") is None) and is_number(t_raw):
                rate = float(t_raw.replace(",", "."))
                sess["rate"] = rate
                sess["waiting_for"] = None
                bot.send_message(cid, f"✅ Rate OT diset: RM {rate:.2f}/jam")
                send_main_buttons(cid)
                print(f"✅ Rate set {rate} for {cid}", flush=True)
                return "OK", 200

            # 2) INPUTS MENGIKUT STATE — PROSES DI SINI TERUS
            wf = sess.get("waiting_for")
            if wf == "weekday":
                parts = [p for p in t_raw.split() if p]
                if len(parts) != 3 or not all(p.lstrip("+-").isdigit() for p in parts):
                    bot.send_message(cid, "❌ Format salah. Contoh betul: 2 1 0")
                    return "OK", 200
                nums = list(map(int, parts))
                total = 0.0; lines = []
                for i, key in enumerate(["OT1","OT2","OT3"]):
                    jam = PRESET_WEEKDAY[key]; hari = nums[i]
                    subtotal = kira_ot(sess["rate"], jam, "weekday") * hari
                    total += subtotal
                    lines.append(f"{key} ({jam}j × {hari}h): RM {subtotal:.2f}")
                sess["weekday"] += total
                sess["waiting_for"] = None
                bot.send_message(cid, "💰 Weekday:\n" + "\n".join(lines) + f"\n\n✅ Total Weekday: RM {total:.2f}", reply_markup=main_menu())
                return "OK", 200

            if wf == "weekend":
                if not t_raw.lstrip("+-").isdigit():
                    bot.send_message(cid, "❌ Sila masukkan bilangan hari (cth: 2)")
                    return "OK", 200
                hari = int(t_raw)
                subtotal = kira_ot(sess["rate"], 8, "weekend") * hari
                sess["weekend"] += subtotal
                sess["waiting_for"] = None
                bot.send_message(cid, f"💰 Weekend: {hari} hari × 8j = RM {subtotal:.2f}", reply_markup=main_menu())
                return "OK", 200

            if wf == "ph":
                if not is_number(t_raw):
                    bot.send_message(cid, "❌ Sila masukkan jumlah jam (cth: 9.5)")
                    return "OK", 200
                jam = float(t_raw.replace(",", "."))
                subtotal = kira_ot(sess["rate"], jam, "public holiday")
                sess["ph"] += subtotal
                sess["waiting_for"] = None
                bot.send_message(cid, f"💰 Public Holiday: RM {subtotal:.2f}", reply_markup=main_menu())
                return "OK", 200

            # 3) Tiada state: jika rate ada, paparkan menu
            if sess.get("rate") is not None:
                send_main_buttons(cid)
                return "OK", 200

        # fallback
        bot.process_new_updates([update])
        print("✅ Update processed OK (fallback)", flush=True)
    except Exception as e:
        print("❌ Error:", repr(e), file=sys.stderr, flush=True)
    return "OK", 200

# ===== Run (Render uses gunicorn) =====
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    print("✅ Flask running on", port)
    app.run(host="0.0.0.0", port=port)
