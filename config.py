import shutil

# ==== Bot credentials (replace with your own) ====
API_ID = 33226415
API_HASH = "01999dae3e5348c7ab0dbcc6f7f4edc5"
BOT_TOKEN = "8584312169:AAHQjPutXzS6sCPQ-NxIKp_5GsmjmvI9TEw"

# ==== Cookie map ====
COOKIE_MAP = {
    "facebook": "cookies_facebook.txt",
    "instagram": "cookies_instagram.txt",
    "tiktok": "cookies_tiktok.txt",
    "pornhub": "cookies_pornhub.txt",
    "xvideos": "cookies_xvideos.txt",
    "twitter": "cookies_twitter.txt",
    "x.com": "cookies_x.txt",
    "jav": "cookies_jav.txt",
    "missav": "cookies_jav.txt",
    "vimeo": "vimeo_cookies.txt",
    "dropbox.com": "dropbox_cookies.txt",
}

DB_FILE = "descargas.json"
# Telegram limit 2GB, increased to 50GB for download before split
LIMIT_2GB = 50 * 1024 * 1024 * 1024

# HAS_ARIA2 = shutil.which("aria2c") is not None
HAS_ARIA2 = False # Desactivado por ban de Railway
HAS_FFMPEG = shutil.which("ffmpeg") is not None