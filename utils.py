import re
import os
import asyncio
import requests
from deep_translator import GoogleTranslator
from config import COOKIE_MAP, TOOLS_DIR

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
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, lambda: GoogleTranslator(source='auto', target='es').translate(texto))
    except Exception as e:
        print(f"Translation error: {e}")
        return texto

# Ruta a gallery-dl
# Prioridad: 1. Pip Install (Latest) | 2. Tools Local (Portable) | 3. System Path
PIP_GALLERY_PATH = r"C:\Users\Gonzalo\AppData\Roaming\Python\Python311\Scripts\gallery-dl.exe"
TOOLS_GALLERY_PATH = os.path.join(TOOLS_DIR, "gallery-dl.exe")

if os.path.exists(PIP_GALLERY_PATH):
    GALLERY_DL_EXEC = PIP_GALLERY_PATH
elif os.path.exists(TOOLS_GALLERY_PATH):
    GALLERY_DL_EXEC = TOOLS_GALLERY_PATH
else:
    GALLERY_DL_EXEC = "gallery-dl"

def descargar_galeria(url, cookie_file=None):
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
        "--config", "gallery-dl.conf",
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

def split_video_generic(input_path, mode, value):
    """
    Divide video por: 'parts', 'min', 'sec'.
    mode: 'parts' (value=num), 'min' (value=minutos), 'sec' (value=segundos)
    """
    import subprocess
    import glob
    import os
    
    if not os.path.exists(input_path): return []
    
    try:
        # 1. Obtener duración
        cmd_dur = [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", input_path
        ]
        duration = float(subprocess.check_output(cmd_dur).decode().strip())
    except Exception as e:
        print(f"Error duration: {e}")
        return []

    if duration < 1: return []

    # 2. Calcular segment_time
    segment_time = 0
    if mode == 'parts':
        segment_time = duration / int(value)
    elif mode == 'min':
        segment_time = float(value) * 60
    elif mode == 'sec':
        segment_time = float(value)
        
    if segment_time <= 0: return []
    
    # 3. Directorio salida
    base_dir = os.path.dirname(input_path)
    base_name = os.path.splitext(os.path.basename(input_path))[0]
    output_pattern = os.path.join(base_dir, f"{base_name}_part%03d.mp4")
    
    # 4. Dividir
    cmd_split = [
        "ffmpeg", "-y", "-i", input_path, "-c", "copy",
        "-f", "segment", "-segment_time", str(segment_time),
        "-reset_timestamps", "1", output_pattern
    ]
    
    # print(f"✂️ Splitting {mode}={value} (seg={segment_time:.2f})")
    subprocess.run(cmd_split, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    # 5. Listar resultados
    parts = sorted(glob.glob(os.path.join(base_dir, f"{base_name}_part*.mp4")))
    return parts

def get_video_metadata(path):
    """Retorna (width, height) del video."""
    import subprocess
    import json
    try:
        cmd = [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height", "-of", "json", path
        ]
        # Si no hay json en imports globales... importarlo dentro.
        out = subprocess.check_output(cmd).decode()
        data = json.loads(out)
        w = data['streams'][0]['width']
        h = data['streams'][0]['height']
        return w, h
    except Exception as e:
        print(f"Meta Error: {e}")
        return 0, 0

def compress_video_ffmpeg(input_path, crf=28, preset="fast"):
    """
    Comprime video usando FFmpeg + libx264.
    crf: 0-51 (23=default, 28=whatsapp, 35=potato).
    Retorna ruta del archivo comprimido o None si falla.
    """
    import subprocess
    import os
    
    if not os.path.exists(input_path): return None
    
    base_dir = os.path.dirname(input_path)
    base_name = os.path.splitext(os.path.basename(input_path))[0]
    output_path = os.path.join(base_dir, f"compressed_{base_name}.mp4")
    
    try:
        # Comando FFmpeg simple
        # -v error: menos spam
        # -c:v libx264: codec video
        # -crf: factor calidad
        # -preset: velocidad
        # -c:a copy: copiar audio sin tocar (más rápido)
        cmd = [
            "ffmpeg", "-y", "-i", input_path,
            "-c:v", "libx264", "-crf", str(crf), "-preset", preset,
            "-c:a", "copy",
            output_path
        ]
        
        print(f"🗜 Iniciando compresión (CRF={crf}): {input_path}")
        subprocess.run(cmd, check=True) # Check lanza error si falla
        
        if os.path.exists(output_path):
            return output_path
        return None
        
    except Exception as e:
        print(f"❌ Error compresión: {e}")
        return None

def cut_video_range(input_path, start, end):
    """
    Corta un rango específico.
    start/end: strings formato HH:MM:SS o MM:SS o segundos.
    """
    import subprocess
    import os
    
    if not os.path.exists(input_path): return None
    
    base_dir = os.path.dirname(input_path)
    base_name = os.path.splitext(os.path.basename(input_path))[0]
    
    # Limpiar caracteres raros en tiempos para nombre archivo
    s_safe = str(start).replace(":", "-")
    e_safe = str(end).replace(":", "-")
    output_path = os.path.join(base_dir, f"cut_{base_name}_{s_safe}_to_{e_safe}.mp4")
    
    try:
        # Usamos -ss antes de -i para fast seek
        # -to especifica el punto final (no duración)
        # -c copy para velocidad máxima
        cmd = [
            "ffmpeg", "-y", 
            "-ss", str(start),
            "-to", str(end),
            "-i", input_path,
            "-c", "copy",
            "-avoid_negative_ts", "make_zero",
            output_path
        ]
        
        print(f"✂️ Cutting range {start} -> {end}")
        subprocess.run(cmd, check=True)
        
        if os.path.exists(output_path):
            return output_path
        return None
    except Exception as e:
        print(f"❌ Cut Error: {e}")
        return None
