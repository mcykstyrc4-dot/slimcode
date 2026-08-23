#!/usr/bin/env python3
"""Выгрузка заявок в таблицу: python3 export_leads.py

Создаёт файл leads.csv — открывается в Excel и Google Таблицах.
"""

import csv
import datetime
import os
import sqlite3

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
db_path = os.path.join(BASE_DIR, "bot.db")
out_path = os.path.join(BASE_DIR, "leads.csv")

STATUS = {"new": "новая", "in_progress": "в работе", "no_contact": "клиент жалуется, что не перезвонили"}

db = sqlite3.connect(db_path)
db.row_factory = sqlite3.Row
rows = db.execute("SELECT * FROM leads ORDER BY id").fetchall()

with open(out_path, "w", newline="", encoding="utf-8-sig") as handle:
    writer = csv.writer(handle, delimiter=";")
    writer.writerow(["№", "Дата", "Салон", "Услуга", "Когда удобно", "Имя", "Телефон", "Telegram", "Статус"])
    for row in rows:
        created = datetime.datetime.fromtimestamp(row["created_at"]).strftime("%d.%m.%Y %H:%M")
        writer.writerow([
            row["id"], created, row["salon"], row["service"], row["when_text"],
            row["name"], row["phone"],
            f"@{row['username']}" if row["username"] else "",
            STATUS.get(row["status"], row["status"]),
        ])

print(f"✅ Готово: {out_path} — заявок в файле: {len(rows)}")
