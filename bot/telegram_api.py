"""Минимальный клиент Telegram Bot API. Только стандартная библиотека Python."""

import json
import logging
import socket
import time
import urllib.error
import urllib.parse
import urllib.request

log = logging.getLogger("telegram")

API_URL = "https://api.telegram.org/bot{token}/{method}"


class TelegramError(Exception):
    """Telegram ответил ошибкой."""

    def __init__(self, method, code, description):
        super().__init__(f"{method}: {code} {description}")
        self.method = method
        self.code = code
        self.description = description


class BotBlocked(TelegramError):
    """Пользователь заблокировал бота или удалил чат — писать ему больше нельзя."""


class TelegramAPI:
    """Обёртка над HTTP-методами Telegram с повторами при сетевых сбоях."""

    def __init__(self, token, network_retries=4):
        self.token = token
        self.network_retries = network_retries

    def call(self, method, **params):
        payload = {k: v for k, v in params.items() if v is not None}
        for key, value in list(payload.items()):
            if isinstance(value, (dict, list)):
                payload[key] = json.dumps(value, ensure_ascii=False)
        data = urllib.parse.urlencode(payload).encode("utf-8")
        url = API_URL.format(token=self.token, method=method)
        # Свой таймаут: long polling ждёт дольше обычных запросов.
        timeout = int(params.get("timeout", 0)) + 20

        delay = 2
        for attempt in range(self.network_retries + 1):
            try:
                request = urllib.request.Request(url, data=data)
                with urllib.request.urlopen(request, timeout=timeout) as response:
                    body = json.loads(response.read().decode("utf-8"))
                return body["result"]
            except urllib.error.HTTPError as error:
                body = self._parse_error_body(error)
                code = body.get("error_code", error.code)
                description = body.get("description", str(error))
                retry_after = body.get("parameters", {}).get("retry_after")
                if retry_after:
                    log.warning("Лимит частоты, ждём %s с", retry_after)
                    time.sleep(retry_after + 1)
                    continue
                if code == 403 or "bot was blocked" in description or "chat not found" in description:
                    raise BotBlocked(method, code, description) from None
                if code >= 500 and attempt < self.network_retries:
                    time.sleep(delay)
                    delay *= 2
                    continue
                raise TelegramError(method, code, description) from None
            except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError) as error:
                if attempt >= self.network_retries:
                    raise
                log.warning("Сеть недоступна (%s), повтор через %s с", error, delay)
                time.sleep(delay)
                delay *= 2
        raise RuntimeError("недостижимо")

    @staticmethod
    def _parse_error_body(error):
        try:
            return json.loads(error.read().decode("utf-8"))
        except Exception:
            return {}

    # --- методы, которые использует бот ---

    def get_updates(self, offset, timeout=50):
        return self.call(
            "getUpdates",
            offset=offset,
            timeout=timeout,
            allowed_updates=["message", "callback_query"],
        )

    def send_message(self, chat_id, text, reply_markup=None, parse_mode="HTML"):
        return self.call(
            "sendMessage",
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
            link_preview_options={"is_disabled": True},
        )

    def edit_message_text(self, chat_id, message_id, text, reply_markup=None, parse_mode="HTML"):
        return self.call(
            "editMessageText",
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
            link_preview_options={"is_disabled": True},
        )

    def answer_callback_query(self, callback_query_id, text=None):
        return self.call("answerCallbackQuery", callback_query_id=callback_query_id, text=text)

    def set_my_commands(self, commands):
        return self.call("setMyCommands", commands=commands)

    def set_my_description(self, description):
        return self.call("setMyDescription", description=description)

    def set_my_short_description(self, short_description):
        return self.call("setMyShortDescription", short_description=short_description)

    def get_me(self):
        return self.call("getMe")
