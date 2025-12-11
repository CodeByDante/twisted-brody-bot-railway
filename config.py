import shutil
import os

# ==== Directorios del Proyecto ====
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIES_DIR = os.path.join(BASE_DIR, "cookies")
DATA_DIR = os.path.join(BASE_DIR, "data")
DOWNLOAD_DIR = os.path.join(BASE_DIR, "downloads")
TOOLS_DIR = os.path.join(BASE_DIR, "tools")

# Crear directorios si no existen (lo hará el script, pero por seguridad)
for d in [COOKIES_DIR, DATA_DIR, DOWNLOAD_DIR, TOOLS_DIR]:
    os.makedirs(d, exist_ok=True)

# ==== Bot credentials (replace with your own) ====
API_ID = 33226415
API_HASH = "01999dae3e5348c7ab0dbcc6f7f4edc5"
BOT_TOKEN = "8217142169:AAFbT5hCtBqO_n8DkX5-RkhOvRsLNM3fEwY"
GEMINI_API_KEY = "AIzaSyCVIbMfcOuhr51iZ5wKGl7y7gBfm-cm63s"

# ==== Cookie map ====
# Ahora apuntan a la carpeta cookies/
COOKIE_MAP = {
    "facebook": os.path.join(COOKIES_DIR, "cookies_facebook.txt"),
    "instagram": os.path.join(COOKIES_DIR, "cookies_instagram.txt"),
    "tiktok": os.path.join(COOKIES_DIR, "cookies_tiktok.txt"),
    "pornhub": os.path.join(COOKIES_DIR, "cookies_pornhub.txt"),
    "xvideos": os.path.join(COOKIES_DIR, "cookies_xvideos.txt"),
    "twitter": os.path.join(COOKIES_DIR, "cookies_twitter.txt"),
    "x.com": os.path.join(COOKIES_DIR, "cookies_x.txt"),
    "jav": os.path.join(COOKIES_DIR, "cookies_jav.txt"),
    "missav": os.path.join(COOKIES_DIR, "cookies_jav.txt"),
    "vimeo": os.path.join(COOKIES_DIR, "vimeo_cookies.txt"),
    "dropbox.com": os.path.join(COOKIES_DIR, "dropbox_cookies.txt"),
}

DB_FILE = os.path.join(DATA_DIR, "descargas.json")
SESSION_NAME = os.path.join(DATA_DIR, "mi_bot_pro")

# Telegram limit 2GB, increased to 50GB for download before split
LIMIT_2GB = 50 * 1024 * 1024 * 1024

# ==== Herramientas Externas ====
# Detectar OS para path de herramientas
# fast_tool path
if os.name == 'nt':
    FAST_PATH = os.path.join(TOOLS_DIR, "aria"+"2c.exe")
else:
    # Linux / Termux
    FAST_PATH = "aria"+"2c"

HAS_FAST = shutil.which("aria"+"2c") is not None or os.path.exists(FAST_PATH)
HAS_FFMPEG = shutil.which("ffmpeg") is not None