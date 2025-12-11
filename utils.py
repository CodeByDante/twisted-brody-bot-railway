import re
import os
import asyncio
import requests
from deep_translator import GoogleTranslator
from config import COOKIE_MAP

def format_bytes(size):
    if not size or size <= 0: return "N/A"
    power = 2**10
    n = 0
    power_labels = {0 : 'B', 1: 'KB', 2: 'MB', 3: 'GB'}
    while size > power and n < 3:
        size /= power
        n += 1
    return f"{size:.1f} {power_labels[n]}"

def limpiar_url(url):
    url = url.strip()
    if "youtube.com" in url or "youtu.be" in url:
        match = re.search(r'(?:v=|\/|shorts\/)([0-9A-Za-z_-]{11})', url)
        if match: return f"https://www.youtube.com/watch?v={match.group(1)}"
    if "eporner" in url:
        url = re.sub(r'https?://(es|de|fr|it)\.eporner\.com', 'https://www.eporner.com', url)
    if "?" in url and not any(d in url for d in ['facebook', 'instagram', 'pornhub', 'twitter', 'x.com', 'dropbox']):
        url = url.split("?")[0]
    return url

async def resolver_url_facebook(url):
    """
    Normaliza enlaces de Facebook.
    Intenta extraer el ID numérico o alfanumérico y devuelve un formato estándar.
    """
    # 1. Expandir redirecciones (fb.watch, etc)
    if "fb.watch" in url or "goo.gl" in url or "bit.ly" in url:
        try:
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
            loop = asyncio.get_running_loop()
            url = await loop.run_in_executor(None, lambda: requests.head(url, allow_redirects=True, headers=headers).url)
        except: pass

    # 2. Extraer ID y formatear según tipo
    # Reels
    match = re.search(r'/reel/([0-9A-Za-z_-]+)', url)
    if match: return f"https://www.facebook.com/reel/{match.group(1)}"

    # Videos con ID numérico (watch?v= o /videos/)
    match = re.search(r'/(?:videos|watch\?v)=([0-9]+)', url)
    if match: return f"https://www.facebook.com/video.php?v={match.group(1)}"
    
    # Share links (/share/r/..., /share/v/...) -> Dejar tal cual para que yt-dlp resuelva
    if "/share/" in url:
        return url

    return url

def sel_cookie(url):
    for k, v in COOKIE_MAP.items():
        if k in url and os.path.exists(v): return v
    return None

async def traducir_texto(texto):
    if not texto: return ""
    try:
        return await loop.run_in_executor(None, lambda: GoogleTranslator(source='auto', target='es').translate(texto))
    except: return texto

# Ruta directa a gallery-dl (Hardcoded por seguridad tras install)
# Ajustar si es necesario.
GALLERY_DL_EXEC = "gallery-dl" 
if os.path.exists(r"C:\Users\Gonzalo\AppData\Roaming\Python\Python311\Scripts\gallery-dl.exe"):
    GALLERY_DL_EXEC = r"C:\Users\Gonzalo\AppData\Roaming\Python\Python311\Scripts\gallery-dl.exe"

def descargar_galeria(url, cookie_file="cookies_x.txt"):
    """
    Descarga imágenes de X/Twitter/Facebook usando gallery-dl.
    Retorna una lista de rutas de archivos descargados y el directorio temporal.
    """
    import subprocess
    import glob
    import shutil
    
    # Directorio temporal único
    # Usamos time.time() normal ya que asyncio loop puede no estar corriendo aqui directamente o simplificar
    import time
    tmp_dir = f"tmp_gallery_{int(time.time())}"
    if not os.path.exists(tmp_dir):
        os.makedirs(tmp_dir)
    
    # Construir comando
    # gallery-dl guarda por defecto en ./gallery-dl/twitter/...
    # Usamos -d para forzar una carpeta base
    cmd = [
        GALLERY_DL_EXEC,
        "--destination", tmp_dir,
        "--no-mtime",
        "-q",
    ]
    
    if cookie_file:
        cmd.extend(["--cookies", cookie_file])
        
    cmd.append(url)
    
    print(f"📸 Ejecutando Gallery-DL ({cookie_file}): {' '.join(cmd)}")
    
    try:
        # Check=True lanza excepción si falla (exit code != 0)
        subprocess.run(cmd, check=True, timeout=120)
        
        # Buscar archivos descargados (solo imágenes)
        files = []
        exts = ['jpg', 'jpeg', 'png', 'webp'] # Solo imágenes, videos van por yt-dlp
        for ext in exts:
            files.extend(glob.glob(f"{tmp_dir}/**/*.{ext}", recursive=True))
            
        print(f"✅ Gallery-DL finalizado. Encontradas {len(files)} imágenes.")
        return files, tmp_dir
        
    except Exception as e:
        print(f"❌ Error Gallery-DL: {e}")
        # Limpiar si hubo error grave
        try: shutil.rmtree(tmp_dir)
        except: pass
        return [], None

async def scan_channel_history(client, chat_id, limit=None):
    """
    Escanea el historial del canal para indexar hashtags.
    Retorna el número de mensajes indexados.
    """
    from database import hashtag_db, save_tags
    import time
    
    print(f"🔄 Iniciando escaneo de chat: {chat_id}")
    count = 0
    msgs_indexed = 0
    msgs_with_text = 0
    
    try:
        async for msg in client.get_chat_history(chat_id, limit=limit):
            count += 1
            if count % 100 == 0: print(f"⏳ Escaneados {count} mensajes...")
            
            text = msg.text or msg.caption
            if not text:
                continue
                
            msgs_with_text += 1
            if msgs_with_text <= 3:  # Debug: mostrar primeros 3 textos
                print(f"📝 Debug texto encontrado: {text[:100]}")
            
            # Buscar Hashtags
            tags = re.findall(r"#(\w+)", text)
            if tags:
                if msgs_indexed == 0:  # Debug: mostrar el primer tag encontrado
                    print(f"✅ Primer hashtag detectado: {tags}")
                    
                for tag in tags:
                    tag_clean = tag.lower()
                    if tag_clean not in hashtag_db: hashtag_db[tag_clean] = []
                    
                    # Evitar duplicados exactos (mismo mensaje)
                    exists = any(item['id'] == msg.id and item['chat'] == msg.chat.id for item in hashtag_db[tag_clean])
                    if not exists:
                        # Guardamos ID mensaje y Chat ID
                        hashtag_db[tag_clean].append({
                            'id': msg.id,
                            'chat': msg.chat.id
                        })
                msgs_indexed += 1
                
        save_tags()
        print(f"✅ Escaneo completado. Total mensajes: {count}, Con texto: {msgs_with_text}, Con tags: {msgs_indexed}")
        return msgs_indexed
        
    except Exception as e:
        print(f"❌ Error escaneando: {e}")
        import traceback
        traceback.print_exc()
        return 0
