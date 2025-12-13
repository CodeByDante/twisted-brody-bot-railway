import firebase_admin
from firebase_admin import credentials, firestore
import os
import json

# Variable global para el cliente de Firestore
db = None

def init_firebase():
    global db
    if db is not None:
        return db

    try:
        # 1. Intentar cargar desde variable de entorno (JSON RAW)
        firebase_json = os.environ.get("FIREBASE_KEY")
        
        # 2. Si no es JSON raw, intentar ruta de archivo
        if not firebase_json:
            cred_path = os.environ.get("FIREBASE_CREDENTIALS", "firebase_credentials.json")
            if os.path.exists(cred_path):
                cred = credentials.Certificate(cred_path)
            else:
                print("⚠️ [Firebase] No se encontraron credenciales (FIREBASE_KEY ni archivo).")
                return None
        else:
            # Parsear el JSON del string
            try:
                cred_dict = json.loads(firebase_json)
                cred = credentials.Certificate(cred_dict)
            except Exception as e:
                print(f"❌ [Firebase] Error parseando FIREBASE_KEY JSON: {e}")
                return None

        # Inicializar App
        if not firebase_admin._apps:
            firebase_admin.initialize_app(cred)
        
        db = firestore.client()
        print("🔥 [Firebase] Conectado exitosamente a Firestore.")
        return db

    except Exception as e:
        print(f"❌ [Firebase] Error inicializando: {e}")
        return None

# Inicializar al importar (o llamar explícitamente en main)
init_firebase()

async def get_cached_file(video_id, quality):
    """
    Busca en la colección 'media_cache' si existe el file_id.
    Retorna el file_id o None.
    """
    if not db: return None

    try:
        # Usamos el video_id como ID del documento para búsqueda rápida O(1)
        doc_ref = db.collection('media_cache').document(str(video_id))
        doc = doc_ref.get()
        
        if doc.exists:
            data = doc.to_dict()
            # data estructura: {'mp3': 'file_id_1', '720': 'file_id_2', ...}
            return data.get(quality)
        return None
    except Exception as e:
        print(f"⚠️ [Firebase] Error leyendo cache: {e}")
        return None

async def get_cached_data(video_id):
    """
    Retorna el documento completo del cache (incluyendo meta y todos los formatos).
    """
    if not db: return None
    try:
        doc = db.collection('media_cache').document(str(video_id)).get()
        if doc.exists: return doc.to_dict()
    except Exception as e:
        print(f"⚠️ [Firebase] Error leyendo data cache: {e}")
    return None

async def save_cached_file(video_id, quality, file_id, meta=None):
    """
    Guarda o actualiza el file_id para una calidad dada.
    """
    if not db: return
    
    try:
        doc_ref = db.collection('media_cache').document(str(video_id))
        
        # Usamos set con merge=True para no borrar otras calidades
        update_data = {
            quality: file_id,
            'last_updated': firestore.SERVER_TIMESTAMP
        }
        
        if meta:
            update_data['meta'] = meta # Título, duración, etc si queremos guardar info extra
            
        doc_ref.set(update_data, merge=True)
        print(f"🔥 [Firebase] Cache guardado: {video_id} [{quality}]")
    except Exception as e:
        print(f"❌ [Firebase] Error guardando cache: {e}")
