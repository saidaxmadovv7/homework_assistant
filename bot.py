"""
📚 SchoolBot - Telegram Homework Manager
pyTelegramBotAPI versiyasi - Python 3.14 bilan ishlaydi
"""

import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
import sqlite3
import os
import threading
import time
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

# ─── Config ──────────────────────────────────────────────────────────────────
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
DB_PATH = "schoolbot.db"

bot = telebot.TeleBot(BOT_TOKEN)

# ─── Database ────────────────────────────────────────────────────────────────

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS homework (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id     INTEGER NOT NULL,
        username    TEXT,
        subject     TEXT NOT NULL,
        description TEXT NOT NULL,
        deadline    TEXT,
        is_done     INTEGER DEFAULT 0,
        created_at  TEXT NOT NULL
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS group_settings (
        chat_id         INTEGER PRIMARY KEY,
        reminder_hour   INTEGER DEFAULT 20,
        reminder_minute INTEGER DEFAULT 0,
        reminders_on    INTEGER DEFAULT 1
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS activity (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id    INTEGER NOT NULL,
        user_id    INTEGER NOT NULL,
        username   TEXT,
        created_at TEXT NOT NULL
    )""")
    conn.commit()
    conn.close()


def db():
    """Return a new DB connection."""
    return sqlite3.connect(DB_PATH)


# ─── User state (for multi-step input) ───────────────────────────────────────
# {user_id: {"step": ..., "data": {...}}}
user_state = {}


# ─── Keyboards ───────────────────────────────────────────────────────────────

def main_menu():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(KeyboardButton("➕ Add Homework"), KeyboardButton("📋 View Homework"))
    kb.row(KeyboardButton("📅 Today's Tasks"), KeyboardButton("⏰ Set Reminder"))
    kb.row(KeyboardButton("🏆 Leaderboard"),   KeyboardButton("ℹ️ Help"))
    return kb


SUBJECTS = [
    "📐 Math", "📖 Literature", "🔬 Science", "🌍 Geography",
    "🗣️ English", "💻 IT/CS", "🎨 Art", "🏃 PE",
    "🧪 Chemistry", "⚗️ Physics", "📜 History", "🎵 Music",
]

def subject_keyboard():
    kb = InlineKeyboardMarkup(row_width=3)
    buttons = [InlineKeyboardButton(s, callback_data=f"subj|{s}") for s in SUBJECTS]
    kb.add(*buttons)
    kb.add(InlineKeyboardButton("✏️ Type manually", callback_data="subj|custom"))
    kb.add(InlineKeyboardButton("❌ Cancel", callback_data="cancel"))
    return kb


def deadline_keyboard():
    today = datetime.now()
    kb = InlineKeyboardMarkup(row_width=2)
    options = [
        ("📅 Today",     today.strftime("%Y-%m-%d")),
        ("📅 Tomorrow",  (today + timedelta(days=1)).strftime("%Y-%m-%d")),
        ("📅 In 2 days", (today + timedelta(days=2)).strftime("%Y-%m-%d")),
        ("📅 In 3 days", (today + timedelta(days=3)).strftime("%Y-%m-%d")),
        ("📅 Next week", (today + timedelta(days=7)).strftime("%Y-%m-%d")),
        ("⏭️ No deadline","none"),
    ]
    kb.add(*[InlineKeyboardButton(label, callback_data=f"dl|{date}") for label, date in options])
    kb.add(InlineKeyboardButton("✏️ Enter date manually", callback_data="dl|custom"))
    return kb


def reminder_keyboard():
    kb = InlineKeyboardMarkup(row_width=3)
    times = [("17:00","17:00"),("18:00","18:00"),("19:00","19:00"),
             ("20:00","20:00"),("21:00","21:00"),("22:00","22:00")]
    kb.add(*[InlineKeyboardButton(t, callback_data=f"rt|{t}") for t, _ in times])
    kb.add(InlineKeyboardButton("🔕 Disable reminders", callback_data="rt|off"))
    return kb


def hw_action_keyboard(hw_id, is_done=False):
    kb = InlineKeyboardMarkup(row_width=2)
    if not is_done:
        kb.add(InlineKeyboardButton("✅ Mark Done", callback_data=f"done|{hw_id}"))
    kb.add(InlineKeyboardButton("🗑️ Delete", callback_data=f"del|{hw_id}"))
    return kb


# ─── Formatters ──────────────────────────────────────────────────────────────

def fmt_deadline(deadline):
    if not deadline:
        return "📅 No deadline"
    try:
        dt = datetime.strptime(deadline, "%Y-%m-%d")
        delta = (dt.date() - datetime.now().date()).days
        fmt = dt.strftime("%d %b %Y")
        if delta < 0:   return f"⚠️ Overdue ({fmt})"
        elif delta == 0: return f"🔴 Due today! ({fmt})"
        elif delta == 1: return f"🟡 Tomorrow ({fmt})"
        elif delta <= 3: return f"🟠 In {delta} days ({fmt})"
        else:            return f"🟢 {fmt}"
    except:
        return f"📅 {deadline}"


def fmt_hw(hw):
    return (f"📌 <b>#{hw[0]} {hw[3]}</b>\n"
            f"   {hw[4]}\n"
            f"   {fmt_deadline(hw[5])} · by {hw[2] or 'unknown'}")


# ─── Database helpers ─────────────────────────────────────────────────────────

def add_hw(chat_id, user_id, username, subject, description, deadline):
    with db() as conn:
        c = conn.cursor()
        c.execute("INSERT INTO homework (chat_id,username,subject,description,deadline,created_at) VALUES (?,?,?,?,?,?)",
                  (chat_id, username, subject, description, deadline, datetime.now().isoformat()))
        hw_id = c.lastrowid
        c.execute("INSERT INTO activity (chat_id,user_id,username,created_at) VALUES (?,?,?,?)",
                  (chat_id, user_id, username, datetime.now().isoformat()))
        conn.commit()
    return hw_id


def get_hw(chat_id):
    with db() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM homework WHERE chat_id=? AND is_done=0 ORDER BY deadline ASC", (chat_id,))
        return c.fetchall()


def get_today_hw(chat_id):
    today = datetime.now().strftime("%Y-%m-%d")
    with db() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM homework WHERE chat_id=? AND is_done=0 AND (deadline=? OR deadline<?)",
                  (chat_id, today, today))
        return c.fetchall()


def get_tomorrow_hw(chat_id):
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    with db() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM homework WHERE chat_id=? AND is_done=0 AND deadline=?", (chat_id, tomorrow))
        return c.fetchall()


def mark_done_db(hw_id, chat_id):
    with db() as conn:
        c = conn.cursor()
        c.execute("UPDATE homework SET is_done=1 WHERE id=? AND chat_id=?", (hw_id, chat_id))
        conn.commit()
        return c.rowcount > 0


def delete_hw_db(hw_id, chat_id):
    with db() as conn:
        c = conn.cursor()
        c.execute("DELETE FROM homework WHERE id=? AND chat_id=?", (hw_id, chat_id))
        conn.commit()
        return c.rowcount > 0


def get_settings(chat_id):
    with db() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM group_settings WHERE chat_id=?", (chat_id,))
        row = c.fetchone()
        if not row:
            c.execute("INSERT INTO group_settings (chat_id) VALUES (?)", (chat_id,))
            conn.commit()
            return (chat_id, 20, 0, 1)
        return row


def save_reminder(chat_id, hour, minute):
    with db() as conn:
        c = conn.cursor()
        c.execute("""INSERT INTO group_settings (chat_id,reminder_hour,reminder_minute,reminders_on)
                     VALUES (?,?,?,1)
                     ON CONFLICT(chat_id) DO UPDATE SET
                     reminder_hour=excluded.reminder_hour,
                     reminder_minute=excluded.reminder_minute,
                     reminders_on=1""", (chat_id, hour, minute))
        conn.commit()


def disable_reminders(chat_id):
    with db() as conn:
        c = conn.cursor()
        c.execute("""INSERT INTO group_settings (chat_id,reminders_on) VALUES (?,0)
                     ON CONFLICT(chat_id) DO UPDATE SET reminders_on=0""", (chat_id,))
        conn.commit()


def get_leaderboard(chat_id):
    with db() as conn:
        c = conn.cursor()
        c.execute("""SELECT username, COUNT(*) as cnt FROM activity
                     WHERE chat_id=? GROUP BY user_id ORDER BY cnt DESC LIMIT 5""", (chat_id,))
        return c.fetchall()


def all_settings():
    with db() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM group_settings WHERE reminders_on=1")
        return c.fetchall()


# ─── Handlers ─────────────────────────────────────────────────────────────────

@bot.message_handler(commands=["start"])
def cmd_start(msg):
    name = msg.from_user.first_name or "Student"
    get_settings(msg.chat.id)  # init settings
    bot.send_message(msg.chat.id,
        f"👋 Salom <b>{name}</b>! <b>SchoolBot</b> ga xush kelibsiz!\n\n"
        "Darslarni boshqarish uchun quyidagi tugmalardan foydalaning 👇",
        parse_mode="HTML", reply_markup=main_menu())


@bot.message_handler(func=lambda m: m.text == "ℹ️ Help")
def cmd_help(msg):
    bot.send_message(msg.chat.id,
        "📚 <b>SchoolBot — Dars Menejeri</b>\n\n"
        "➕ <b>Add Homework</b> — Yangi dars qo'shish\n"
        "📋 <b>View Homework</b> — Barcha darslarni ko'rish\n"
        "📅 <b>Today's Tasks</b> — Bugungi darslar\n"
        "⏰ <b>Set Reminder</b> — Eslatma vaqtini belgilash\n"
        "🏆 <b>Leaderboard</b> — Eng faol o'quvchilar\n\n"
        "<i>Guruhga qo'shib ishlatish yanada qulay!</i>",
        parse_mode="HTML", reply_markup=main_menu())


# ─── Add Homework ─────────────────────────────────────────────────────────────

@bot.message_handler(func=lambda m: m.text == "➕ Add Homework")
def add_homework_start(msg):
    user_state[msg.from_user.id] = {"step": "subject", "data": {}, "chat_id": msg.chat.id}
    bot.send_message(msg.chat.id, "📚 <b>1/3 — Fanni tanlang:</b>",
                     parse_mode="HTML", reply_markup=subject_keyboard())


@bot.callback_query_handler(func=lambda c: c.data.startswith("subj|"))
def subject_chosen(call):
    uid = call.from_user.id
    subject = call.data.split("|", 1)[1]

    if subject == "custom":
        user_state[uid] = {**user_state.get(uid, {}), "step": "subject_custom",
                           "data": {}, "chat_id": call.message.chat.id}
        bot.edit_message_text("✏️ Fan nomini yozing:", call.message.chat.id, call.message.message_id)
        bot.answer_callback_query(call.id)
        return

    state = user_state.get(uid, {})
    state["data"]["subject"] = subject
    state["step"] = "description"
    user_state[uid] = state

    bot.edit_message_text(
        f"✅ Fan: <b>{subject}</b>\n\n📝 <b>2/3 — Dars tavsifini yozing:</b>\n"
        f"<i>Misol: 12-mashq, 45-bet</i>",
        call.message.chat.id, call.message.message_id, parse_mode="HTML")
    bot.answer_callback_query(call.id)


@bot.callback_query_handler(func=lambda c: c.data.startswith("dl|"))
def deadline_chosen(call):
    uid = call.from_user.id
    value = call.data.split("|", 1)[1]

    if value == "custom":
        user_state[uid]["step"] = "deadline_custom"
        bot.edit_message_text("✏️ Sanani kiriting <b>KK.OO.YYYY</b> formatida:\n<i>Misol: 15.06.2025</i>",
                              call.message.chat.id, call.message.message_id, parse_mode="HTML")
        bot.answer_callback_query(call.id)
        return

    deadline = None if value == "none" else value
    _save_homework(call.from_user, call.message.chat.id, deadline, call.message)
    bot.answer_callback_query(call.id)


def _save_homework(user, chat_id, deadline, edit_msg=None):
    uid = user.id
    state = user_state.pop(uid, {})
    data = state.get("data", {})
    username = f"@{user.username}" if user.username else user.first_name

    hw_id = add_hw(chat_id, uid, username, data["subject"], data["description"], deadline)
    dl_label = f" ({deadline})" if deadline else ""
    text = (f"✅ <b>Dars qo'shildi!</b> #{hw_id}\n\n"
            f"📚 <b>{data['subject']}</b>{dl_label}\n{data['description']}\n\n"
            f"<i>Bu chatdagi barcha o'quvchilar ko'ra oladi.</i>")

    if edit_msg:
        bot.edit_message_text(text, edit_msg.chat.id, edit_msg.message_id, parse_mode="HTML")
    else:
        bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=main_menu())


# ─── View Homework ────────────────────────────────────────────────────────────

@bot.message_handler(func=lambda m: m.text == "📋 View Homework")
def view_homework(msg):
    items = get_hw(msg.chat.id)
    if not items:
        bot.send_message(msg.chat.id, "✅ <b>Barcha darslar bajarilgan!</b>", parse_mode="HTML")
        return
    bot.send_message(msg.chat.id, f"📋 <b>Kutilayotgan darslar ({len(items)} ta):</b>", parse_mode="HTML")
    for hw in items:
        bot.send_message(msg.chat.id, fmt_hw(hw), parse_mode="HTML",
                         reply_markup=hw_action_keyboard(hw[0]))


@bot.message_handler(func=lambda m: m.text == "📅 Today's Tasks")
def today_tasks(msg):
    items = get_today_hw(msg.chat.id)
    if not items:
        bot.send_message(msg.chat.id, "✅ <b>Bugun uchun dars yo'q!</b>", parse_mode="HTML")
        return
    bot.send_message(msg.chat.id, f"📅 <b>Bugungi darslar ({len(items)} ta):</b>", parse_mode="HTML")
    for hw in items:
        bot.send_message(msg.chat.id, fmt_hw(hw), parse_mode="HTML",
                         reply_markup=hw_action_keyboard(hw[0]))


# ─── Homework Actions ─────────────────────────────────────────────────────────

@bot.callback_query_handler(func=lambda c: c.data.startswith("done|"))
def mark_done(call):
    hw_id = int(call.data.split("|")[1])
    if mark_done_db(hw_id, call.message.chat.id):
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id,
                                      reply_markup=hw_action_keyboard(hw_id, is_done=True))
        bot.answer_callback_query(call.id, "✅ Bajarildi!")
    else:
        bot.answer_callback_query(call.id, "⚠️ Topilmadi", show_alert=True)


@bot.callback_query_handler(func=lambda c: c.data.startswith("del|"))
def delete_hw(call):
    hw_id = int(call.data.split("|")[1])
    if delete_hw_db(hw_id, call.message.chat.id):
        bot.delete_message(call.message.chat.id, call.message.message_id)
        bot.answer_callback_query(call.id, "🗑️ O'chirildi!")
    else:
        bot.answer_callback_query(call.id, "⚠️ Topilmadi", show_alert=True)


@bot.callback_query_handler(func=lambda c: c.data == "cancel")
def cancel(call):
    uid = call.from_user.id
    user_state.pop(uid, None)
    bot.delete_message(call.message.chat.id, call.message.message_id)
    bot.answer_callback_query(call.id, "Bekor qilindi")


# ─── Reminders ────────────────────────────────────────────────────────────────

@bot.message_handler(func=lambda m: m.text == "⏰ Set Reminder")
def set_reminder(msg):
    s = get_settings(msg.chat.id)
    status = "🟢 Yoqilgan" if s[3] else "🔴 O'chirilgan"
    bot.send_message(msg.chat.id,
        f"⏰ <b>Eslatma sozlamalari</b>\n\nHolat: {status}\nVaqt: <b>{s[1]:02d}:{s[2]:02d}</b>\n\n"
        "Yangi vaqt tanlang:",
        parse_mode="HTML", reply_markup=reminder_keyboard())


@bot.callback_query_handler(func=lambda c: c.data.startswith("rt|"))
def reminder_time(call):
    value = call.data.split("|")[1]
    if value == "off":
        disable_reminders(call.message.chat.id)
        bot.edit_message_text("🔕 <b>Eslatmalar o'chirildi.</b>",
                              call.message.chat.id, call.message.message_id, parse_mode="HTML")
    else:
        h, m = map(int, value.split(":"))
        save_reminder(call.message.chat.id, h, m)
        bot.edit_message_text(f"✅ <b>Eslatma {value} ga belgilandi!</b>\nHar kecha uyga vazifalar haqida xabar beraman.",
                              call.message.chat.id, call.message.message_id, parse_mode="HTML")
    bot.answer_callback_query(call.id)


# ─── Leaderboard ─────────────────────────────────────────────────────────────

@bot.message_handler(func=lambda m: m.text == "🏆 Leaderboard")
def leaderboard(msg):
    entries = get_leaderboard(msg.chat.id)
    if not entries:
        bot.send_message(msg.chat.id, "🏆 <b>Leaderboard</b>\n\nHali faollik yo'q!", parse_mode="HTML")
        return
    medals = ["🥇","🥈","🥉","4️⃣","5️⃣"]
    lines = ["🏆 <b>Eng faol o'quvchilar:</b>\n"]
    for i, (name, cnt) in enumerate(entries):
        lines.append(f"{medals[i]} {name} — <b>{cnt}</b> ta dars qo'shgan")
    bot.send_message(msg.chat.id, "\n".join(lines), parse_mode="HTML")


# ─── Text message router (FSM) ────────────────────────────────────────────────

@bot.message_handler(func=lambda m: m.from_user.id in user_state)
def fsm_router(msg):
    uid = msg.from_user.id
    state = user_state.get(uid, {})
    step = state.get("step")
    chat_id = state.get("chat_id", msg.chat.id)

    if step == "subject_custom":
        state["data"]["subject"] = msg.text.strip()
        state["step"] = "description"
        user_state[uid] = state
        bot.send_message(chat_id, f"✅ Fan: <b>{msg.text.strip()}</b>\n\n📝 <b>2/3 — Tavsifni yozing:</b>",
                         parse_mode="HTML")

    elif step == "description":
        state["data"]["description"] = msg.text.strip()
        state["step"] = "deadline"
        user_state[uid] = state
        bot.send_message(chat_id, "📅 <b>3/3 — Topshiriq muddati:</b>",
                         parse_mode="HTML", reply_markup=deadline_keyboard())

    elif step == "deadline_custom":
        try:
            dt = datetime.strptime(msg.text.strip(), "%d.%m.%Y")
            deadline = dt.strftime("%Y-%m-%d")
            _save_homework(msg.from_user, chat_id, deadline)
        except ValueError:
            bot.send_message(chat_id, "⚠️ Noto'g'ri format. <b>KK.OO.YYYY</b> ko'rinishida kiriting:",
                             parse_mode="HTML")


# ─── Reminder Scheduler (background thread) ──────────────────────────────────

def reminder_loop():
    while True:
        now = datetime.now()
        for s in all_settings():
            chat_id, hour, minute, on = s[0], s[1], s[2], s[3]
            if on and now.hour == hour and now.minute == minute:
                items = get_tomorrow_hw(chat_id)
                if items:
                    lines = [f"📌 <b>{hw[3]}</b>: {hw[4]}" for hw in items]
                    text = "🌙 <b>Kechki eslatma</b> — ertangi darslar:\n\n" + "\n".join(lines) + "\n\n💪 Omad!"
                else:
                    text = "🌙 <b>Kechki eslatma</b>\n\n✅ Ertaga uchun dars yo'q! Yaxshi dam oling 🎉"
                try:
                    bot.send_message(chat_id, text, parse_mode="HTML")
                except:
                    pass
        time.sleep(60)


# ─── Main ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    init_db()
    print("✅ Database tayyor")

    # Start reminder thread
    t = threading.Thread(target=reminder_loop, daemon=True)
    t.start()
    print("✅ Eslatma tizimi ishga tushdi")

    print("🚀 SchoolBot ishlamoqda...")
    bot.infinity_polling()
