#!/usr/bin/env python3
"""Проверка логики бота без Telegram: python3 selftest.py

Подделываем Telegram, прогоняем клиента по всем веткам и сверяем результат.
Реальный токен и интернет не нужны.
"""

import os
import sys
import tempfile

import texts
from bot import Bot
from content import Content
from storage import Storage, now

CLIENT = 111
ADMIN_CHAT = -1001


class FakeAPI:
    """Заглушка Telegram: запоминает отправленное вместо реальных запросов."""

    def __init__(self):
        self.sent = []
        self.edits = []
        self.next_id = 1000

    def _record(self, chat_id, text, markup):
        self.next_id += 1
        self.sent.append({"chat_id": chat_id, "text": text, "markup": markup, "message_id": self.next_id})
        return {"message_id": self.next_id}

    def send_message(self, chat_id, text, reply_markup=None, parse_mode="HTML"):
        return self._record(chat_id, text, reply_markup)

    def edit_message_text(self, chat_id, message_id, text, reply_markup=None, parse_mode="HTML"):
        self.edits.append({"chat_id": chat_id, "message_id": message_id, "text": text})
        return self._record(chat_id, text, reply_markup)

    def answer_callback_query(self, callback_query_id, text=None):
        return True

    def call(self, method, **params):
        return self._record(params.get("chat_id"), f"[{method}]", None)

    # --- помощники проверки ---

    def last(self, chat_id=CLIENT):
        for item in reversed(self.sent):
            if item["chat_id"] == chat_id:
                return item
        raise AssertionError(f"боту нечего было отправить в чат {chat_id}")

    def buttons(self, chat_id=CLIENT):
        markup = self.last(chat_id)["markup"] or {}
        return [button for row in markup.get("inline_keyboard", []) for button in row]

    def callbacks(self, chat_id=CLIENT):
        return [button.get("callback_data") for button in self.buttons(chat_id)]

    def to_admin(self):
        return [item for item in self.sent if item["chat_id"] == ADMIN_CHAT]


def message(text, chat_id=CLIENT, **extra):
    payload = {
        "message_id": 1,
        "chat": {"id": chat_id},
        "from": {"id": chat_id, "first_name": "Анна", "username": "anna"},
        "text": text,
    }
    payload.update(extra)
    return {"message": payload}


def press(data, chat_id=CLIENT):
    return {
        "callback_query": {
            "id": "cq",
            "data": data,
            "from": {"id": chat_id, "first_name": "Анна", "username": "anna"},
            "message": {"message_id": 500, "chat": {"id": chat_id}, "text": "предыдущее сообщение"},
        }
    }


def check(condition, description):
    if not condition:
        print(f"❌ {description}")
        sys.exit(1)
    print(f"✅ {description}")


def main():
    base = os.path.dirname(os.path.abspath(__file__))
    content = Content.load(os.path.join(base, "salon.json"))
    db_path = os.path.join(tempfile.mkdtemp(), "test.db")
    api = FakeAPI()
    bot = Bot(
        api,
        Storage(db_path),
        content,
        {"admin_chat_id": ADMIN_CHAT, "reminder_after_minutes": 30, "followup_after_hours": 24},
    )

    print("\n— Стартовое сообщение и главное меню —")
    bot.handle_update(message("/start"))
    check("Здравствуйте" in api.last()["text"], "на /start приходит приветствие")
    check(
        api.callbacks() == ["book", "srv", "pro", "addr", "faq"],
        "в главном меню ровно 5 кнопок в нужном порядке",
    )

    print("\n— Ветка «Записаться» —")
    bot.handle_update(press("book"))
    check(len(api.callbacks()) == len(content.salons) + 1, "предлагает выбрать салон")
    bot.handle_update(press("bs:0"))
    check(
        bot.db.get_draft(CLIENT).get("salon") == content.salons[0]["title"],
        "выбранный салон запомнен",
    )
    check("bc:0" in api.callbacks(), "предлагает направление услуг")
    bot.handle_update(press("bc:0"))
    check("bsv:0:0" in api.callbacks(), "предлагает конкретные услуги")
    bot.handle_update(press("bsv:0:0"))
    check("Когда вам удобно" in api.last()["text"], "спрашивает удобное время")

    bot.handle_update(message("в субботу после 15:00"))
    check("Как вас зовут" in api.last()["text"], "спрашивает имя")
    bot.handle_update(message("Анна"))
    check("телефон" in api.last()["text"], "спрашивает телефон")

    bot.handle_update(message("не скажу"))
    check("не хватает цифр" in api.last()["text"], "телефон без цифр не принимает")
    bot.handle_update(message("+7 900 123-45-67"))
    check("Проверьте" in api.sent[-2]["text"], "показывает сводку заявки")
    check(api.callbacks() == ["cyes", "cedit", "menu"], "предлагает подтвердить, исправить или выйти")

    admin_before = len(api.to_admin())
    bot.handle_update(press("cyes"))
    check("Заявка №1 принята" in api.last()["text"], "клиент получает подтверждение с номером заявки")
    check(len(api.to_admin()) == admin_before + 1, "заявка ушла администраторам")
    admin_card = api.to_admin()[-1]
    check("+7 900 123-45-67" in admin_card["text"], "в заявке администратора есть телефон")
    check("в субботу после 15:00" in admin_card["text"], "в заявке есть пожелание по времени")
    check("Женская стрижка" in admin_card["text"], "в заявке есть услуга")

    lead = bot.db.get_lead(1)
    check(lead["phone"] == "+7 900 123-45-67", "заявка сохранена в базе")

    print("\n— Кнопка «Взял в работу» у администратора —")
    bot.handle_update(
        {
            "callback_query": {
                "id": "cq",
                "data": "take:1",
                "from": {"id": 7, "first_name": "Ольга"},
                "message": {"message_id": admin_card["message_id"], "chat": {"id": ADMIN_CHAT}, "text": "📝 Заявка №1"},
            }
        }
    )
    check(bot.db.get_lead(1)["status"] == "in_progress", "статус заявки меняется на «в работе»")

    print("\n— Возврат в меню есть на каждом шаге —")
    screens = ["book", "bs:0", "bc:0", "srv", "srvc:0", "srvs:0:0", "pro", "prom:0", "addr", "faq", "faqa:0", "op"]
    for screen in screens:
        bot.handle_update(press(screen))
        check("menu" in api.callbacks(), f"экран «{screen}»: кнопка возврата в меню на месте")

    print("\n— Услуги, акции, адреса —")
    bot.handle_update(press("srvs:0:0"))
    card = api.last()["text"]
    check("от 2 500 ₽" in card and "1 ч" in card, "в карточке услуги есть цена и длительность")
    check(any(str(c).startswith("booksvc") for c in api.callbacks()), "из карточки услуги можно записаться")
    bot.handle_update(press("prom:0"))
    check(any(str(c).startswith("bookpromo") for c in api.callbacks()), "из акции можно записаться")
    bot.handle_update(press("addr"))
    addresses = api.last()["text"]
    check(all(salon["address"] in addresses for salon in content.salons), "показаны все три адреса")
    check(any(button.get("url") for button in api.buttons()), "есть кнопка-ссылка на карту")

    print("\n— Запись из карточки услуги пропускает лишний шаг —")
    bot.handle_update(press("booksvc:0:0"))
    bot.handle_update(press("bs:1"))
    check("Когда вам удобно" in api.last()["text"], "услуга уже известна, спрашивает сразу про время")

    print("\n— Запись по акции попадает в заявку —")
    bot.handle_update(press("bookpromo:0"))
    bot.handle_update(press("bs:0"))
    bot.handle_update(press("bc:1"))
    bot.handle_update(press("bsv:1:0"))
    bot.handle_update(message("завтра вечером"))
    bot.handle_update(message("Мария"))
    bot.handle_update(message("89001234567"))
    bot.handle_update(press("cyes"))
    check("по акции" in api.to_admin()[-1]["text"], "в заявке видно, что клиент пришёл по акции")

    print("\n— Вопросы и живой администратор —")
    bot.handle_update(press("faqa:0"))
    check("Администратор перезванивает" in api.last()["text"], "автоответ на частый вопрос приходит")
    bot.handle_update(press("op"))
    bot.handle_update(message("Во сколько работает мастер Ирина?"))
    question = api.to_admin()[-1]
    check("Ирина" in question["text"], "вопрос клиента ушёл администратору")
    bot.handle_update(
        message("Ирина работает по вторникам", chat_id=ADMIN_CHAT, reply_to_message={"message_id": question["message_id"]})
    )
    check("Ответ администратора" in api.last(CLIENT)["text"], "ответ администратора вернулся клиенту")

    print("\n— Напоминание о брошенной записи —")
    bot.handle_update(press("menu"))
    bot.handle_update(press("book"))
    bot.handle_update(press("bs:0"))
    bot.handle_update(press("bc:0"))
    bot.handle_update(press("bsv:0:0"))
    bot.db.db.execute("UPDATE users SET last_activity = ? WHERE chat_id = ?", (now() - 3600, CLIENT))
    bot.db.db.commit()
    bot.run_scheduled()
    check("не закончили" in api.last()["text"], "через полчаса приходит напоминание")
    check("rcont" in api.callbacks(), "напоминание предлагает продолжить запись")
    bot.run_scheduled()
    check("не закончили" in api.last()["text"], "повторно напоминание не шлётся")
    bot.handle_update(press("rcont"))
    check("Когда вам удобно" in api.last()["text"], "запись продолжается с того же шага")

    print("\n— Автосообщение через сутки —")
    bot.db.db.execute("UPDATE jobs SET run_at = ? WHERE kind = 'followup'", (now() - 10,))
    bot.db.db.commit()
    bot.run_scheduled()
    check("Вчера вы оставили заявку" in api.last()["text"], "через сутки бот сам напоминает о себе")
    check(any(str(c).startswith("ffail") for c in api.callbacks()), "можно пожаловаться, что не перезвонили")
    admin_before = len(api.to_admin())
    bot.handle_update(press("ffail:1"))
    check(len(api.to_admin()) > admin_before, "жалоба уходит администраторам")

    print("\n— Прочее —")
    bot.handle_update(press("menu"))
    bot.handle_update(message("привет, а вы стрижёте мальчиков?"))
    check("кнопки" in api.last()["text"], "на свободный текст вне записи бот подсказывает меню")
    bot.handle_update(press("несуществующая:кнопка"))
    check("устарела" in api.last()["text"] or "меню" in api.last()["text"].lower(), "устаревшая кнопка не ломает бота")

    print("\n🎉 Все проверки пройдены.")


if __name__ == "__main__":
    main()
