import time
from pip._internal.cli.main import main

# todo убрать когда-то

try:
    import lxml
except ModuleNotFoundError:
    main(["install", "-U", "lxml>=5.3.0"])
except:
    pass
try:
    import bcrypt
except ModuleNotFoundError:
    main(["install", "-U", "bcrypt>=4.2.0"])
except:
    pass
try:
    import socks
except ModuleNotFoundError:
    main(["install", "-U", "pysocks>=1.7.1"])
except:
    pass
import Utils.badtrip_tools
import Utils.config_loader as cfg_loader
from first_setup import first_setup
from colorama import Fore, Style
from Utils.logger import configure_logging
import logging
import colorama
import sys
import os
from badtrip import BadTrip
import Utils.exceptions as excs
from locales.localizer import Localizer

VERSION = "0.1.1"

Utils.badtrip_tools.set_console_title(f"BadTrip v{VERSION}")

if getattr(sys, 'frozen', False):
    os.chdir(os.path.dirname(sys.executable))
else:
    os.chdir(os.path.dirname(__file__))

folders = ["configs", "logs", "storage", "storage/cache", "storage/plugins", "storage/products", "plugins"]
for i in folders:
    if not os.path.exists(i):
        os.makedirs(i)

files = ["configs/auto_delivery.cfg", "configs/auto_response.cfg"]
for i in files:
    if not os.path.exists(i):
        with open(i, "w", encoding="utf-8") as f:
            ...

colorama.init()

Utils.badtrip_tools.terminal_rain()
Utils.badtrip_tools.terminal_eye()

configure_logging()
logging.raiseExceptions = False
logger = logging.getLogger("main")
logger.debug("------------------------------------------------------------------")

Utils.badtrip_tools.terminal_banner()
Utils.badtrip_tools.scramble_print(
    f"\n{Utils.badtrip_tools.center_pad('v' + VERSION)}"
    f"{Fore.WHITE}{Style.BRIGHT}v{VERSION}{Style.RESET_ALL}\n")  # locale

if not os.path.exists("configs/_main.cfg"):
    first_setup()
    sys.exit()

if sys.platform == "linux" and os.getenv('BadTrip_IS_RUNNIG_AS_SERVICE', '0') == '1':
    import getpass

    pid = str(os.getpid())
    pidFile = open(f"/run/BadTrip/{getpass.getuser()}/BadTrip.pid", "w")
    pidFile.write(pid)
    pidFile.close()

    logger.info(f"$GREENPID-файл готов, PID процесса: {pid}")  # locale


try:
    MAIN_CFG = cfg_loader.load_main_config("configs/_main.cfg")
    localizer = Localizer(MAIN_CFG["Other"]["language"])
    _ = localizer.translate

    AR_CFG = cfg_loader.load_auto_response_config("configs/auto_response.cfg")
    RAW_AR_CFG = cfg_loader.load_raw_auto_response_config("configs/auto_response.cfg")

    AD_CFG = cfg_loader.load_auto_delivery_config("configs/auto_delivery.cfg")
except excs.ConfigParseError as e:
    logger.error(e)
    logger.error("Гашусь...")  # locale
    time.sleep(5)
    sys.exit()
except UnicodeDecodeError:
    logger.error("UTF-8 не разжевался. Проверь: кодировка файла = UTF-8, "
                 "концы строк = LF.")  # locale
    logger.error("Гашусь...")  # locale
    time.sleep(5)
    sys.exit()
except:
    logger.critical("Непредвиденная ошибка. Трип прерван.")  # locale
    logger.warning("TRACEBACK", exc_info=True)
    logger.error("Гашусь...")  # locale
    time.sleep(5)
    sys.exit()

localizer = Localizer(MAIN_CFG["Other"]["language"])

try:
    BadTrip(MAIN_CFG, AD_CFG, AR_CFG, RAW_AR_CFG, VERSION).init().run()
except KeyboardInterrupt:
    logger.info("Гашусь...")  # locale
    sys.exit()
except:
    logger.critical("BadTrip упал с необработанной ошибкой.")  # locale
    logger.warning("TRACEBACK", exc_info=True)
    logger.critical("Гашусь...")  # locale
    time.sleep(5)
    sys.exit()
