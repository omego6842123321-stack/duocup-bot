import os
import json
import time
import sqlite3
import csv
import io
import html
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 6655762147
DB_FILE = "duocup.db"

if not TOKEN:
    raise RuntimeError("Не задана переменная BOT_TOKEN")

API = f"https://api.telegram.org/bot{TOKEN}/"

db = sqlite3.connect(DB_FILE, check_same_thread=False)
db.row_factory = sqlite3.Row
db.execute("""
CREATE TABLE IF NOT EXISTS teams (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    team_name TEXT NOT NULL,
    player1_telegram TEXT NOT NULL,
    player1_discord TEXT NOT NULL,
    player1_steam TEXT NOT NULL,
    player2_telegram TEXT NOT NULL,
    player2_discord TEXT NOT NULL,
    player2_steam TEXT NOT NULL,
    captain_id INTEGER NOT NULL,
    created_at TEXT NOT NULL
)
""")
db.commit()

# Заблокированные участники/капитаны
db.execute("""
CREATE TABLE IF NOT EXISTS bans (
    user_id INTEGER PRIMARY KEY,
    reason TEXT NOT NULL DEFAULT '',
    banned_at TEXT NOT NULL
)
""")
db.commit()

states = {}

def api(method, data=None, timeout=40):
    body = None
    headers = {}
    if data is not None:
        body = urllib.parse.urlencode(data).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    req = urllib.request.Request(API + method, data=body, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        result = json.loads(r.read().decode())
    if not result.get("ok"):
        raise RuntimeError(result.get("description", "Telegram API error"))
    return result["result"]

def send(chat_id, text, keyboard=None):
    data = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if keyboard:
        data["reply_markup"] = json.dumps(keyboard, ensure_ascii=False)
    return api("sendMessage", data)

def edit(chat_id, message_id, text, keyboard=None):
    data = {"chat_id": chat_id, "message_id": message_id, "text": text, "parse_mode": "HTML"}
    if keyboard:
        data["reply_markup"] = json.dumps(keyboard, ensure_ascii=False)
    return api("editMessageText", data)

def answer_callback(callback_id, text=None, alert=False):
    data = {"callback_query_id": callback_id}
    if text:
        data["text"] = text
        data["show_alert"] = str(alert).lower()
    return api("answerCallbackQuery", data)

def main_menu():
    return {"inline_keyboard": [
        [{"text": "🏆 Зарегистрировать команду", "callback_data": "register"}],
        [{"text": "📋 Моя регистрация", "callback_data": "my_registration"}],
        [{"text": "📜 Правила турнира", "callback_data": "rules"}],
        [{"text": "📞 Связь с организатором", "callback_data": "contact"}],
    ]}

def admin_menu():
    return {"inline_keyboard": [
        [{"text": "📊 Статистика", "callback_data": "admin_stats"}],
        [{"text": "📋 Все команды", "callback_data": "admin_teams"}],
        [{"text": "🚫 Заблокированные", "callback_data": "admin_bans"}],
        [{"text": "📥 Экспорт CSV", "callback_data": "admin_export"}],
    ]}

def is_banned(user_id):
    return db.execute("SELECT 1 FROM bans WHERE user_id=?", (user_id,)).fetchone() is not None

def team_admin_keyboard(team):
    banned = is_banned(team["captain_id"])
    action = "unban_team" if banned else "ban_team"
    label = "✅ Разбанить команду" if banned else "🚫 Забанить команду"
    return {"inline_keyboard": [
        [{"text": label, "callback_data": f"{action}:{team['id']}"}],
        [{"text": "⬅️ К списку команд", "callback_data": "admin_teams"}],
        [{"text": "🏠 Админ-панель", "callback_data": "admin_home"}],
    ]}

def format_admin_team(team):
    def tg_link(value):
        v = value.strip()
        if v.startswith("@"):
            return f'<a href="https://t.me/{html.escape(v[1:])}">{html.escape(v)}</a>'
        return html.escape(v)
    def safe(value):
        return html.escape(str(value))
    banned = is_banned(team["captain_id"])
    return (
        f"🔢 <b>Команда #{team['id']:03d}</b>\n"
        f"🏷 <b>{safe(team['team_name'])}</b>\n"
        f"🕒 {safe(team['created_at'])}\n"
        f"👑 Telegram ID капитана: <code>{team['captain_id']}</code>\n"
        f"🚦 Статус: <b>{'🚫 ЗАБАНЕНА' if banned else '✅ Активна'}</b>\n\n"
        "👤 <b>Игрок 1</b>\n"
        f"Telegram: {tg_link(team['player1_telegram'])}\n"
        f"Discord: <code>{safe(team['player1_discord'])}</code>\n"
        f"Steam: <a href=\"{safe(team['player1_steam'])}\">открыть Steam</a>\n\n"
        "👤 <b>Игрок 2</b>\n"
        f"Telegram: {tg_link(team['player2_telegram'])}\n"
        f"Discord: <code>{safe(team['player2_discord'])}</code>\n"
        f"Steam: <a href=\"{safe(team['player2_steam'])}\">открыть Steam</a>"
    )

def confirmation_keyboard():
    return {"inline_keyboard": [
        [{"text": "✅ Подтвердить", "callback_data": "confirm_registration"}],
        [{"text": "❌ Отменить", "callback_data": "cancel_registration"}],
    ]}

def back_keyboard():
    return {"inline_keyboard": [[{"text": "⬅️ Назад", "callback_data": "back_main"}]]}

def format_team(team):
    return (
        "🏆 <b>DuoCup</b>\n\n"
        f"🔢 Команда: <b>#{team['id']:03d}</b>\n"
        f"🏷 Название: <b>{team['team_name']}</b>\n\n"
        "👤 <b>Игрок 1</b>\n"
        f"Telegram: {team['player1_telegram']}\n"
        f"Discord: {team['player1_discord']}\n"
        f"Steam: {team['player1_steam']}\n\n"
        "👤 <b>Игрок 2</b>\n"
        f"Telegram: {team['player2_telegram']}\n"
        f"Discord: {team['player2_discord']}\n"
        f"Steam: {team['player2_steam']}"
    )

def start(chat_id):
    states.pop(chat_id, None)
    send(chat_id,
         "🏆 <b>DuoCup</b>\n\n"
         "Турнир по <b>PUBG: BATTLEGROUNDS на PC</b>\n"
         "Формат: <b>Duo</b>\n\n"
         "Выберите действие:",
         main_menu())

def handle_message(message):
    chat_id = message["chat"]["id"]
    text = message.get("text", "")
    if text == "/start":
        start(chat_id)
        return
    if text == "/admin":
        if chat_id == ADMIN_ID:
            send(chat_id, "🔐 <b>Админ-панель DuoCup</b>", admin_menu())
        else:
            send(chat_id, "⛔ Доступ запрещён.")
        return

    state = states.get(chat_id)
    if not state:
        return

    value = text.strip()
    if not value:
        send(chat_id, "❌ Отправьте текст.")
        return

    step = state["step"]
    if step == "team_name":
        if len(value) < 2:
            send(chat_id, "❌ Название слишком короткое. Введите ещё раз.")
            return
        if len(value) > 50:
            send(chat_id, "❌ Максимум 50 символов.")
            return
        state["team_name"] = value
        state["step"] = "player1_telegram"
        send(chat_id, "👤 <b>Игрок 1</b>\n\nВведите Telegram игрока.\nНапример: <code>@username</code>")
    elif step == "player1_telegram":
        state["player1_telegram"] = value
        state["step"] = "player1_discord"
        send(chat_id, "💬 Введите Discord игрока 1:")
    elif step == "player1_discord":
        state["player1_discord"] = value
        state["step"] = "player1_steam"
        send(chat_id, "🔗 Отправьте Steam-ссылку игрока 1:")
    elif step == "player1_steam":
        if "steamcommunity.com" not in value.lower():
            send(chat_id, "❌ Похоже, это не Steam-ссылка.\nОтправьте ссылку вида:\nhttps://steamcommunity.com/...")
            return
        state["player1_steam"] = value
        state["step"] = "player2_telegram"
        send(chat_id, "👤 <b>Игрок 2</b>\n\nВведите Telegram игрока 2:")
    elif step == "player2_telegram":
        state["player2_telegram"] = value
        state["step"] = "player2_discord"
        send(chat_id, "💬 Введите Discord игрока 2:")
    elif step == "player2_discord":
        state["player2_discord"] = value
        state["step"] = "player2_steam"
        send(chat_id, "🔗 Отправьте Steam-ссылку игрока 2:")
    elif step == "player2_steam":
        if "steamcommunity.com" not in value.lower():
            send(chat_id, "❌ Похоже, это не Steam-ссылка.\nОтправьте корректную Steam-ссылку.")
            return
        state["player2_steam"] = value
        text = (
            "🏆 <b>Проверьте регистрацию</b>\n\n"
            f"🏷 <b>Команда:</b> {state['team_name']}\n\n"
            "👤 <b>Игрок 1</b>\n"
            f"Telegram: {state['player1_telegram']}\n"
            f"Discord: {state['player1_discord']}\n"
            f"Steam: {state['player1_steam']}\n\n"
            "👤 <b>Игрок 2</b>\n"
            f"Telegram: {state['player2_telegram']}\n"
            f"Discord: {state['player2_discord']}\n"
            f"Steam: {state['player2_steam']}\n\n"
            "Всё верно?"
        )
        send(chat_id, text, confirmation_keyboard())

def handle_callback(cq):
    chat_id = cq["message"]["chat"]["id"]
    msg_id = cq["message"]["message_id"]
    data = cq.get("data", "")
    user_id = cq["from"]["id"]

    try:
        if data == "register":
            if is_banned(user_id):
                answer_callback(cq["id"], "🚫 Вы заблокированы и не можете зарегистрировать команду.", True)
                return
            existing = db.execute("SELECT 1 FROM teams WHERE captain_id=?", (user_id,)).fetchone()
            if existing:
                answer_callback(cq["id"], "У вас уже есть зарегистрированная команда.", True)
                return
            states[chat_id] = {"step": "team_name"}
            edit(chat_id, msg_id, "🏆 <b>Регистрация DuoCup</b>\n\nВведите <b>название команды</b>:")
            answer_callback(cq["id"])
        elif data == "confirm_registration":
            if is_banned(user_id):
                states.pop(chat_id, None)
                answer_callback(cq["id"], "🚫 Вы заблокированы.", True)
                return
            state = states.get(chat_id)
            if not state:
                answer_callback(cq["id"], "Регистрация устарела.", True)
                return
            existing = db.execute("SELECT 1 FROM teams WHERE captain_id=?", (user_id,)).fetchone()
            if existing:
                states.pop(chat_id, None)
                edit(chat_id, msg_id, "❌ У вас уже есть зарегистрированная команда.")
                answer_callback(cq["id"])
                return
            created = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cur = db.execute("""
                INSERT INTO teams (
                    team_name, player1_telegram, player1_discord, player1_steam,
                    player2_telegram, player2_discord, player2_steam,
                    captain_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                state["team_name"], state["player1_telegram"], state["player1_discord"],
                state["player1_steam"], state["player2_telegram"], state["player2_discord"],
                state["player2_steam"], user_id, created
            ))
            db.commit()
            team_id = cur.lastrowid
            states.pop(chat_id, None)
            edit(chat_id, msg_id,
                 "✅ <b>Регистрация успешно завершена!</b>\n\n"
                 f"🏆 Турнир: <b>DuoCup</b>\n🎮 Формат: <b>Duo</b>\n"
                 f"🔢 Номер команды: <b>#{team_id:03d}</b>\n"
                 f"🏷 Команда: <b>{state['team_name']}</b>\n\n"
                 "Сохраните номер команды.\nОрганизатор свяжется с вами при необходимости.")
            admin_text = (
                "🚨 <b>Новая регистрация DuoCup!</b>\n\n"
                f"🔢 Команда: <b>#{team_id:03d}</b>\n"
                f"🏷 Название: <b>{state['team_name']}</b>\n\n"
                f"👤 <b>Игрок 1</b>\nTelegram: {state['player1_telegram']}\n"
                f"Discord: {state['player1_discord']}\nSteam: {state['player1_steam']}\n\n"
                f"👤 <b>Игрок 2</b>\nTelegram: {state['player2_telegram']}\n"
                f"Discord: {state['player2_discord']}\nSteam: {state['player2_steam']}"
            )
            try:
                send(ADMIN_ID, admin_text)
            except Exception:
                pass
            answer_callback(cq["id"], "Команда зарегистрирована!")
        elif data == "cancel_registration":
            states.pop(chat_id, None)
            edit(chat_id, msg_id, "❌ Регистрация отменена.\n\nЧтобы начать заново, нажмите /start")
            answer_callback(cq["id"])
        elif data == "my_registration":
            team = db.execute("SELECT * FROM teams WHERE captain_id=?", (user_id,)).fetchone()
            if not team:
                answer_callback(cq["id"], "У вас пока нет регистрации.", True)
                return
            keyboard = {"inline_keyboard": [
                [{"text": "❌ Отменить регистрацию", "callback_data": "delete_my_registration"}],
                [{"text": "⬅️ Назад", "callback_data": "back_main"}],
            ]}
            edit(chat_id, msg_id, format_team(team), keyboard)
            answer_callback(cq["id"])
        elif data == "delete_my_registration":
            db.execute("DELETE FROM teams WHERE captain_id=?", (user_id,))
            db.commit()
            edit(chat_id, msg_id, "❌ Ваша регистрация удалена.\n\nЧтобы зарегистрироваться снова, нажмите /start")
            answer_callback(cq["id"], "Регистрация удалена.")
        elif data == "rules":
            edit(chat_id, msg_id,
                 "📜 <b>Правила DuoCup</b>\n\n"
                 "🎮 Игра: PUBG: BATTLEGROUNDS PC\n👥 Формат: Duo\n\n"
                 "Для регистрации необходимо указать:\n"
                 "• название команды\n• Telegram двух игроков\n"
                 "• Discord двух игроков\n• Steam-ссылку двух игроков\n\n"
                 "⚠️ Финальные правила турнира организатор может дополнить перед началом соревнования.",
                 back_keyboard())
            answer_callback(cq["id"])
        elif data == "contact":
            edit(chat_id, msg_id,
                 "📞 <b>Связь с организатором</b>\n\n"
                 "По всем вопросам турнира обращайтесь к администратору.",
                 {"inline_keyboard": [
                     [{"text": "👤 Написать администратору",
                       "url": "https://t.me/renako_812"}],
                     [{"text": "⬅️ Назад", "callback_data": "back_main"}]
                 ]})
            answer_callback(cq["id"])
        elif data == "back_main":
            edit(chat_id, msg_id,
                 "🏆 <b>DuoCup</b>\n\nТурнир по PUBG: BATTLEGROUNDS PC\n"
                 "Формат: <b>Duo</b>\n\nВыберите действие:", main_menu())
            answer_callback(cq["id"])
        elif data == "admin_stats":
            if user_id != ADMIN_ID:
                answer_callback(cq["id"], "⛔ Доступ запрещён.", True)
                return
            total = db.execute("SELECT COUNT(*) AS c FROM teams").fetchone()["c"]
            edit(chat_id, msg_id, f"📊 <b>Статистика DuoCup</b>\n\n🏆 Зарегистрировано команд: <b>{total}</b>\n👥 Участников: <b>{total*2}</b>", admin_menu())
            answer_callback(cq["id"])
        elif data == "admin_home":
            if user_id != ADMIN_ID:
                answer_callback(cq["id"], "⛔ Доступ запрещён.", True)
                return
            edit(chat_id, msg_id, "🔐 <b>Админ-панель DuoCup</b>", admin_menu())
            answer_callback(cq["id"])
        elif data == "admin_teams":
            if user_id != ADMIN_ID:
                answer_callback(cq["id"], "⛔ Доступ запрещён.", True)
                return
            teams = db.execute("SELECT * FROM teams ORDER BY id ASC").fetchall()
            if not teams:
                edit(chat_id, msg_id, "📋 <b>Команды</b>\n\nПока нет зарегистрированных команд.", admin_menu())
            else:
                rows = []
                for t in teams:
                    status = "🚫" if is_banned(t["captain_id"]) else "✅"
                    rows.append([{"text": f"{status} #{t['id']:03d} — {t['team_name']}", "callback_data": f"admin_team:{t['id']}"}])
                rows.append([{"text": "🏠 Админ-панель", "callback_data": "admin_home"}])
                edit(chat_id, msg_id, "📋 <b>Команды</b>\n\nНажми на команду, чтобы увидеть Telegram, Discord, Steam и управление баном.", {"inline_keyboard": rows})
            answer_callback(cq["id"])
        elif data.startswith("admin_team:"):
            if user_id != ADMIN_ID:
                answer_callback(cq["id"], "⛔ Доступ запрещён.", True)
                return
            team_id = int(data.split(":", 1)[1])
            team = db.execute("SELECT * FROM teams WHERE id=?", (team_id,)).fetchone()
            if not team:
                answer_callback(cq["id"], "Команда не найдена.", True)
                return
            edit(chat_id, msg_id, format_admin_team(team), team_admin_keyboard(team))
            answer_callback(cq["id"])
        elif data in ("ban_team", "unban_team") or data.startswith("ban_team:") or data.startswith("unban_team:"):
            if user_id != ADMIN_ID:
                answer_callback(cq["id"], "⛔ Доступ запрещён.", True)
                return
            action, team_id_text = data.split(":", 1)
            team = db.execute("SELECT * FROM teams WHERE id=?", (int(team_id_text),)).fetchone()
            if not team:
                answer_callback(cq["id"], "Команда не найдена.", True)
                return
            if action == "ban_team":
                db.execute("INSERT OR REPLACE INTO bans (user_id, reason, banned_at) VALUES (?, ?, ?)", (team["captain_id"], "Заблокирован администратором", datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                db.commit()
                try:
                    send(team["captain_id"], "🚫 <b>Ваша команда заблокирована организатором DuoCup.</b>")
                except Exception:
                    pass
                answer_callback(cq["id"], "Команда заблокирована.")
            else:
                db.execute("DELETE FROM bans WHERE user_id=?", (team["captain_id"],))
                db.commit()
                try:
                    send(team["captain_id"], "✅ <b>Блокировка вашей команды снята.</b>")
                except Exception:
                    pass
                answer_callback(cq["id"], "Блокировка снята.")
            team = db.execute("SELECT * FROM teams WHERE id=?", (team["id"],)).fetchone()
            edit(chat_id, msg_id, format_admin_team(team), team_admin_keyboard(team))
        elif data == "admin_bans":
            if user_id != ADMIN_ID:
                answer_callback(cq["id"], "⛔ Доступ запрещён.", True)
                return
            bans = db.execute("SELECT * FROM bans ORDER BY banned_at DESC").fetchall()
            rows = []
            text = "🚫 <b>Заблокированные</b>\n\n"
            if not bans:
                text += "Список пуст."
            else:
                for b in bans:
                    team = db.execute("SELECT id, team_name FROM teams WHERE captain_id=?", (b["user_id"],)).fetchone()
                    name = f"#{team['id']:03d} — {team['team_name']}" if team else "команда удалена"
                    text += f"👤 <code>{b['user_id']}</code> — {html.escape(name)}\n🕒 {html.escape(b['banned_at'])}\n\n"
            rows.append([{"text": "⬅️ Админ-панель", "callback_data": "admin_home"}])
            edit(chat_id, msg_id, text, {"inline_keyboard": rows})
            answer_callback(cq["id"])
        elif data == "admin_export":
            if user_id != ADMIN_ID:
                answer_callback(cq["id"], "⛔ Доступ запрещён.", True)
                return
            teams = db.execute("SELECT * FROM teams ORDER BY id ASC").fetchall()
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(["ID","Team","Player 1 Telegram","Player 1 Discord","Player 1 Steam",
                             "Player 2 Telegram","Player 2 Discord","Player 2 Steam","Created"])
            for t in teams:
                writer.writerow([t["id"],t["team_name"],t["player1_telegram"],t["player1_discord"],
                                 t["player1_steam"],t["player2_telegram"],t["player2_discord"],
                                 t["player2_steam"],t["created_at"]])
            send_document(chat_id, "duocup_registrations.csv", output.getvalue().encode("utf-8-sig"))
            answer_callback(cq["id"], "Файл подготовлен.")
    except Exception as e:
        print("Callback error:", e)
        try:
            answer_callback(cq["id"], "Произошла ошибка.", True)
        except Exception:
            pass

def send_document(chat_id, filename, content):
    boundary = "----DuoCupBoundary"
    parts = []
    parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"chat_id\"\r\n\r\n{chat_id}\r\n".encode())
    parts.append(
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"document\"; filename=\"{filename}\"\r\n"
        "Content-Type: text/csv\r\n\r\n".encode() + content + b"\r\n"
    )
    body = b"".join(parts) + f"--{boundary}--\r\n".encode()
    req = urllib.request.Request(
        API + "sendDocument",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}
    )
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.loads(r.read().decode())

def poll():
    offset = None
    print("DuoCup Bot запущен (минимальная версия, без сторонних Python-библиотек).")
    while True:
        try:
            params = {"timeout": 25}
            if offset is not None:
                params["offset"] = offset
            updates = api("getUpdates", params, timeout=35)
            for u in updates:
                offset = u["update_id"] + 1
                if "message" in u:
                    handle_message(u["message"])
                elif "callback_query" in u:
                    handle_callback(u["callback_query"])
        except Exception as e:
            print("Polling error:", e)
            time.sleep(3)

if __name__ == "__main__":
    poll()
