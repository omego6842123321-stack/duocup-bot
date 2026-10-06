import os
from flask import Flask, request, jsonify
import bot

app = Flask(__name__)

WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")

@app.get("/")
def home():
    return "DuoCup bot is running."

@app.post("/telegram/<secret>")
def telegram_webhook(secret):
    if not WEBHOOK_SECRET or secret != WEBHOOK_SECRET:
        return jsonify({"ok": False}), 403

    update = request.get_json(silent=True)
    if not update:
        return jsonify({"ok": False, "error": "empty update"}), 400

    try:
        if "message" in update:
            bot.handle_message(update["message"])
        elif "callback_query" in update:
            bot.handle_callback(update["callback_query"])
        return jsonify({"ok": True})
    except Exception as e:
        print("Webhook error:", repr(e))
        return jsonify({"ok": False}), 500
