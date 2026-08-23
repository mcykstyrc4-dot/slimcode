#!/usr/bin/env python3
"""Проверка salon.json перед запуском бота: python3 check_content.py"""

import os
import sys

from content import Content, ContentError

path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "salon.json")

try:
    content = Content.load(path)
except ContentError as error:
    print(f"❌ {error}")
    sys.exit(1)

services = sum(len(category["services"]) for category in content.categories)
print("✅ Файл salon.json заполнен правильно.")
print(f"   Салон: {content.salon_name}")
print(f"   Адресов: {len(content.salons)}")
print(f"   Категорий услуг: {len(content.categories)}, услуг всего: {services}")
print(f"   Акций: {len(content.promos)}, вопросов в разделе «Задать вопрос»: {len(content.faq)}")
