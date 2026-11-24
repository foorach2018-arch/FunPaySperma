from __future__ import annotations
from typing import TYPE_CHECKING

import bcrypt
import requests

from locales.localizer import Localizer

if TYPE_CHECKING:
    from badtrip import BadTrip

import FunPayAPI.types

from datetime import datetime
import Utils.exceptions
import itertools
import threading
import psutil
import json
import sys
import os
import re
import time
import random
import shutil
import math
import logging

PHOTO_RE = re.compile(r'\$photo=[\d]+')
ENTITY_RE = re.compile(r"\$photo=\d+|\$new|(\$sleep=(\d+\.\d+|\d+))")
logger = logging.getLogger("BadTrip.badtrip_tools")
localizer = Localizer()
_ = localizer.translate

_products_file_locks: dict[str, threading.Lock] = {}
_products_file_locks_guard = threading.Lock()


def get_products_file_lock(path: str) -> threading.Lock:
    """
    Возвращает Lock, общий для всех обращений к указанному товарному файлу (создаёт при первом
    обращении). Используется всеми функциями, читающими/пишущими storage/products/*, чтобы
    синхронизировать доступ из разных потоков.

    :param path: путь до товарного файла.

    :return: Lock, специфичный для данного файла.
    """
    normalized = os.path.normcase(os.path.abspath(path))
    with _products_file_locks_guard:
        if normalized not in _products_file_locks:
            _products_file_locks[normalized] = threading.Lock()
        return _products_file_locks[normalized]


def count_products(path: str) -> int:
    """
    Считает кол-во товара в указанном файле.

    :param path: путь до файла с товарами.

    :return: кол-во товара в указанном файле.
    """
    with get_products_file_lock(path):
        if not os.path.exists(path):
            return 0
        with open(path, "r", encoding="utf-8") as f:
            products = f.read()
    products = products.split("\n")
    products = list(itertools.filterfalse(lambda el: not el, products))
    return len(products)


def cache_blacklist(blacklist: list[str]) -> None:
    """
    Кэширует черный список.

    :param blacklist: черный список.
    """
    if not os.path.exists("storage/cache"):
        os.makedirs("storage/cache")

    with open("storage/cache/blacklist.json", "w", encoding="utf-8") as f:
        f.write(json.dumps(blacklist, indent=4))


def load_blacklist() -> list[str]:
    """
    Загружает черный список.

    :return: черный список.
    """
    if not os.path.exists("storage/cache/blacklist.json"):
        return []

    with open("storage/cache/blacklist.json", "r", encoding="utf-8") as f:
        blacklist = f.read()

        try:
            blacklist = json.loads(blacklist)
        except json.decoder.JSONDecodeError:
            return []
        return blacklist


def check_proxy(proxy: dict) -> bool:
    """
    Проверяет работоспособность прокси.

    :param proxy: словарь с данными прокси.

    :return: True, если прокси работает, иначе - False.
    """
    logger.info(_("crd_checking_proxy"))
    try:
        response = requests.get("https://api.ipify.org/", proxies=proxy, timeout=10)
    except:
        logger.error(_("crd_proxy_err"))
        logger.debug("TRACEBACK", exc_info=True)
        return False
    logger.info(_("crd_proxy_success", response.content.decode()))
    return True


def validate_proxy(proxy: str):
    """
    Проверяет прокси на соответствие формату IPv4 и выбрасывает исключение или возвращает логин, пароль, IP и порт.

    :param proxy: прокси
    :return: логин, пароль, IP и порт
    """
    if "://" in proxy:
        scheme, rest = proxy.split("://", 1)
    else:
        scheme = "http"
        rest = proxy

    if "@" in rest:
        login_password, ip_port = rest.split("@")
        login, password = login_password.split(":")
    else:
        login, password = "", ""
        ip_port = rest

    ip, port = ip_port.split(":")

    if scheme == "socks5":
        scheme = "socks5h"

    ip_parts = ip.split(".")
    if len(ip_parts) != 4 or not all(part.isdigit() and 0 <= int(part) < 256 for part in ip_parts):
        raise ValueError("Неправильный IP")

    if not port.isdigit() or not 0 < int(port) <= 65535:
        raise ValueError("Неправильный порт")

    if scheme not in ("http", "https", "socks5", "socks5h"):
        raise ValueError("Схема прокси должна быть http, https, socks5 или socks5h")

    return scheme, login, password, ip, port

def build_proxy(scheme: str | None, login: str, password: str, ip: str, port: str) -> str:
    if not scheme:
        scheme = "http"
    if login and password:
        return f"{scheme}://{login}:{password}@{ip}:{port}"
    else:
        return f"{scheme}://{ip}:{port}"


def cache_proxy_dict(proxy_dict: dict[int, str]) -> None:
    """
    Кэширует список прокси.

    :param proxy_dict: список прокси.
    """
    if not os.path.exists("storage/cache"):
        os.makedirs("storage/cache")

    with open("storage/cache/proxy_dict.json", "w", encoding="utf-8") as f:
        f.write(json.dumps(proxy_dict, indent=4))


def load_proxy_dict() -> dict[int, str]:
    """
    Загружает список прокси.

    :return: список прокси.
    """
    if not os.path.exists("storage/cache/proxy_dict.json"):
        return {}

    with open("storage/cache/proxy_dict.json", "r", encoding="utf-8") as f:
        proxy = f.read()

        try:
            proxy = json.loads(proxy)
            proxy_dict = {}
            for id_, proxy_str in proxy.items():
                try:
                    proxy_dict[int(id_)] = build_proxy(*validate_proxy(proxy_str))
                except:
                    logger.debug(f"Не удалось добавить {proxy_str}")
                    logger.debug("TRACEBACK", exc_info=True)
        except json.decoder.JSONDecodeError:
            return {}
        return proxy_dict


def cache_disabled_plugins(disabled_plugins: list[str]) -> None:
    """
    Кэширует UUID отключенных плагинов.

    :param disabled_plugins: список UUID отключенных плагинов.
    """
    if not os.path.exists("storage/cache"):
        os.makedirs("storage/cache")

    with open("storage/cache/disabled_plugins.json", "w", encoding="utf-8") as f:
        f.write(json.dumps(disabled_plugins))


def load_disabled_plugins() -> list[str]:
    """
    Загружает список UUID отключенных плагинов из кэша.

    :return: список UUID отключенных плагинов.
    """
    if not os.path.exists("storage/cache/disabled_plugins.json"):
        return []

    with open("storage/cache/disabled_plugins.json", "r", encoding="utf-8") as f:
        try:
            return json.loads(f.read())
        except json.decoder.JSONDecodeError:
            return []

def cache_pinned_plugins(pinned_plugins: list[str]) -> None:
    """
    Кэширует UUID закрепленных плагинов.

    :param pinned_plugins: список UUID закрепленных плагинов.
    """
    if not os.path.exists("storage/cache"):
        os.makedirs("storage/cache")

    with open("storage/cache/pinned_plugins.json", "w", encoding="utf-8") as f:
        f.write(json.dumps(pinned_plugins))

def load_pinned_plugins() -> list[str]:
    """
    Загружает список UUID закрепленных плагинов из кэша.

    :return: список UUID закрепленных плагинов.
    """
    if not os.path.exists("storage/cache/pinned_plugins.json"):
        return []

    with open("storage/cache/pinned_plugins.json", "r", encoding="utf-8") as f:
        try:
            return json.loads(f.read())
        except json.decoder.JSONDecodeError:
            return []


def cache_old_users(old_users: dict[int, float]):
    """
    Сохраняет в кэш список пользователей, которые уже писали на аккаунт.
    """
    if not os.path.exists("storage/cache"):
        os.makedirs("storage/cache")
    with open(f"storage/cache/old_users.json", "w", encoding="utf-8") as f:
        f.write(json.dumps(old_users, ensure_ascii=False))


def load_old_users(greetings_cooldown: float) -> dict[int, float]:
    """
    Загружает из кэша список пользователей, которые уже писали на аккаунт.

    :return: список ID чатов.
    """
    if not os.path.exists(f"storage/cache/old_users.json"):
        return dict()
    with open(f"storage/cache/old_users.json", "r", encoding="utf-8") as f:
        users = f.read()
    try:
        users = json.loads(users)
    except json.decoder.JSONDecodeError:
        return dict()
    # todo убрать позже, конвертация для старых версий бота
    if type(users) == list:
        users = {user: time.time() for user in users}
    else:
        users = {int(user): time_ for user, time_ in users.items() if
                 time.time() - time_ < greetings_cooldown * 24 * 60 * 60}
    cache_old_users(users)
    return users


def create_greeting_text(badtrip: BadTrip):
    """
    Генерирует приветствие для вывода в консоль после загрузки данных о пользователе.
    """
    account = badtrip.account
    balance = badtrip.balance
    current_time = datetime.now()
    if current_time.hour < 4:
        greetings = "Бессонная ночь"  # locale
    elif current_time.hour < 12:
        greetings = "Доброе утро"
    elif current_time.hour < 17:
        greetings = "Рабочий день"
    else:
        greetings = "Тёплый вечер"

    lines = [
        f"$MAGENTA│ $WHITE{greetings}, $CYAN{account.username}.",
        f"$MAGENTA│ $WHITEТвой ID: $YELLOW{account.id}.",
        f"$MAGENTA│ $WHITEБаланс: $CYAN{balance.total_rub} RUB $RESET| $WHITE{balance.total_usd} USD $RESET| $YELLOW{balance.total_eur} EUR",
        f"$MAGENTA│ $WHITEНезавершённых сделок: $YELLOW{account.active_sales}.",
        f"$MAGENTA│ $WHITEПрибыльного трипа! $CYAN(◉_◉)"
    ]

    length = 60
    bar = "─" * (length - 2)
    greetings_text = f"\n$MAGENTA╭{bar}╮\n"
    for line in lines:
        greetings_text += line + " " * (length - len(
            line.replace("$CYAN", "").replace("$YELLOW", "").replace("$MAGENTA", "").replace("$WHITE",
                                                                                             "").replace("$RESET",
                                                                                                         "")) - 1) + "$RESET$MAGENTA│\n"
    greetings_text += f"$MAGENTA╰{bar}╯\n"
    return greetings_text


def time_to_str(time_: int):
    """
    Конвертирует число в строку формата "Хд Хч Хмин Хсек"

    :param time_: число для конвертации.

    :return: строку-время.
    """
    days = time_ // 86400
    hours = (time_ - days * 86400) // 3600
    minutes = (time_ - days * 86400 - hours * 3600) // 60
    seconds = time_ - days * 86400 - hours * 3600 - minutes * 60

    if not any([days, hours, minutes, seconds]):  # locale
        return "0 сек"
    time_str = ""
    if days:
        time_str += f"{days}д"
    if hours:
        time_str += f" {hours}ч"
    if minutes:
        time_str += f" {minutes}мин"
    if seconds:
        time_str += f" {seconds}сек"
    return time_str.strip()


def get_month_name(month_number: int) -> str:
    """
    Возвращает название месяца в родительном падеже.

    :param month_number: номер месяца.

    :return: название месяца в родительном падеже.
    """
    months = [
        "Января", "Февраля", "Марта",
        "Апреля", "Мая", "Июня",
        "Июля", "Августа", "Сентября",
        "Октября", "Ноября", "Декабря"
    ]  # todo локализация
    if month_number > len(months):
        return months[0]
    return months[month_number - 1]


def get_products(path: str, amount: int = 1) -> list[list[str] | int] | None:
    """
    Берет из товарного файла товар/-ы, удаляет их из товарного файла.

    :param path: путь до файла с товарами.
    :param amount: кол-во товара.

    :return: [[Товар/-ы], оставшееся кол-во товара]
    """
    with get_products_file_lock(path):
        with open(path, "r", encoding="utf-8") as f:
            products = f.read()

        products = products.split("\n")

        # Убираем пустые элементы
        products = list(itertools.filterfalse(lambda el: not el, products))

        if not products:
            raise Utils.exceptions.NoProductsError(path)

        elif len(products) < amount:
            raise Utils.exceptions.NotEnoughProductsError(path, len(products), amount)

        got_products = products[:amount]
        save_products = products[amount:]
        amount = len(save_products)

        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(save_products))

        return [got_products, amount]


def add_products(path: str, products: list[str], at_zero_position=False):
    """
    Добавляет товары в файл с товарами.

    :param path: путь до файла с товарами.
    :param products: товары.
    :param at_zero_position: добавить товары в начало товарного файла.
    """
    with get_products_file_lock(path):
        if not at_zero_position:
            with open(path, "a", encoding="utf-8") as f:
                f.write("\n" + "\n".join(products))
        else:
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(products) + "\n" + text)


def safe_text(text: str):
    return "⁣".join(text)


def format_msg_text(text: str, obj: FunPayAPI.types.Message | FunPayAPI.types.ChatShortcut) -> str:
    """
    Форматирует текст, подставляя значения переменных, доступных для MessageEvent.

    :param text: текст для форматирования.
    :param obj: экземпляр types.Message или types.ChatShortcut.

    :return: форматированый текст.
    """
    date_obj = datetime.now()
    month_name = get_month_name(date_obj.month)
    date = date_obj.strftime("%d.%m.%Y")
    str_date = f"{date_obj.day} {month_name}"
    str_full_date = str_date + f" {date_obj.year} года"  # locale

    time_ = date_obj.strftime("%H:%M")
    time_full = date_obj.strftime("%H:%M:%S")

    username = obj.author if isinstance(obj, FunPayAPI.types.Message) else obj.name
    chat_name = obj.chat_name if isinstance(obj, FunPayAPI.types.Message) else obj.name
    chat_id = str(obj.chat_id) if isinstance(obj, FunPayAPI.types.Message) else str(obj.id)

    variables = {
        "$full_date_text": str_full_date,
        "$date_text": str_date,
        "$date": date,
        "$time": time_,
        "$full_time": time_full,
        "$username": safe_text(username),
        "$message_text": str(obj),
        "$chat_id": chat_id,
        "$chat_name": safe_text(chat_name)
    }

    for var in variables:
        text = text.replace(var, variables[var])
    return text


def format_order_text(text: str, order: FunPayAPI.types.OrderShortcut | FunPayAPI.types.Order) -> str:
    """
    Форматирует текст, подставляя значения переменных, доступных для Order.

    :param text: текст для форматирования.
    :param order: экземпляр Order.

    :return: форматированый текст.
    """
    date_obj = datetime.now()
    month_name = get_month_name(date_obj.month)
    date = date_obj.strftime("%d.%m.%Y")
    str_date = f"{date_obj.day} {month_name}"
    str_full_date = str_date + f" {date_obj.year} года"  # locale
    time_ = date_obj.strftime("%H:%M")
    time_full = date_obj.strftime("%H:%M:%S")
    game = subcategory_fullname = subcategory = ""
    try:
        if isinstance(order, FunPayAPI.types.OrderShortcut) and not order.subcategory:
            game, subcategory = order.subcategory_name.rsplit(", ", 1)
            subcategory_fullname = f"{subcategory} {game}"
        else:
            subcategory_fullname = order.subcategory.fullname
            game = order.subcategory.category.name
            subcategory = order.subcategory.name
    except:
        logger.warning("Ошибка парсинга игры из заказа")  # locale
        logger.debug("TRACEBACK", exc_info=True)
    description = order.description if isinstance(order,
                                                  FunPayAPI.types.OrderShortcut) else order.short_description if order.short_description else ""
    params = order.lot_params_text if isinstance(order, FunPayAPI.types.Order) and order.lot_params else ""
    variables = {
        "$full_date_text": str_full_date,
        "$date_text": str_date,
        "$date": date,
        "$time": time_,
        "$full_time": time_full,
        "$username": safe_text(order.buyer_username),
        "$order_desc_and_params": f"{description}, {params}" if description and params else f"{description}{params}",
        "$order_desc_or_params": description if description else params,
        "$order_desc": description,
        "$order_title": description,
        "$order_params": params,
        "$order_id": order.id,
        "$order_link": f"https://funpay.com/orders/{order.id}/",
        "$category_fullname": subcategory_fullname,
        "$category": subcategory,
        "$game": game
    }

    for var in variables:
        text = text.replace(var, variables[var])
    return text


def restart_program():
    """
    Полный перезапуск BadTrip.
    """
    python = sys.executable
    os.execl(python, python, *sys.argv)
    try:
        process = psutil.Process()
        for handler in process.open_files():
            os.close(handler.fd)
        for handler in process.connections():
            os.close(handler.fd)
    except:
        pass


def shut_down():
    """
    Полное отключение BadTrip.
    """
    try:
        process = psutil.Process()
        process.terminate()
    except:
        pass


def set_console_title(title: str) -> None:
    """
    Изменяет название консоли для Windows.
    """
    try:
        if os.name == 'nt':  # Windows
            import ctypes
            ctypes.windll.kernel32.SetConsoleTitleW(title)
    except:
        logger.warning("Ошибка смены названия консоли")
        logger.debug("TRACEBACK", exc_info=True)


def _console_window_size() -> tuple[int, int] | None:
    """
    Возвращает реальный видимый размер окна консоли (не буфера) на Windows.
    shutil.get_terminal_size на Windows возвращает ширину буфера, которая может быть
    намного ширине видимого окна.
    """
    if os.name != "nt":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class COORD(ctypes.Structure):
            _fields_ = [("X", wintypes.SHORT), ("Y", wintypes.SHORT)]

        class SMALL_RECT(ctypes.Structure):
            _fields_ = [("Left", wintypes.SHORT), ("Top", wintypes.SHORT),
                        ("Right", wintypes.SHORT), ("Bottom", wintypes.SHORT)]

        class CONSOLE_SCREEN_BUFFER_INFO(ctypes.Structure):
            _fields_ = [("dwSize", COORD), ("dwCursorPosition", COORD), ("wAttributes", wintypes.WORD),
                        ("srWindow", SMALL_RECT), ("dwMaximumWindowSize", COORD)]

        handle = ctypes.windll.kernel32.GetStdHandle(-11)
        info = CONSOLE_SCREEN_BUFFER_INFO()
        if not ctypes.windll.kernel32.GetConsoleScreenBufferInfo(handle, ctypes.byref(info)):
            return None
        return (info.srWindow.Right - info.srWindow.Left + 1,
                info.srWindow.Bottom - info.srWindow.Top + 1)
    except Exception:
        return None


def _anim_console():
    """
    Возвращает поток для терминальных анимаций или None, если анимацию нужно пропустить
    (нет терминала / запуск как служба).
    """
    if os.getenv("BadTrip_IS_RUNNIG_AS_SERVICE", "0") == "1":
        return None
    out = getattr(sys, "__stdout__", None)
    if out is None:
        return None
    try:
        if not out.isatty():
            return None
    except Exception:
        return None
    if os.name == "nt":
        os.system("")  # включает обработку ANSI-кодов в консоли Windows
    return out


def terminal_rain(duration: float = 3.5, fps: float = 24.0) -> None:
    """
    Анимация «дождя из символов» при запуске бота.
    Пропускается, если вывод не привязан к терминалу (например, запуск как службы).
    """
    out = _anim_console()
    if out is None:
        return

    charset = "БАДТРИПBADTRIP0123456789#$%&*+=/<>@!?~^:;"
    colors = ("\x1b[1;97m", "\x1b[1;95m", "\x1b[95m", "\x1b[35m", "\x1b[90m", "\x1b[1;35m")
    try:
        cols, rows = _console_window_size() or shutil.get_terminal_size(fallback=(80, 25))
        cols = max(12, cols)
        rows = max(8, rows)

        def make_drops(cols, rows):
            drops = []
            for x in range(cols):
                if random.random() < 0.15:
                    continue
                drop_len = random.randint(4, 10)
                drops.append({"x": x, "y": random.uniform(-drop_len, rows), "v": random.uniform(0.5, 1.8),
                              "l": drop_len})
            return drops

        drops = make_drops(cols, rows)

        out.write("\x1b[?25l\x1b[3J\x1b[2J\x1b[H")
        out.flush()
        start = time.perf_counter()
        title = "B A D T R I P"
        frame_delay = 1.0 / fps
        while time.perf_counter() - start < duration:
            frame_start = time.perf_counter()
            try:
                live = _console_window_size()
            except Exception:
                live = None
            if live:
                nc, nr = max(12, live[0]), max(8, live[1])
                if (nc, nr) != (cols, rows):
                    cols, rows = nc, nr
                    drops = make_drops(cols, rows)
            title_row = rows // 2
            title_col = max(0, (cols - len(title)) // 2)
            screen = [[" "] * cols for _ in range(rows)]
            shade = [[5] * cols for _ in range(rows)]
            for d in drops:
                head = int(d["y"])
                for k in range(d["l"]):
                    row = head - k
                    if 0 <= row < rows:
                        screen[row][d["x"]] = random.choice(charset)
                        shade[row][d["x"]] = 0 if k == 0 else 1 + 3 * k // max(1, d["l"] - 1)
            for i, ch in enumerate(title):
                screen[title_row][title_col + i] = ch
                shade[title_row][title_col + i] = 5

            buf = []
            for r in range(rows):
                line = []
                scr_row, sh_row = screen[r], shade[r]
                for c in range(cols):
                    ch = scr_row[c]
                    if ch == " ":
                        line.append(" ")
                    else:
                        line.append(colors[sh_row[c]])
                        line.append(ch)
                buf.append(f"\x1b[{r + 1};1H")
                buf.append("".join(line))
            out.write("".join(buf))
            out.flush()

            for d in drops:
                d["y"] += d["v"]
                if int(d["y"]) - d["l"] > rows:
                    d["y"] = random.uniform(-d["l"], 0)
                    d["v"] = random.uniform(0.5, 1.8)
                    d["l"] = random.randint(4, 10)
            delay = frame_delay - (time.perf_counter() - frame_start)
            if delay > 0:
                time.sleep(delay)
    except BaseException:
        pass  # любая ошибка/прерывание просто останавливает анимацию, не мешая запуску бота
    finally:
        try:
            out.write("\x1b[0m\x1b[3J\x1b[2J\x1b[H\x1b[?25h")
            out.flush()
        except Exception:
            pass


def terminal_eye(fps: float = 30.0) -> None:
    """
    Анимация «живого глаза» после дождя: миндалевидный разрез с ресницами,
    радужка с волокнами, тёмным лимбом, зрачком и бликом. Глаз открывается,
    моргает и быстро осматривается по сторонам (саккады). Символы статичны,
    цвета — как у дождя.
    """
    out = _anim_console()
    if out is None:
        return
    try:
        cols, rows = _console_window_size() or shutil.get_terminal_size(fallback=(80, 25))
        cols = max(20, cols)
        rows = max(10, rows)
    except Exception:
        cols, rows = 80, 25

    W = cols - 2
    H = rows - 2
    if W < 24 or H < 9:
        return
    eye_row = max(1, (rows - H) // 2)
    eye_col = max(1, (cols - W) // 2)

    span = float(max(6, min(H - 4, 12)))  # высота раскрытия глаза (верхнее + нижнее веко)
    bu = span * 0.58             # арка верхнего века
    bl = span * 0.42             # арка нижнего века
    cx = (W - 1) / 2
    cy = bu + 2.0 + max(0.0, (H - 3 - span) / 2)  # +2 строки сверху под ресницы
    a = min((W - 3) / 2, span * 3.6)
    if a < 8.0:
        return
    fx = 0.5                     # символы в 2 раза выше ширины: dx в колонках
    ri = span * 0.46             # радиус радужки (в строках)
    look = a * 0.45              # амплитуда движения радужки

    charset = "БАДТРИПBADTRIP0123456789#$%&*+=/<>@!?~^:;"
    DENSE = "@#%&$890"
    HOT, PINK, MAG, BR = "\x1b[1;95m", "\x1b[95m", "\x1b[35m", "\x1b[1;97m"
    SHDW = "\x1b[38;5;53m"       # тёмно-фиолетовый для теней
    fibers = ["-", "\\", "|", "/"] * 2
    dim_map = {HOT: PINK, PINK: MAG, MAG: MAG}
    bright_map = {MAG: PINK, PINK: HOT, HOT: HOT}

    # веки: на каждую колонку — кривизна и статичный символ; крутые участки
    # дуги рисуются слэшами, плоская середина — случайными символами
    up_p, lo_p, up_ch, lo_ch = {}, {}, {}, {}
    for x in range(int(round(cx - a)), int(round(cx + a)) + 1):
        u = (x - cx) / a
        if abs(u) > 1.0:
            continue
        up_p[x] = (1 - u * u) ** 0.75
        lo_p[x] = (1 - u * u) ** 1.1
    up_rows = {x: round(cy - bu * p) for x, p in up_p.items()}
    lo_rows = {x: round(cy + bl * p) for x, p in lo_p.items()}
    prev = None
    for x in sorted(up_rows):
        dy = 0 if prev is None else up_rows[x] - prev
        prev = up_rows[x]
        u = (x - cx) / a
        au = abs(u)
        if abs(dy) >= 1 and au > 0.4:
            ch = "/" if u < 0 else "\\"
            col = PINK if au < 0.8 else MAG
        else:
            ch = random.choice(DENSE)
            col = HOT if au < 0.55 else PINK
        up_ch[x] = (ch, col)
    prev = None
    for x in sorted(lo_rows):
        dy = 0 if prev is None else lo_rows[x] - prev
        prev = lo_rows[x]
        u = (x - cx) / a
        au = abs(u)
        if abs(dy) >= 1 and au > 0.4:
            ch = "/" if u < 0 else "\\"
            col = MAG
        else:
            ch = random.choice(DENSE)
            col = PINK if au < 0.55 else MAG
        lo_ch[x] = (ch, col)

    # ресницы верхнего века — плотность растёт с шириной глаза
    lashes = []
    n_lash = max(7, int(a * 0.45))
    for i in range(n_lash):
        u = -0.92 + 1.8 * i / max(1, n_lash - 1)
        x = int(round(cx + u * a))
        if x not in up_p:
            continue
        ln = 2 if abs(u) > 0.5 or random.random() < 0.5 else 1
        ch = "\\" if u < -0.35 else ("/" if u > 0.35 else "|")
        col = MAG if random.random() < 0.7 else PINK
        for k in range(ln):
            lashes.append((x, up_p[x], k, ch, col))

    # складка века — редкая ровная дуга над верхним веком
    crease = []
    for x in sorted(up_rows):
        if x % 3 == 0:
            crease.append((x, up_p[x], "~", MAG))

    # тень от верхнего века на белке — гаснет вниз за 3 строки
    shadow = []
    for x in sorted(up_rows):
        if x % 2 == 0:
            shadow.append((x, up_p[x], 1, random.choice(DENSE), MAG))
        elif random.random() < 0.4:
            shadow.append((x, up_p[x], 1, random.choice(DENSE), SHDW))
        if random.random() < 0.3:
            shadow.append((x, up_p[x], 2, random.choice(DENSE), SHDW))
        if random.random() < 0.15:
            shadow.append((x, up_p[x], 3, random.choice(DENSE), SHDW))

    # подсветка нижнего века — свет ложится на нижний край белка
    lo_hl = []
    for x in sorted(lo_rows):
        if x % 2 == 0 and random.random() < 0.6:
            lo_hl.append((x, lo_p[x], random.choice(DENSE), PINK))

    # потёки — густые от уголков и по всей нижней дуге; символы перебираются
    # в каждом кадре, дорожки слегка видимые
    tears = []
    tear_top = round(cy) + 1
    for sx in (int(round(cx - a)), int(round(cx + a))):
        for off, prob in ((-1, 0.6), (0, 0.95), (1, 0.7)):
            x = sx + off
            if x < 0 or x >= W or random.random() > prob:
                continue
            for r in range(random.randint(5, 10)):
                if random.random() < 0.2:
                    continue
                tears.append((x, tear_top + r, SHDW if random.random() < 0.8 else MAG))
    for x in sorted(lo_rows):
        if x % 3 == 0 and random.random() < 0.5:
            ry0 = int(round(cy + bl * lo_p[x])) + 1
            for r in range(random.randint(3, 7)):
                if random.random() < 0.3:
                    continue
                tears.append((x, ry0 + r, SHDW if random.random() < 0.85 else MAG))

    # зерно — мерцающий шум по всему раскрытию глаза
    grain = []
    for x in sorted(up_rows):
        for ry in range(up_rows[x] + 3, lo_rows[x] - 2):
            if random.random() < 0.18:
                grain.append((x, ry))

    # гало — редкий шум вокруг глаза снаружи
    halo = []
    for x in range(max(0, int(round(cx - a)) - 6), min(W, int(round(cx + a)) + 7)):
        inside = x in up_rows
        for ry in range(max(0, round(cy) - 3), min(H, round(cy) + 9)):
            if inside and up_rows[x] - 1 <= ry <= lo_rows[x] + 1:
                continue
            if random.random() < 0.045:
                halo.append((x, ry))

    # радужка как сфера: пустой зрачок, тёмное кольцо, яркое кольцо у зрачка,
    # тело с радиальными волокнами (свет слева сверху — тень справа снизу),
    # тёмный лимб по краю, блик
    iris = []
    rmax_y = int(ri) + 1
    rmax_x = int(ri / fx) + 1
    for dy in range(-rmax_y, rmax_y + 1):
        for dx in range(-rmax_x, rmax_x + 1):
            rc = ((dx * fx) ** 2 + dy ** 2) ** 0.5
            if rc > ri:
                continue
            t = rc / ri
            if t < 0.36:
                continue
            oct_ = int(((math.atan2(dy * 2, dx) + math.pi) % (2 * math.pi)) / (math.pi / 4)) % 8
            if t < 0.44:
                ch, col = random.choice(DENSE), MAG
            elif t < 0.56:
                ch, col = random.choice(DENSE), HOT
            else:
                ch = random.choice(charset) if random.random() < 0.35 else fibers[oct_]
                if t < 0.70:
                    col = HOT if random.random() < 0.5 else PINK
                else:
                    col = PINK if random.random() < 0.5 else MAG
                if dx > 0 and dy > 0:
                    col = dim_map[col]
                elif dx < 0 and dy < 0:
                    col = bright_map[col]
                if t >= 0.85:
                    ch, col = random.choice(DENSE), MAG
            iris.append((dx, dy, ch, col, t >= 0.56))
    gdx, gdy = int(round(-ri / fx * 0.4)), int(round(-ri * 0.45))
    iris.append((gdx, gdy, "*", BR, False))
    iris.append((gdx + 1, gdy, "*", BR, False))

    def draw_frame(ix: float, closure: float) -> None:
        bu_e, bl_e = bu * (1 - closure), bl * (1 - closure)
        yu = {x: round(cy - bu_e * p) for x, p in up_p.items()}
        yl = {x: round(cy + bl_e * p) for x, p in lo_p.items()}
        grid = [[" "] * W for _ in range(H)]
        gcol = [[None] * W for _ in range(H)]
        for x, (ch, col) in up_ch.items():
            if 0 <= yu[x] < H:
                grid[yu[x]][x] = random.choice(DENSE) if random.random() < 0.08 else ch
                gcol[yu[x]][x] = col
        for x, (ch, col) in lo_ch.items():
            if 0 <= yl[x] < H:
                grid[yl[x]][x] = random.choice(DENSE) if random.random() < 0.08 else ch
                gcol[yl[x]][x] = col
        if closure < 0.4:
            for x, p, ch, col in crease:
                ry = round(cy - bu_e * p) - 2
                if 0 <= ry < H and grid[ry][x] == " ":
                    grid[ry][x] = ch
                    gcol[ry][x] = col
        if closure < 0.5:
            for x, p, i, ch, col in lashes:
                ry = round(cy - bu_e * p) - 1 - i
                if 0 <= ry < H and grid[ry][x] == " ":
                    grid[ry][x] = ch
                    gcol[ry][x] = col
        if closure < 0.7:
            for x, p, lvl, ch, col in shadow:
                ry = round(cy - bu_e * p) + lvl
                if 0 <= ry < H and grid[ry][x] == " ":
                    grid[ry][x] = ch
                    gcol[ry][x] = col
            for x, p, ch, col in lo_hl:
                ry = round(cy + bl_e * p) - 1
                if 0 <= ry < H and grid[ry][x] == " ":
                    grid[ry][x] = ch
                    gcol[ry][x] = col
        for x, ry in grain:
            if 0 <= ry < H and x in yu and yu[x] < ry < yl[x] and grid[ry][x] == " " and random.random() < 0.8:
                grid[ry][x] = random.choice(charset)
                gcol[ry][x] = SHDW
        for x, ry in halo:
            if 0 <= ry < H and grid[ry][x] == " " and random.random() < 0.8:
                grid[ry][x] = random.choice(charset)
                gcol[ry][x] = SHDW
        tear_off = int(round(closure * 2.2))
        for x, ry, col in tears:
            ryo = ry + tear_off
            if 0 <= ryo < H and grid[ryo][x] == " ":
                grid[ryo][x] = random.choice(DENSE)
                gcol[ryo][x] = col
        if closure < 0.55:
            ixi, icy = int(round(ix)), int(round(cy - 1.1))
            for dx, dy, ch, col, body in iris:
                if body and random.random() < 0.06:
                    ch = random.choice(charset)
                px, py = ixi + dx, icy + dy
                if 0 <= px < W and 0 <= py < H and px in yu and yu[px] < py < yl[px]:
                    grid[py][px] = ch
                    gcol[py][px] = col
        parts = []
        for y in range(H):
            parts.append(f"\x1b[{eye_row + y};{eye_col}H")
            cur, run = None, []
            for x in range(W):
                col, ch = gcol[y][x], grid[y][x]
                if col != cur:
                    if run:
                        parts.append(("" if cur is None else cur) + "".join(run))
                    cur, run = col, [ch]
                else:
                    run.append(ch)
            if run:
                parts.append(("" if cur is None else cur) + "".join(run))
            parts.append("\x1b[0m")
        out.write("".join(parts))
        out.flush()

    def blink_kf(n: int):
        up_t, hold_t, dn_t, gap_t = 0.09, 0.05, 0.09, 0.06
        cyc = up_t + hold_t + dn_t
        kf = [(0.0, 0.0)]
        for i in range(n):
            b0 = i * (cyc + gap_t)
            kf += [(b0 + up_t, 1.0), (b0 + up_t + hold_t, 1.0), (b0 + cyc, 0.0)]
            if i < n - 1:
                kf.append((b0 + cyc + gap_t, 0.0))
        return kf

    def interp(kf, t):
        if t <= kf[0][0]:
            return kf[0][1]
        for (t0, v0), (t1, v1) in zip(kf, kf[1:]):
            if t <= t1:
                f = (t - t0) / (t1 - t0) if t1 > t0 else 1.0
                return v0 + (v1 - v0) * f
        return kf[-1][1]

    blink1, blink2 = blink_kf(1), blink_kf(2)
    timeline = [
        ("wake", cx, 0.22),          # глаз открывается
        ("hold", cx, 0.35),
        ("blink", blink1, blink1[-1][0]),
        ("hold", cx, 0.15),
        ("move", cx - look, 0.09),
        ("hold", cx - look, 0.55),
        ("move", cx + look, 0.09),
        ("hold", cx + look, 0.55),
        ("move", cx, 0.09),
        ("hold", cx, 0.25),
        ("blink", blink2, blink2[-1][0]),
        ("hold", cx, 0.15),
        ("move", cx - look * 0.85, 0.08),
        ("hold", cx - look * 0.85, 0.18),
        ("move", cx + look, 0.08),
        ("hold", cx + look, 0.3),
        ("move", cx, 0.08),
        ("hold", cx, 0.35),
    ]

    out.write("\x1b[?25l\x1b[3J\x1b[2J")
    out.flush()
    prev = cx
    try:
        for kind, arg, dur in timeline:
            seg_start = time.perf_counter()
            while True:
                frame_start = time.perf_counter()
                t = frame_start - seg_start
                if t >= dur:
                    break
                if kind == "move":
                    ix = prev + (arg - prev) * (t / dur)
                    draw_frame(ix, 0.0)
                elif kind == "wake":
                    draw_frame(prev, 1.0 - t / dur)
                elif kind == "blink":
                    draw_frame(prev, interp(arg, t))
                else:
                    draw_frame(arg, 0.0)
                delay = 1.0 / fps - (time.perf_counter() - frame_start)
                if delay > 0:
                    time.sleep(delay)
            if kind == "move":
                prev = arg
        draw_frame(cx, 0.0)
    except BaseException:
        pass
    finally:
        try:
            out.write("\x1b[0m\x1b[3J\x1b[2J\x1b[H\x1b[?25h")
            out.flush()
        except Exception:
            pass


SCRAMBLE_CHARS = "БАДТРИПBADTRIPbadtrip0123456789#$%&*+=/<>@!?~^:;"


def scramble_print(text: str, total_time: float = 1.2) -> None:
    """
    Печатает текст с эффектом перебора символов: каждый глиф на мгновение
    мелькает случайными символами и фиксируется. ANSI-цвета сохраняются,
    пробелы и переводы строк печатаются без перебора. Без терминала — обычный print.
    """
    out = _anim_console()
    if out is None:
        print(text)
        return
    tokens = []
    seq = ""
    for part in re.split(r"(\x1b\[[0-9;]*m)", text):
        if not part:
            continue
        if part.startswith("\x1b[") and part.endswith("m"):
            seq = "" if part == "\x1b[0m" else seq + part
            continue
        for ch in part:
            tokens.append((ch, "" if ch == "\n" else seq))
    visible = sum(1 for ch, _ in tokens if ch not in ("\n", " "))
    delay = min(0.025, max(0.004, total_time / max(visible, 1)))
    with console_lock:
        try:
            for ch, cs in tokens:
                if ch == "\n":
                    out.write("\n")
                    continue
                if ch == " ":
                    out.write(" ")
                    continue
                if cs:
                    out.write(cs)
                out.write(random.choice(SCRAMBLE_CHARS))
                out.write("\b")
                out.write(ch)
                out.flush()
                time.sleep(delay)
            out.flush()
        except BaseException:
            pass


def center_pad(text: str) -> str:
    """Возвращает отступ слева для центрирования однострочного текста по ширине консоли."""
    ws = _console_window_size()
    cols = (ws or (80, 25))[0]
    return " " * max(0, (cols - len(text)) // 2)


def _banner_lines(cols: int) -> list[str]:
    """Собирает текст баннера: компактная фиксированная ширина, буквы вплотную."""
    w = min(32, max(20, cols - 6))
    if w % 2:
        w += 1
    interior = w - 2
    title = "B A D T R I P"
    pad = max(0, (interior - len(title)) // 2)
    blank = " " * interior
    row = "║" + " " * pad + title + " " * (interior - len(title) - pad) + "║"
    bar = "═" * (w - 2)
    return ["╔" + bar + "╗", "║" + blank + "║", row, "║" + blank + "║", "╚" + bar + "╝"]


def terminal_banner(duration: float = 3.2, fps: float = 24.0) -> None:
    """
    Анимированный баннер по центру экрана: рамка собирается из середины,
    буквы перебираются случайными символами и фиксируются по одной,
    внутри и вокруг мерцает шум. Финальный кадр остаётся на экране.
    """
    out = _anim_console()
    if out is None:
        print("\n".join(_banner_lines(80)))
        return
    cols, rows = _console_window_size() or (80, 25)
    raw = _banner_lines(cols)
    bw = len(raw[0])
    bh = len(raw)
    col0 = max(0, (cols - bw) // 2)
    row0 = max(1, (rows - bh - 2) // 2)
    MAG, PINK, HOT, DIM, RESET = "\x1b[35m", "\x1b[95m", "\x1b[1;95m", "\x1b[38;5;53m", "\x1b[0m"

    mid_col = bw // 2
    born = {}
    half = (bw + 1) // 2
    for x in range(bw):
        d = abs(x - mid_col)
        born[(0, x)] = 0.35 * (1 - d / max(half, 1))
        born[(bh - 1, x)] = 0.18 + 0.35 * (1 - d / max(half, 1))
    for y in range(1, bh - 1):
        born[(y, 0)] = 0.53
        born[(y, bw - 1)] = 0.58

    letters = [(x, ch) for x, ch in enumerate(raw[2]) if ch != " "]
    settle = {x: (0.85 + 0.11 * i, ch) for i, (x, ch) in enumerate(letters)}

    noise = []
    for ry in range(-2, bh + 2):
        for _ in range(4):
            x = col0 - 10 + random.randrange(bw + 20)
            y = row0 + ry
            if 0 <= y < rows and 0 <= x < cols:
                noise.append((y, x, random.random() * 6.0))

    def draw(t: float, final: bool = False) -> None:
        grid: dict[int, dict[int, tuple[str, str]]] = {}

        def put(r, c, ch, col):
            if 0 <= r < rows and 0 <= c < cols:
                grid.setdefault(r, {})[c] = (col, ch)

        pulse = not final and (abs(t - 1.45) < 0.12 or abs(t - 2.0) < 0.12 or abs(t - 2.55) < 0.12)
        for (ry, x), b in born.items():
            if not final and t < b:
                continue
            ch = raw[ry][x]
            if not final and t - b < 0.14:
                ch = random.choice(SCRAMBLE_CHARS)
            put(row0 + ry, col0 + x, ch, PINK if pulse else MAG)
        for x, (st, ch) in settle.items():
            r, c = row0 + 2, col0 + x
            if final or t >= st:
                put(r, c, ch, HOT)
            elif t >= st - 0.22:
                put(r, c, random.choice(SCRAMBLE_CHARS), PINK if random.random() < 0.5 else MAG)
        if not final:
            for y, x, ph in noise:
                if (y, x) in grid:
                    continue
                if ((t * 6.0 + ph) % 1.0) < 0.4:
                    put(y, x, random.choice(SCRAMBLE_CHARS), DIM)
            for ry in range(1, bh - 1):
                for x in range(1, bw - 1):
                    if (row0 + ry, col0 + x) in grid:
                        continue
                    if random.random() < 0.10:
                        put(row0 + ry, col0 + x, random.choice(SCRAMBLE_CHARS), DIM)

        parts = []
        for r in range(max(0, row0 - 2), min(rows, row0 + bh + 2)):
            cells = grid.get(r)
            parts.append(f"\x1b[{r + 1};1H")
            cur, run = None, []
            for c in range(cols):
                col, ch = cells.get(c, (None, " ")) if cells else (None, " ")
                if col != cur:
                    if run:
                        parts.append(("" if cur is None else cur) + "".join(run))
                    cur, run = col, []
                run.append(ch)
            if run:
                parts.append(("" if cur is None else cur) + "".join(run))
            parts.append(RESET)
        out.write("".join(parts))
        out.flush()

    t0 = time.perf_counter()
    out.write("\x1b[?25l")
    out.flush()
    try:
        while True:
            t = time.perf_counter() - t0
            if t >= duration:
                break
            draw(t)
            time.sleep(1.0 / fps)
        draw(duration, final=True)
    except BaseException:
        pass
    finally:
        try:
            out.write("\x1b[?25h")
            out.flush()
        except Exception:
            pass


console_lock = threading.RLock()


def console_input(prompt: str = "") -> str:
    """input() без встроенного ввода-вывода: промпт печатается под console_lock,
    строка читается из stdin — чтобы поток фликера не рвал промпт."""
    out = _anim_console()
    if out is None:
        return input(prompt)
    with console_lock:
        out.write(prompt)
        out.flush()
    return sys.stdin.readline().rstrip("\n")


# Хеширование пароля
def hash_password(password: str) -> str:
    # Генерация соли и хеширование пароля
    salt = bcrypt.gensalt()
    hashed_password = bcrypt.hashpw(password.encode(), salt)
    return hashed_password.decode()  # Возвращаем хеш как строку


# Проверка пароля
def check_password(password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed_password.encode())  # Кодируем для проверки
