#!/usr/bin/env python3
"""Бот салона красоты для Telegram. Запуск: python3 bot.py"""

import json
import logging
import os
import re
import sys
import time

import texts
from content import Content, ContentError
from storage import Storage, now
from telegram_api import BotBlocked, TelegramAPI, TelegramError

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

log = logging.getLogger("bot")

# Состояния, в которых клиент не дошёл до конца записи — им шлём напоминание.
BOOKING_STATES = (
    "book_salon",
    "book_category",
    "book_service",
    "book_when",
    "book_name",
    "book_phone",
    "book_confirm",
)

DIGITS = re.compile(r"\d")


def load_config():
    path = os.path.join(BASE_DIR, "config.json")
    if not os.path.exists(path):
        sys.exit(
            "❌ Не найден файл config.json.\n"
            "   Скопируйте config.example.json в config.json и впишите туда токен бота "
            "и ID чата администраторов."
        )
    with open(path, encoding="utf-8") as handle:
        config = json.load(handle)
    if not config.get("token") or "ВСТАВЬТЕ" in str(config.get("token")):
        sys.exit("❌ В config.json не вписан токен бота (поле \"token\"). Токен выдаёт @BotFather.")
    if not config.get("admin_chat_id"):
        sys.exit(
            "❌ В config.json не указан admin_chat_id — чат, куда падают заявки.\n"
            "   Как его узнать, написано в README.md."
        )
    config.setdefault("reminder_after_minutes", 30)
    config.setdefault("followup_after_hours", 24)
    config.setdefault("db_path", os.path.join(BASE_DIR, "bot.db"))
    return config


def button_label(text, limit=48):
    """Подпись кнопки: длинные названия обрезаем, иначе кнопка занимает пол-экрана."""
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 1].rstrip(" ,.;:") + "…"


def keyboard(*rows):
    """Инлайн-клавиатура: keyboard([("Текст", "данные")], [("Ещё", "данные2")])"""
    return {
        "inline_keyboard": [
            [
                {"text": button_label(text), "url": data[4:]} if str(data).startswith("url:") else
                {"text": button_label(text), "callback_data": data}
                for text, data in row
            ]
            for row in rows
            if row
        ]
    }


class Bot:
    def __init__(self, api, storage, content, config):
        self.api = api
        self.db = storage
        self.content = content
        self.config = config
        self.admin_chat_id = int(config["admin_chat_id"])

    # ------------------------------------------------------------------ запуск

    def run(self):
        offset = None
        log.info("Бот запущен, жду сообщений")
        while True:
            try:
                updates = self.api.get_updates(offset, timeout=30)
            except TelegramError as error:
                log.error("Telegram вернул ошибку при получении обновлений: %s", error)
                time.sleep(5)
                continue
            except Exception as error:  # сеть моргнула — не роняем бота
                log.error("Сбой при получении обновлений: %s", error)
                time.sleep(5)
                continue

            for update in updates:
                offset = update["update_id"] + 1
                try:
                    self.handle_update(update)
                except BotBlocked:
                    pass
                except Exception:
                    log.exception("Ошибка при обработке обновления %s", update.get("update_id"))

            try:
                self.run_scheduled()
            except Exception:
                log.exception("Ошибка планировщика")

    def setup_profile(self):
        """Название команд и описание бота в Telegram."""
        try:
            self.api.set_my_commands(
                [
                    {"command": "start", "description": "Начать сначала"},
                    {"command": "menu", "description": "Главное меню"},
                ]
            )
            self.api.set_my_short_description(
                f"Запись и цены салона красоты «{self.content.salon_name}»"
            )
            self.api.set_my_description(
                f"Салон красоты «{self.content.salon_name}». "
                "Запись к мастеру, услуги и цены, акции, адреса. "
                "Нажмите «Старт», чтобы открыть меню."
            )
        except TelegramError as error:
            log.warning("Не удалось обновить профиль бота: %s", error)

    # ------------------------------------------------- отправка и клавиатуры

    def send(self, chat_id, text, markup=None, message_id=None):
        """Если пришли из кнопки — правим сообщение, иначе шлём новое."""
        try:
            if message_id:
                return self.api.edit_message_text(chat_id, message_id, text, markup)
            return self.api.send_message(chat_id, text, markup)
        except BotBlocked:
            self.db.mark_blocked(chat_id)
            raise
        except TelegramError as error:
            if message_id and "not modified" in error.description:
                return None
            if message_id:
                return self.api.send_message(chat_id, text, markup)
            raise

    def menu_row(self, back=None):
        row = []
        if back:
            row.append((texts.BTN_BACK, back))
        row.append((texts.BTN_MENU, "menu"))
        return row

    def main_menu_markup(self):
        return keyboard(
            [(texts.BTN_BOOK, "book")],
            [(texts.BTN_SERVICES, "srv")],
            [(texts.BTN_PROMOS, "pro")],
            [(texts.BTN_ADDRESSES, "addr")],
            [(texts.BTN_QUESTION, "faq")],
        )

    def show_menu(self, chat_id, message_id=None, greeting=False):
        self.db.set_state(chat_id, "idle")
        self.db.clear_draft(chat_id)
        text = texts.START.format(salon=self.content.salon_name) if greeting else texts.MENU
        self.send(chat_id, text, self.main_menu_markup(), message_id)

    # ------------------------------------------------------------ обновления

    def handle_update(self, update):
        if "callback_query" in update:
            self.on_callback(update["callback_query"])
        elif "message" in update:
            self.on_message(update["message"])

    def on_message(self, message):
        chat_id = message["chat"]["id"]

        if chat_id == self.admin_chat_id:
            self.on_admin_message(message)
            return

        user = message.get("from", {})
        self.db.touch_user(chat_id, user.get("first_name"), user.get("username"))

        text = (message.get("text") or "").strip()
        if text in ("/start", "/menu", texts.BTN_MENU) or text.startswith("/start"):
            self.show_menu(chat_id, greeting=text.startswith("/start"))
            return

        state = (self.db.get_user(chat_id) or {}).get("state", "idle")

        if state == "book_when":
            self.step_when(chat_id, text)
        elif state == "book_name":
            self.step_name(chat_id, text)
        elif state == "book_phone":
            self.step_phone(chat_id, message, text)
        elif state == "operator":
            self.forward_to_admin(chat_id, message, text)
        else:
            self.send(chat_id, texts.UNKNOWN_TEXT, self.main_menu_markup())

    def on_callback(self, query):
        data = query.get("data") or ""
        message = query.get("message") or {}
        chat_id = message.get("chat", {}).get("id")
        message_id = message.get("message_id")
        user = query.get("from", {})

        if chat_id == self.admin_chat_id:
            self.on_admin_callback(query, data, message_id, user)
            return

        self.db.touch_user(chat_id, user.get("first_name"), user.get("username"))
        try:
            self.api.answer_callback_query(query["id"])
        except TelegramError:
            pass

        parts = data.split(":")
        action = parts[0]
        try:
            self.route(action, parts, chat_id, message_id)
        except IndexError:
            self.show_menu(chat_id, message_id)

    def route(self, action, parts, chat_id, message_id):
        if action == "menu":
            self.show_menu(chat_id, message_id)
        elif action == "book":
            self.start_booking(chat_id, message_id)
        elif action == "booksvc":
            self.start_booking(chat_id, message_id, service=self.service_title(parts[1], parts[2]))
        elif action == "bookpromo":
            promo = self.content.promo(int(parts[1]))
            self.start_booking(chat_id, message_id, promo=promo["title"] if promo else None)
        elif action == "bs":
            self.pick_salon(chat_id, message_id, int(parts[1]))
        elif action == "bc":
            self.show_booking_services(chat_id, message_id, int(parts[1]))
        elif action == "bsv":
            self.pick_service(chat_id, message_id, self.service_title(parts[1], parts[2]))
        elif action == "bskip":
            self.pick_service(chat_id, message_id, texts.SERVICE_UNSURE_TITLE)
        elif action == "cyes":
            self.submit_lead(chat_id, message_id)
        elif action == "cedit":
            self.start_booking(chat_id, message_id)
        elif action == "srv":
            self.show_service_categories(chat_id, message_id)
        elif action == "srvc":
            self.show_services(chat_id, message_id, int(parts[1]))
        elif action == "srvs":
            self.show_service_card(chat_id, message_id, int(parts[1]), int(parts[2]))
        elif action == "pro":
            self.show_promos(chat_id, message_id)
        elif action == "prom":
            self.show_promo(chat_id, message_id, int(parts[1]))
        elif action == "addr":
            self.show_addresses(chat_id, message_id)
        elif action == "faq":
            self.show_faq(chat_id, message_id)
        elif action == "faqa":
            self.show_faq_answer(chat_id, message_id, int(parts[1]))
        elif action == "op":
            self.start_operator(chat_id, message_id)
        elif action == "opstop":
            self.db.set_state(chat_id, "idle")
            self.send(chat_id, texts.OPERATOR_LEFT, self.main_menu_markup(), message_id)
        elif action == "rcont":
            self.resume_booking(chat_id, message_id)
        elif action == "rrestart":
            self.start_booking(chat_id, message_id)
        elif action == "fok":
            self.send(chat_id, texts.FOLLOWUP_OK_REPLY, self.main_menu_markup(), message_id)
        elif action == "ffail":
            self.followup_complaint(chat_id, message_id, int(parts[1]) if len(parts) > 1 else 0)
        else:
            self.send(chat_id, texts.STALE_BUTTON, self.main_menu_markup(), message_id)

    def service_title(self, category_index, service_index):
        service = self.content.service(int(category_index), int(service_index))
        return service["title"] if service else None

    # ------------------------------------------------------------ ветка «Записаться»

    def start_booking(self, chat_id, message_id=None, service=None, promo=None):
        draft = {}
        if service:
            draft["service"] = service
        if promo:
            draft["promo"] = promo
        self.db.save_draft(chat_id, draft)

        if not self.content.multi_salon:
            self.apply_salon(chat_id, message_id, 0)
            return

        self.db.set_state(chat_id, "book_salon")
        rows = [
            [(salon["title"], f"bs:{index}")] for index, salon in enumerate(self.content.salons)
        ]
        self.send(chat_id, texts.BOOK_SALON, keyboard(*rows, self.menu_row()), message_id)

    def pick_salon(self, chat_id, message_id, index):
        self.apply_salon(chat_id, message_id, index)

    def apply_salon(self, chat_id, message_id, index):
        salon = self.content.salon(index)
        if not salon:
            self.show_menu(chat_id, message_id)
            return
        draft = self.db.get_draft(chat_id)
        draft["salon"] = salon["title"]
        self.db.save_draft(chat_id, draft)

        if draft.get("service"):
            self.ask_when(chat_id, message_id)
        elif self.content.multi_category:
            self.show_booking_categories(chat_id, message_id)
        else:
            self.show_booking_services(chat_id, message_id, 0)

    def show_booking_categories(self, chat_id, message_id):
        self.db.set_state(chat_id, "book_category")
        draft = self.db.get_draft(chat_id)
        rows = [
            [(category["title"], f"bc:{index}")]
            for index, category in enumerate(self.content.categories)
        ]
        rows.append([(texts.BOOK_SERVICE_UNSURE, "bskip")])
        self.send(
            chat_id,
            texts.BOOK_CATEGORY.format(salon=draft.get("salon", "")),
            keyboard(*rows, self.menu_row(back="book")),
            message_id,
        )

    def show_booking_services(self, chat_id, message_id, category_index):
        category = self.content.category(category_index)
        if not category:
            self.show_menu(chat_id, message_id)
            return
        self.db.set_state(chat_id, "book_service")
        rows = [
            [(service["title"], f"bsv:{category_index}:{index}")]
            for index, service in enumerate(category["services"])
        ]
        rows.append([(texts.BOOK_SERVICE_UNSURE, "bskip")])
        back = "book" if self.content.multi_category else "menu"
        self.send(chat_id, texts.BOOK_SERVICE, keyboard(*rows, self.menu_row(back=back)), message_id)

    def pick_service(self, chat_id, message_id, title):
        if not title:
            self.show_menu(chat_id, message_id)
            return
        draft = self.db.get_draft(chat_id)
        draft["service"] = title
        self.db.save_draft(chat_id, draft)
        self.ask_when(chat_id, message_id)

    def ask_when(self, chat_id, message_id=None):
        self.db.set_state(chat_id, "book_when")
        draft = self.db.get_draft(chat_id)
        self.send(
            chat_id,
            texts.BOOK_WHEN.format(service=draft.get("service", ""), salon=draft.get("salon", "")),
            keyboard(self.menu_row()),
            message_id,
        )

    def step_when(self, chat_id, text):
        if not text:
            self.ask_when(chat_id)
            return
        draft = self.db.get_draft(chat_id)
        draft["when"] = text[:300]
        self.db.save_draft(chat_id, draft)
        self.ask_name(chat_id)

    def ask_name(self, chat_id):
        self.db.set_state(chat_id, "book_name")
        self.send(chat_id, texts.BOOK_NAME, keyboard(self.menu_row()))

    def step_name(self, chat_id, text):
        if not text or len(text) > 60:
            self.send(chat_id, texts.BOOK_NAME_INVALID, keyboard(self.menu_row()))
            return
        draft = self.db.get_draft(chat_id)
        draft["name"] = text
        self.db.save_draft(chat_id, draft)
        self.ask_phone(chat_id)

    def ask_phone(self, chat_id):
        self.db.set_state(chat_id, "book_phone")
        draft = self.db.get_draft(chat_id)
        share_keyboard = {
            "keyboard": [
                [{"text": texts.BTN_SHARE_PHONE, "request_contact": True}],
                [{"text": texts.BTN_MENU}],
            ],
            "resize_keyboard": True,
            "one_time_keyboard": True,
        }
        self.api.send_message(
            chat_id, texts.BOOK_PHONE.format(name=draft.get("name", "")), share_keyboard
        )

    def step_phone(self, chat_id, message, text):
        contact = message.get("contact") or {}
        phone = contact.get("phone_number") or text
        if len(DIGITS.findall(phone or "")) < 10:
            self.send(chat_id, texts.BOOK_PHONE_INVALID)
            return
        draft = self.db.get_draft(chat_id)
        draft["phone"] = phone.strip()
        self.db.save_draft(chat_id, draft)
        self.ask_confirm(chat_id)

    def ask_confirm(self, chat_id):
        self.db.set_state(chat_id, "book_confirm")
        draft = self.db.get_draft(chat_id)
        summary = texts.BOOK_CONFIRM.format(
            salon=draft.get("salon", "—"),
            service=self.service_line(draft),
            when=draft.get("when", "—"),
            name=draft.get("name", "—"),
            phone=draft.get("phone", "—"),
        )
        # Первым сообщением убираем клавиатуру с кнопкой «отправить номер».
        self.api.send_message(chat_id, summary, {"remove_keyboard": True})
        self.api.send_message(
            chat_id,
            texts.BOOK_CONFIRM_QUESTION,
            keyboard(
                [(texts.BTN_CONFIRM_SEND, "cyes")],
                [(texts.BTN_CONFIRM_RESTART, "cedit")],
                self.menu_row(),
            ),
        )

    @staticmethod
    def service_line(draft):
        service = draft.get("service", "—")
        if draft.get("promo"):
            return f"{service} (по акции «{draft['promo']}»)"
        return service

    def submit_lead(self, chat_id, message_id):
        draft = self.db.get_draft(chat_id)
        if not draft.get("phone"):
            self.start_booking(chat_id, message_id)
            return

        user = self.db.get_user(chat_id) or {}
        lead_draft = dict(draft, service=self.service_line(draft))
        lead_id = self.db.create_lead(chat_id, lead_draft, user.get("username"))

        self.notify_admin_lead(lead_id, lead_draft, user)
        self.db.schedule(
            "followup",
            chat_id,
            now() + int(self.config["followup_after_hours"]) * 3600,
            {"lead_id": lead_id},
        )

        self.db.set_state(chat_id, "idle")
        self.db.clear_draft(chat_id)
        self.send(
            chat_id,
            texts.BOOK_DONE.format(
                lead_id=lead_id,
                salon=draft.get("salon", ""),
                service=lead_draft["service"],
                when=draft.get("when", ""),
            ),
            self.main_menu_markup(),
            message_id,
        )

    def notify_admin_lead(self, lead_id, draft, user):
        card = texts.ADMIN_LEAD.format(
            lead_id=lead_id,
            salon=draft.get("salon", "—"),
            service=draft.get("service", "—"),
            when=draft.get("when", "—"),
            name=draft.get("name", "—"),
            phone=draft.get("phone", "—"),
            client=self.client_label(user),
        )
        try:
            sent = self.api.send_message(
                self.admin_chat_id, card, keyboard([(texts.BTN_ADMIN_TAKE, f"take:{lead_id}")])
            )
            self.db.link_operator_message(sent["message_id"], user.get("chat_id"))
        except TelegramError as error:
            log.error(
                "Заявка №%s сохранена, но не ушла в чат администраторов: %s. "
                "Проверьте admin_chat_id в config.json и что бот добавлен в этот чат.",
                lead_id,
                error,
            )

    @staticmethod
    def client_label(user):
        name = user.get("first_name") or "клиент"
        username = user.get("username")
        return f"{name} (@{username})" if username else name

    def resume_booking(self, chat_id, message_id):
        """Продолжить брошенную запись с того шага, где человек остановился."""
        state = (self.db.get_user(chat_id) or {}).get("state", "idle")
        if state == "book_when":
            self.ask_when(chat_id, message_id)
        elif state == "book_name":
            self.ask_name(chat_id)
        elif state == "book_phone":
            self.ask_phone(chat_id)
        elif state == "book_confirm":
            self.ask_confirm(chat_id)
        elif state == "book_category":
            self.show_booking_categories(chat_id, message_id)
        elif state == "book_service":
            self.show_booking_services(chat_id, message_id, 0)
        else:
            self.start_booking(chat_id, message_id)

    # ------------------------------------------------------- ветка «Услуги и цены»

    def show_service_categories(self, chat_id, message_id):
        self.db.set_state(chat_id, "idle")
        if not self.content.multi_category:
            self.show_services(chat_id, message_id, 0)
            return
        rows = [
            [(category["title"], f"srvc:{index}")]
            for index, category in enumerate(self.content.categories)
        ]
        self.send(chat_id, texts.SERVICES_CATEGORIES, keyboard(*rows, self.menu_row()), message_id)

    def show_services(self, chat_id, message_id, category_index):
        category = self.content.category(category_index)
        if not category:
            self.show_menu(chat_id, message_id)
            return
        rows = [
            [(service["title"], f"srvs:{category_index}:{index}")]
            for index, service in enumerate(category["services"])
        ]
        back = "srv" if self.content.multi_category else None
        self.send(
            chat_id,
            texts.SERVICES_LIST.format(category=category["title"]),
            keyboard(*rows, self.menu_row(back=back)),
            message_id,
        )

    def show_service_card(self, chat_id, message_id, category_index, service_index):
        service = self.content.service(category_index, service_index)
        if not service:
            self.show_menu(chat_id, message_id)
            return
        text = texts.SERVICE_CARD.format(
            title=service["title"],
            description=service.get("description", ""),
            price=service["price"],
            duration=service["duration"],
        )
        self.send(
            chat_id,
            text,
            keyboard(
                [(texts.BTN_BOOK_THIS, f"booksvc:{category_index}:{service_index}")],
                self.menu_row(back=f"srvc:{category_index}"),
            ),
            message_id,
        )

    # ------------------------------------------------------------- ветка «Акции»

    def show_promos(self, chat_id, message_id):
        self.db.set_state(chat_id, "idle")
        if not self.content.promos:
            self.send(chat_id, texts.PROMOS_EMPTY, keyboard(self.menu_row()), message_id)
            return
        rows = [
            [(promo["title"], f"prom:{index}")] for index, promo in enumerate(self.content.promos)
        ]
        self.send(chat_id, texts.PROMOS_LIST, keyboard(*rows, self.menu_row()), message_id)

    def show_promo(self, chat_id, message_id, index):
        promo = self.content.promo(index)
        if not promo:
            self.show_menu(chat_id, message_id)
            return
        self.send(
            chat_id,
            texts.PROMO_CARD.format(title=promo["title"], text=promo["text"]),
            keyboard(
                [(texts.BTN_BOOK_PROMO, f"bookpromo:{index}")],
                self.menu_row(back="pro"),
            ),
            message_id,
        )

    # ------------------------------------------------------------ ветка «Адреса»

    def show_addresses(self, chat_id, message_id):
        self.db.set_state(chat_id, "idle")
        blocks = [texts.ADDRESSES_HEADER]
        map_rows = []
        for salon in self.content.salons:
            landmark = salon.get("landmark")
            blocks.append(
                texts.ADDRESS_CARD.format(
                    title=salon["title"],
                    address=salon["address"],
                    landmark=f"{landmark}\n" if landmark else "",
                    hours=salon["hours"],
                    phone=salon.get("phone") or self.content.contact_phone,
                )
            )
            if salon.get("map_url"):
                map_rows.append([(texts.BTN_MAP.format(title=salon["title"]), f"url:{salon['map_url']}")])
        rows = map_rows + [[(texts.BTN_BOOK, "book")], self.menu_row()]
        self.send(chat_id, "\n\n".join(blocks), keyboard(*rows), message_id)

    # ------------------------------------------------------ ветка «Задать вопрос»

    def show_faq(self, chat_id, message_id):
        self.db.set_state(chat_id, "idle")
        rows = [
            [(item["question"], f"faqa:{index}")] for index, item in enumerate(self.content.faq)
        ]
        rows.append([(texts.BTN_OPERATOR, "op")])
        self.send(chat_id, texts.FAQ_HEADER, keyboard(*rows, self.menu_row()), message_id)

    def show_faq_answer(self, chat_id, message_id, index):
        item = self.content.faq_item(index)
        if not item:
            self.show_menu(chat_id, message_id)
            return
        self.send(
            chat_id,
            texts.FAQ_ANSWER.format(question=item["question"], answer=item["answer"]),
            keyboard(
                [(texts.BTN_OPERATOR, "op")],
                [(texts.BTN_BOOK, "book")],
                self.menu_row(back="faq"),
            ),
            message_id,
        )

    def start_operator(self, chat_id, message_id):
        self.db.set_state(chat_id, "operator")
        self.send(
            chat_id,
            texts.OPERATOR_START,
            keyboard([(texts.BTN_OPERATOR_STOP, "opstop")], self.menu_row()),
            message_id,
        )

    def forward_to_admin(self, chat_id, message, text):
        user = self.db.get_user(chat_id) or {}
        body = text or "(вложение ниже)"
        try:
            sent = self.api.send_message(
                self.admin_chat_id,
                texts.ADMIN_QUESTION.format(client=self.client_label(user), text=body),
            )
            self.db.link_operator_message(sent["message_id"], chat_id)
            if not text:
                copied = self.api.call(
                    "copyMessage",
                    chat_id=self.admin_chat_id,
                    from_chat_id=chat_id,
                    message_id=message["message_id"],
                )
                self.db.link_operator_message(copied["message_id"], chat_id)
        except TelegramError as error:
            log.error("Вопрос клиента не ушёл администраторам: %s", error)
        self.send(
            chat_id,
            texts.OPERATOR_SENT,
            keyboard([(texts.BTN_OPERATOR_STOP, "opstop")], self.menu_row()),
        )

    # ------------------------------------------------ сообщения из чата администраторов

    def on_admin_message(self, message):
        """Ответ администратора на пересланное сообщение уходит клиенту."""
        reply_to = message.get("reply_to_message")
        text = (message.get("text") or "").strip()
        if not reply_to or not text:
            return
        client_chat_id = self.db.operator_chat_for(reply_to["message_id"])
        if not client_chat_id:
            return
        try:
            self.api.send_message(client_chat_id, texts.OPERATOR_REPLY.format(text=text))
            self.api.send_message(self.admin_chat_id, texts.ADMIN_REPLY_SENT)
        except BotBlocked:
            self.db.mark_blocked(client_chat_id)
            self.api.send_message(self.admin_chat_id, texts.ADMIN_REPLY_FAILED)

    def on_admin_callback(self, query, data, message_id, user):
        if not data.startswith("take:"):
            return
        lead_id = int(data.split(":")[1])
        self.db.set_lead_status(lead_id, "in_progress")
        admin_name = user.get("first_name") or "администратор"
        original = (query.get("message") or {}).get("text", "")
        try:
            self.api.edit_message_text(
                self.admin_chat_id,
                message_id,
                original + texts.ADMIN_LEAD_TAKEN.format(admin=admin_name),
            )
        except TelegramError:
            pass
        try:
            self.api.answer_callback_query(query["id"], "Заявка отмечена как взятая в работу")
        except TelegramError:
            pass

    # ---------------------------------------------- напоминания и автосообщения

    def run_scheduled(self):
        self.send_abandoned_reminders()
        self.run_due_jobs()

    def send_abandoned_reminders(self):
        idle_seconds = int(self.config["reminder_after_minutes"]) * 60
        for user in self.db.abandoned_users(BOOKING_STATES, idle_seconds):
            chat_id = user["chat_id"]
            self.db.mark_reminded(chat_id)
            try:
                self.api.send_message(
                    chat_id,
                    texts.REMINDER_ABANDONED,
                    keyboard(
                        [(texts.BTN_REMINDER_CONTINUE, "rcont")],
                        [(texts.BTN_REMINDER_RESTART, "rrestart")],
                        self.menu_row(),
                    ),
                )
                log.info("Напоминание о брошенной записи отправлено %s", chat_id)
            except BotBlocked:
                self.db.mark_blocked(chat_id)
            except TelegramError as error:
                log.warning("Не удалось отправить напоминание %s: %s", chat_id, error)

    def run_due_jobs(self):
        for job in self.db.due_jobs():
            self.db.finish_job(job["id"])
            if job["kind"] != "followup":
                continue
            payload = json.loads(job["payload"])
            lead_id = payload.get("lead_id")
            lead = self.db.get_lead(lead_id)
            if not lead:
                continue
            try:
                self.api.send_message(
                    job["chat_id"],
                    texts.FOLLOWUP_NEXT_DAY.format(salon=lead["salon"] or self.content.salon_name),
                    keyboard(
                        [(texts.BTN_FOLLOWUP_OK, "fok")],
                        [(texts.BTN_FOLLOWUP_FAIL, f"ffail:{lead_id}")],
                        self.menu_row(),
                    ),
                )
                log.info("Автосообщение через сутки отправлено по заявке №%s", lead_id)
            except BotBlocked:
                self.db.mark_blocked(job["chat_id"])
            except TelegramError as error:
                log.warning("Автосообщение по заявке №%s не ушло: %s", lead_id, error)

    def followup_complaint(self, chat_id, message_id, lead_id):
        lead = self.db.get_lead(lead_id) or {}
        user = self.db.get_user(chat_id) or {}
        self.db.set_lead_status(lead_id, "no_contact")
        try:
            self.api.send_message(
                self.admin_chat_id,
                texts.ADMIN_FOLLOWUP_FAIL.format(
                    lead_id=lead_id,
                    name=lead.get("name", "—"),
                    phone=lead.get("phone", "—"),
                    client=self.client_label(user),
                ),
            )
        except TelegramError as error:
            log.error("Жалоба клиента не ушла администраторам: %s", error)
        self.send(chat_id, texts.FOLLOWUP_FAIL_REPLY, self.main_menu_markup(), message_id)


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%d.%m %H:%M:%S",
    )
    config = load_config()
    try:
        content = Content.load(os.path.join(BASE_DIR, "salon.json"))
    except ContentError as error:
        sys.exit(f"❌ {error}")

    api = TelegramAPI(config["token"])
    try:
        me = api.get_me()
        log.info("Подключился к боту @%s", me.get("username"))
    except TelegramError as error:
        sys.exit(f"❌ Telegram не принял токен: {error}")

    bot = Bot(api, Storage(config["db_path"]), content, config)
    bot.setup_profile()
    bot.run()


if __name__ == "__main__":
    main()
