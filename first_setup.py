"""
В данном модуле написана подпрограмма первичной настройки BadTrip'а.
"""

import os
from configparser import ConfigParser
import time
import telebot
from colorama import Fore, Style
from Utils.badtrip_tools import validate_proxy, hash_password, build_proxy, check_proxy, scramble_print, console_input
from Utils.config_loader import load_main_config

# locale#locale#locale
default_config = {
    "FunPay": {
        "golden_key": "",
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36",
        "autoRaise": "0",
        "autoResponse": "0",
        "autoDelivery": "0",
        "multiDelivery": "0",
        "autoRestore": "0",
        "autoDisable": "0",
        "oldMsgGetMode": "0",
        "locale": "ru"
    },
    "Telegram": {
        "enabled": "0",
        "token": "",
        "secretKeyHash": "ХешСекретногоПароля",
        "blockLogin": "0",
        "proxy": ""
    },

    "BlockList": {
        "blockDelivery": "0",
        "blockResponse": "0",
        "blockNewMessageNotification": "0",
        "blockNewOrderNotification": "0",
        "blockCommandNotification": "0"
    },

    "NewMessageView": {
        "includeMyMessages": "1",
        "includeFPMessages": "1",
        "includeBotMessages": "0",
        "notifyOnlyMyMessages": "0",
        "notifyOnlyFPMessages": "0",
        "notifyOnlyBotMessages": "0",
        "showImageName": "1"
    },

    "Greetings": {
        "ignoreSystemMessages": "0",
        "onlyNewChats": "0",
        "sendGreetings": "0",
        "greetingsText": "Привет, $chat_name!",
        "greetingsCooldown": "2"
    },

    "OrderConfirm": {
        "watermark": "1",
        "sendReply": "0",
        "replyText": "$username, спасибо за подтверждение заказа $order_id!\nЕсли не сложно, оставь, пожалуйста, отзыв!"
    },

    "ReviewReply": {
        "star1Reply": "0",
        "star2Reply": "0",
        "star3Reply": "0",
        "star4Reply": "0",
        "star5Reply": "0",
        "star1ReplyText": "",
        "star2ReplyText": "",
        "star3ReplyText": "",
        "star4ReplyText": "",
        "star5ReplyText": "",
    },

    "Proxy": {
        "enable": "0",
        "proxy": "",
        "check": "0"
    },

    "Other": {
        "watermark": "",
        "requestsDelay": "4",
        "language": "ru"
    }
}


def create_configs():
    if not os.path.exists("configs/auto_response.cfg"):
        with open("configs/auto_response.cfg", "w", encoding="utf-8"):
            ...

    if not os.path.exists("configs/auto_delivery.cfg"):
        with open("configs/auto_delivery.cfg", "w", encoding="utf-8"):
            ...


def create_config_obj(settings) -> ConfigParser:
    """
    Создает объект конфига с нужными настройками.

    :param settings: dict настроек.

    :return: объект конфига.
    """
    config = ConfigParser(delimiters=(":",), interpolation=None)
    config.optionxform = str
    config.read_dict(settings)
    return config


def contains_russian(text: str) -> bool:
    for char in text:
        if 'А' <= char <= 'я' or char in 'Ёё':
            return True
    return False

def input_proxy(set_telebot_proxy: bool = False) -> str | None:
    while True:
        proxy_input = console_input(f"{Fore.MAGENTA}{Style.BRIGHT}╰──> {Style.RESET_ALL}").strip()

        if not proxy_input:
            if set_telebot_proxy:
                telebot.apihelper.proxy = None
            return None

        try:
            scheme, login, password, ip, port = validate_proxy(proxy_input)
            proxy = build_proxy(scheme, login, password, ip, port)

            if not check_proxy({"http": proxy, "https": proxy}):
                scramble_print(f"\n{Fore.WHITE}{Style.BRIGHT}Прокси не работает. Ещё раз. "
                               f"{Fore.RED}(⊙_⊙){Style.RESET_ALL}")
                continue

            if set_telebot_proxy:
                telebot.apihelper.proxy = {"http": proxy, "https": proxy}

            return proxy

        except Exception as ex:
            scramble_print(f"\n{Fore.WHITE}{Style.BRIGHT}Кривой формат: {ex}. Ещё раз. "
                           f"{Fore.RED}(⊙_⊙){Style.RESET_ALL}")

def setup_telegram_proxy():
    config = load_main_config("configs/_main.cfg")
    scramble_print(
        f"\n{Fore.MAGENTA}{Style.BRIGHT}╭── {Fore.WHITE}" f"IPv4-прокси для доступа к Telegram"
        f" (scheme://login:password@ip:port или ip:port, Enter — пропустить). "
        f"{Fore.RED}(◉_◉){Style.RESET_ALL}")
    while True:
        try:
            proxy = input_proxy(set_telebot_proxy=True)
            username = telebot.TeleBot(config["Telegram"]["token"]).get_me().username
            scramble_print(f"\n\n{Fore.WHITE}Telegram подключен: @{username}.{Style.RESET_ALL}")
            break
        except Exception as ex:
            scramble_print(f"\n\n{Fore.WHITE}Не подключилось: {ex}.{Style.RESET_ALL}")

    config.set("Telegram", "proxy", proxy or "")
    scramble_print(f"{Fore.WHITE}Сохраняю...{Style.RESET_ALL}")
    with open("configs/_main.cfg", "w", encoding="utf-8") as f:
        config.write(f)
    time.sleep(5)


def first_setup():
    config = create_config_obj(default_config)
    sleep_time = 1

    scramble_print(f"{Fore.WHITE}{Style.BRIGHT}Йо. Первый запуск BadTrip. {Fore.RED}(◉_◉){Style.RESET_ALL}")
    time.sleep(sleep_time)

    scramble_print(f"\n{Fore.WHITE}{Style.BRIGHT}Конфига нет — свежая установка. {Fore.RED}(⊙_⊙){Style.RESET_ALL}")
    time.sleep(sleep_time)

    scramble_print(f"\n{Fore.WHITE}{Style.BRIGHT}Настроим за минуту. {Fore.RED}(⌐■_■){Style.RESET_ALL}")
    time.sleep(sleep_time)

    while True:
        scramble_print(f"\n{Fore.MAGENTA}{Style.BRIGHT}╭── {Fore.WHITE}"
              f"Вставь golden_key — он в куках FunPay (расширение EditThisCookie). {Fore.RED}(◉_◉){Style.RESET_ALL}")
        golden_key = console_input(f"{Fore.MAGENTA}{Style.BRIGHT}╰──> {Style.RESET_ALL}").strip()
        if len(golden_key) != 32:
            scramble_print(
                f"\n{Fore.WHITE}{Style.BRIGHT}32 символа, это не он. Ещё раз. {Fore.RED}(⊙_⊙){Style.RESET_ALL}")
            continue
        config.set("FunPay", "golden_key", golden_key)
        break

    while True:
        scramble_print(f"\n{Fore.MAGENTA}{Style.BRIGHT}╭── {Fore.WHITE}"
              f"User-agent (Enter — оставим стандарт). "
              f"{Fore.RED}(⌐■_■){Style.RESET_ALL}")
        user_agent = console_input(f"{Fore.MAGENTA}{Style.BRIGHT}╰──> {Style.RESET_ALL}").strip()
        if contains_russian(user_agent):
            scramble_print(
                f"\n{Fore.WHITE}{Style.BRIGHT}Русскими буквами не бывает. Ещё раз. {Fore.RED}(¬_¬){Style.RESET_ALL}")
            continue
        if user_agent:
            config.set("FunPay", "user_agent", user_agent)
        break

    scramble_print(f"\n{Fore.MAGENTA}{Style.BRIGHT}╭── {Fore.WHITE}" f"IPv4-прокси для Telegram"
          f" (scheme://login:password@ip:port или ip:port, Enter — пропустить). "
          f"{Fore.RED}(◉_◉){Style.RESET_ALL}")
    proxy = input_proxy(set_telebot_proxy=True)

    if proxy:
        config.set("Telegram", "proxy", proxy)


    while True:
        scramble_print(
            f"\n{Fore.MAGENTA}{Style.BRIGHT}╭── {Fore.WHITE}Токен бота от @BotFather (юзернейм начинается с \"funpay\"). "
            f"{Fore.RED}(◉_◉){Style.RESET_ALL}")
        token = console_input(f"{Fore.MAGENTA}{Style.BRIGHT}╰──> {Style.RESET_ALL}").strip()
        try:
            if not token or not token.split(":")[0].isdigit():
                raise Exception("Неправильный формат токена")
            username = telebot.TeleBot(token).get_me().username
            if not username.lower().startswith("funpay"):
                scramble_print(
                    f"\n{Fore.WHITE}{Style.BRIGHT}Юзернейм должен начинаться с \"funpay\". {Fore.RED}(⊙_⊙){Style.RESET_ALL}")
                continue
        except Exception as ex:
            s = ""
            if str(ex):
                s = f" ({str(ex)})"
            scramble_print(f"\n{Fore.WHITE}{Style.BRIGHT}Не вышло{s}. Ещё раз. {Fore.RED}(⊙_⊙){Style.RESET_ALL}")
            continue
        break

    while True:
        scramble_print(
            f"\n{Fore.MAGENTA}{Style.BRIGHT}╭── {Fore.WHITE}Пароль для бота: 8+ символов, заглавные, строчные, цифра. "
            f" {Fore.RED}(⌐■_■){Style.RESET_ALL}")
        password = console_input(f"{Fore.MAGENTA}{Style.BRIGHT}╰──> {Style.RESET_ALL}").strip()
        if len(password) < 8 or password.lower() == password or password.upper() == password or not any(
                [i.isdigit() for i in password]):
            scramble_print(
                f"\n{Fore.WHITE}{Style.BRIGHT}Слабый пароль. Крепче. {Fore.RED}(⊙_⊙){Style.RESET_ALL}")
            continue
        break

    config.set("Telegram", "enabled", "1")
    config.set("Telegram", "token", token)
    config.set("Telegram", "secretKeyHash", hash_password(password))

    scramble_print(f"\n{Fore.MAGENTA}{Style.BRIGHT}╭── {Fore.WHITE}" f"IPv4-прокси для FunPay"
          f" (scheme://login:password@ip:port или ip:port, Enter — пропустить). "
          f"{Fore.RED}(⌐■_■){Style.RESET_ALL}")
    proxy = input_proxy(set_telebot_proxy=True)

    if proxy:
        config.set("Proxy", "proxy", proxy)
        config.set("Proxy", "enable", "1")
        config.set("Proxy", "check", "1")

    scramble_print(f"\n{Fore.WHITE}{Style.BRIGHT}Готово. Конфиг сохранён. "
          f"{Fore.RED}(◉_◉){Style.RESET_ALL}")
    scramble_print(f"{Fore.WHITE}{Style.BRIGHT}Запусти меня снова — дальше всё в Telegram-боте. "
          f"{Fore.RED}(⌐■_■){Style.RESET_ALL}")
    with open("configs/_main.cfg", "w", encoding="utf-8") as f:
        config.write(f)
    time.sleep(10)
