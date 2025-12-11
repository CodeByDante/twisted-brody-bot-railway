import json
import os
from config import DB_FILE

DB_TAGS = "hashtags.json"

# --- VARIABLES GLOBALES (NO BORRAR) ---
url_storage = {}    # <-- Esta es la variable que te faltaba
user_config = {}    
downloads_db = {}   
hashtag_db = {}     # <-- Base de datos de hashtags

# --- FUNCIONES ---

def cargar_db():
    global downloads_db
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, 'r') as f:
                downloads_db.update(json.load(f))
        except:
            downloads_db = {}

def guardar_db():
    try:
        with open(DB_FILE, 'w') as f:
            json.dump(downloads_db, f, indent=4)
    except:
        pass

def load_tags():
    global hashtag_db
    if os.path.exists(DB_TAGS):
        try:
            with open(DB_TAGS, 'r', encoding='utf-8') as f:
                hashtag_db.update(json.load(f))
        except:
            hashtag_db = {}

def save_tags():
    try:
        with open(DB_TAGS, 'w', encoding='utf-8') as f:
            json.dump(hashtag_db, f, indent=4, ensure_ascii=False)
    except:
        pass

def get_config(chat_id):
    if chat_id not in user_config:
        user_config[chat_id] = {
            'lang': 'orig', 
            'fmt': 'mp4',
            'q_fixed': None, 
            'q_auto': None, 
            'meta': True,
            'aria2_enabled': True,
            'html_mode': False,
            'doc_mode': False,
            'replay_enabled': False # <--- Nuevo modo replay
        }
    return user_config[chat_id]

# Cargar base de datos al iniciar
cargar_db()
load_tags()