#!/usr/bin/env python3
"""Показывает ID чатов, где бот получал сообщения: python3 get_chat_id.py

Нужно, чтобы вписать admin_chat_id в config.json.
"""

import json
import os
import sys

from telegram_api import TelegramAPI, TelegramError

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
config_path = os.path.join(BASE_DIR, "config.json")

if not os.path.exists(config_path):
    sys.exit("❌ Сначала создайте config.json (скопируйте config.example.json) и впишите токен.")

with open(config_path, encoding="utf-8") as handle:
    config = json.load(handle)

try:
    updates = TelegramAPI(config["token"]).get_updates(offset=None, timeout=5)
except TelegramError as error:
    sys.exit(f"❌ Telegram не принял запрос: {error}")

chats = {}
for update in updates:
    message = update.get("message") or (update.get("callback_query") or {}).get("message") or {}
    chat = message.get("chat")
    if chat:
        chats[chat["id"]] = chat

if not chats:
    print("Пока ничего не нашёл.")
    print("Сделайте так: добавьте бота в рабочую группу, напишите там /start@имя_вашего_бота,")
    print("подождите пару секунд и запустите этот файл снова.")
    sys.exit(0)

print("Найденные чаты:\n")
for chat_id, chat in chats.items():
    title = chat.get("title") or chat.get("first_name") or "—"
    kind = {"private": "личная переписка", "group": "группа", "supergroup": "группа", "channel": "канал"}
    print(f"  ID: {chat_id}   {kind.get(chat['type'], chat['type'])}: {title}")
print("\nID группы администраторов (начинается с минуса) впишите в config.json → admin_chat_id")
