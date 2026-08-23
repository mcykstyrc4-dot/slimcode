"""Загрузка и проверка salon.json — содержимого бота."""

import json
import os


class ContentError(Exception):
    """Ошибка в salon.json, понятная человеку без опыта в программировании."""


class Content:
    def __init__(self, data):
        self.data = data
        self.salon_name = data["salon_name"]
        self.contact_phone = data.get("contact_phone", "")
        self.salons = data["salons"]
        self.categories = data["service_categories"]
        self.promos = data.get("promos", [])
        self.faq = data.get("faq", [])

    @classmethod
    def load(cls, path):
        if not os.path.exists(path):
            raise ContentError(f"Файл {path} не найден.")
        try:
            with open(path, encoding="utf-8") as handle:
                data = json.load(handle)
        except json.JSONDecodeError as error:
            raise ContentError(
                f"В файле {path} ошибка формата на строке {error.lineno}: {error.msg}. "
                "Чаще всего это лишняя или пропущенная запятая либо кавычка."
            ) from None
        cls._validate(data, path)
        return cls(data)

    @staticmethod
    def _validate(data, path):
        def fail(message):
            raise ContentError(f"{path}: {message}")

        for key in ("salon_name", "salons", "service_categories"):
            if key not in data:
                fail(f"не хватает обязательного раздела «{key}».")

        if not isinstance(data["salons"], list) or not data["salons"]:
            fail("раздел «salons» должен содержать хотя бы один салон.")
        for index, salon in enumerate(data["salons"], 1):
            for key in ("title", "address", "hours"):
                if not salon.get(key):
                    fail(f"у салона №{index} не заполнено поле «{key}».")

        if not isinstance(data["service_categories"], list) or not data["service_categories"]:
            fail("раздел «service_categories» должен содержать хотя бы одну категорию услуг.")
        for index, category in enumerate(data["service_categories"], 1):
            if not category.get("title"):
                fail(f"у категории услуг №{index} не заполнено поле «title».")
            services = category.get("services")
            if not isinstance(services, list) or not services:
                fail(f"в категории «{category.get('title')}» нет ни одной услуги.")
            for service in services:
                if not service.get("title"):
                    fail(f"в категории «{category['title']}» у услуги не заполнено поле «title».")
                for key in ("price", "duration"):
                    if not service.get(key):
                        fail(f"у услуги «{service['title']}» не заполнено поле «{key}».")

        for index, promo in enumerate(data.get("promos", []), 1):
            if not promo.get("title") or not promo.get("text"):
                fail(f"у акции №{index} должны быть заполнены «title» и «text».")

        for index, item in enumerate(data.get("faq", []), 1):
            if not item.get("question") or not item.get("answer"):
                fail(f"у вопроса №{index} должны быть заполнены «question» и «answer».")

    # --- доступ по индексам (индексы попадают в данные кнопок) ---

    @property
    def multi_salon(self):
        return len(self.salons) > 1

    @property
    def multi_category(self):
        return len(self.categories) > 1

    def salon(self, index):
        return self.salons[index] if 0 <= index < len(self.salons) else None

    def category(self, index):
        return self.categories[index] if 0 <= index < len(self.categories) else None

    def service(self, category_index, service_index):
        category = self.category(category_index)
        if not category:
            return None
        services = category["services"]
        return services[service_index] if 0 <= service_index < len(services) else None

    def promo(self, index):
        return self.promos[index] if 0 <= index < len(self.promos) else None

    def faq_item(self, index):
        return self.faq[index] if 0 <= index < len(self.faq) else None
