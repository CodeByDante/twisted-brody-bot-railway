import os
import time
import asyncio
import subprocess
import json
import re
import shutil
import urllib.parse
import html
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait
from deep_translator import GoogleTranslator
import yt_dlp

# --- IMPORTANTE: PLAYWRIGHT ---
from playwright.async_api import async_playwright

# --- TUS DATOS ---
API_ID = 33226415                  
API_HASH = "01999dae3e5348c7ab0dbcc6f7f4edc5"
BOT_TOKEN = "8584312169:AAHQjPutXzS6sCPQ-NxIKp_5GsmjmvI9TEw"

# --- COOKIES ---
COOKIE_MAP = {
    'tiktok': 'cookies_tiktok.txt',
    'facebook': 'cookies_facebook.txt',
    'pornhub': 'cookies_pornhub.txt',
    'x.com': 'cookies_x.txt',
    'twitter': 'cookies_x.txt',
    'xvideos': 'cookies_xvideos.txt',
}

DB_FILE = 'descargas.json'
LIMIT_2GB = 9999 * 1024 * 1024 # Sin límites 

HAS_ARIA2 = shutil.which("aria2c") is not None
HAS_FFMPEG = shutil.which("ffmpeg") is not None

url_storage = {}
user_config = {} 
downloads_db = {}

print("🚀 Iniciando Bot Pro (Playwright Sniffer Reforzado + Fix)...")

# --- CACHE DB ---
def cargar_db():
    global downloads_db
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, 'r') as f: downloads_db = json.load(f)
        except: downloads_db = {}

def guardar_db():
    try:
        with open(DB_FILE, 'w') as f: json.dump(downloads_db, f, indent=4)
    except: pass

cargar_db()

app = Client("mi_bot_pro", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, workers=16)

# --- 1. CONFIGURACIÓN ---

def get_config(chat_id):
    if chat_id not in user_config:
        user_config[chat_id] = {
            'lang': 'orig', 'fmt': 'mp4',
            'q_fixed': None, 'q_auto': None, 'meta': True,
            'html_mode': False 
        }
    return user_config[chat_id]

def format_bytes(size):
    if not size or size <= 0: return "N/A"
    power = 2**10
    n = 0
    power_labels = {0 : 'B', 1: 'KB', 2: 'MB', 3: 'GB'}
    while size > power and n < 3:
        size /= power
        n += 1
    return f"{size:.1f} {power_labels[n]}"

# =========================================================================
# 🕵️ SNIFFER AVANZADO CON PLAYWRIGHT (MEJORADO: CLICKS REALES)
# =========================================================================

# Sniffer function removed

# =========================================================================

# --- UTILS ---

def limpiar_url(url):
    if "youtube.com" in url or "youtu.be" in url:
        match = re.search(r'(?:v=|\/|shorts\/)([0-9A-Za-z_-]{11})', url)
        if match: return f"https://www.youtube.com/watch?v={match.group(1)}"
    if "eporner" in url:
        url = re.sub(r'https?://(es|de|fr|it)\.eporner\.com', 'https://www.eporner.com', url)
    return url.split("?")[0]

def sel_cookie(url):
    for k, v in COOKIE_MAP.items():
        if k in url and os.path.exists(v): return v
    return None

async def traducir_texto(texto):
    if not texto: return ""
    try:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, lambda: GoogleTranslator(source='auto', target='es').translate(texto))
    except: return texto

# --- FFMPEG & PROGRESO ---

async def get_thumb(path, cid, ts):
    out = f"t_{cid}_{ts}.jpg"
    if HAS_FFMPEG:
        try:
            await (await asyncio.create_subprocess_exec("ffmpeg", "-i", path, "-ss", "00:00:02", "-vframes", "1", out, "-y", stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)).wait()
            if os.path.exists(out): return out
        except: pass
    return None

async def get_meta(path):
    if not HAS_FFMPEG: return 0,0,0
    try:
        p = await asyncio.create_subprocess_exec("ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height,duration", "-of", "json", path, stdout=subprocess.PIPE)
        d = json.loads((await p.communicate())[0])
        s = d['streams'][0]
        return int(s.get('width',0)), int(s.get('height',0)), int(float(s.get('duration',0)))
    except: return 0,0,0

async def get_audio_dur(path):
    try:
        p = await asyncio.create_subprocess_exec("ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", path, stdout=subprocess.PIPE)
        return int(float(json.loads((await p.communicate())[0])['format']['duration']))
    except: return 0

async def progreso(cur, tot, msg, times, act):
    now = time.time()
    if (now - times[1]) > 4 or cur == tot:
        times[1] = now
        try:
            await msg._client.send_chat_action(msg.chat.id, act)
            per = cur * 100 / tot
            txt = f"📤 **Subiendo...**\n📊 {per:.1f}% | 📦 {cur/1048576:.1f}/{tot/1048576:.1f} MB"
            await msg.edit_text(txt)
        except: pass

# --- PROCESO DE DESCARGA (CORREGIDO) ---

async def procesar_descarga(client, chat_id, url, calidad, datos, msg_orig):
    conf = get_config(chat_id)
    vid_id = datos.get('id')
    
    # --- CORRECCIÓN VARIABLES ---
    # Definimos esto AL PRINCIPIO para evitar 'UnboundLocalError' en el finally
    final = None
    thumb = None
    ts = int(time.time())
    status = None
    # ----------------------------

    url_descarga = url
    if calidad.startswith("html_"):
        idx = int(calidad.split("_")[1])
        if 'html_links_data' in datos and len(datos['html_links_data']) > idx:
            url_descarga = datos['html_links_data'][idx]['url']
            ckey = f"html_{idx}" 
        else:
            await client.send_message(chat_id, "❌ Enlace expirado.")
            return
    else:
        ckey = "mp3" if calidad == "mp3" else calidad
    
    # Revisar Cache
    if vid_id and vid_id in downloads_db and ckey in downloads_db[vid_id]:
        try:
            fid = downloads_db[vid_id][ckey]
            cap = f"🎬 **{datos.get('titulo','Video')}**\n✨ (Cache)"
            if calidad == "mp3": await client.send_audio(chat_id, fid, caption=cap)
            else: await client.send_video(chat_id, fid, caption=cap)
            return
        except: pass

    try:
        status = await client.send_message(chat_id, f"⏳ **Procesando...**\n📥 {calidad}")
        
        opts = {
            'outtmpl': f"dl_{chat_id}_{ts}.%(ext)s",
            'quiet': True, 'no_warnings': True, 'max_filesize': LIMIT_2GB,
            'http_headers': {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        }

        if calidad == "mp3":
            opts.update({'format': 'bestaudio/best', 'postprocessors': [{'key': 'FFmpegExtractAudio','preferredcodec': 'mp3'}]})
        elif calidad.startswith("html_"):
            opts['format'] = 'best'
        else:
            # Aquí usamos el format ID si viene del botón de YT-DLP, o 'best'
            if calidad.isdigit() or "x" in calidad: # Si es resolución o ID
                 opts['format'] = f"bv*[height<={calidad.split('x')[-1]}]+ba/b[height<={calidad.split('x')[-1]}] / best"
            else:
                 opts['format'] = 'best'
            opts['merge_output_format'] = 'mp4'

        if "eporner" in url_descarga: opts.update({'external_downloader': None, 'nocheckcertificate': True})
        elif "pornhub" in url_descarga: opts.update({'cookiefile': 'cookies_pornhub.txt', 'nocheckcertificate': True})
        else:
            c = sel_cookie(url_descarga)
            if c: opts['cookiefile'] = c
            if HAS_ARIA2 and not calidad.startswith("html_"): 
                opts.update({'external_downloader': 'aria2c', 'external_downloader_args': ['-x','16','-k','1M']})

        loop = asyncio.get_running_loop()
        with yt_dlp.YoutubeDL(opts) as ydl:
            await loop.run_in_executor(None, lambda: ydl.download([url_descarga]))
        
        base = f"dl_{chat_id}_{ts}"
        if calidad == "mp3": final = f"{base}.mp3"
        else:
            for e in ['.mp4','.mkv','.webm']:
                if os.path.exists(base+e): 
                    final = base+e
                    break
        
        if not final or not os.path.exists(final):
            if status: await status.edit("❌ Fallo en descarga. El enlace puede estar protegido.")
            return
        
        # if os.path.getsize(final) > LIMIT_2GB:
        #     os.remove(final)
        #     if status: await status.edit("❌ Archivo > 2GB.")
        #     return

        if status: await status.edit("📝 **Obteniendo Metadatos...**")
        
        w, h, dur = 0, 0, 0
        
        if calidad != "mp3":
            thumb = await get_thumb(final, chat_id, ts)
            w, h, dur = await get_meta(final)
        else:
            dur = await get_audio_dur(final)

        cap = ""
        if conf['meta']:
            t = datos.get('titulo','Video')
            if conf['lang'] == 'es': t = await traducir_texto(t)
            tags = [f"#{x.replace(' ','_')}" for x in (datos.get('tags') or [])[:10]]
            res_str = f"{w}x{h}" if w else "Audio"
            cap = f"🎬 **{t}**\n⚙️ {res_str} | ⏱ {time.strftime('%H:%M:%S', time.gmtime(dur))}\n{' '.join(tags)}"[:1024]

        if status: await status.edit("📤 **Subiendo...**")
        act = enums.ChatAction.UPLOAD_AUDIO if calidad == "mp3" else enums.ChatAction.UPLOAD_VIDEO
        
        res = None
        if calidad == "mp3":
            res = await client.send_audio(chat_id, final, caption=cap, duration=dur, thumb=thumb, progress=progreso, progress_args=(status, [time.time(),0], act))
        else:
            res = await client.send_video(chat_id, final, caption=cap, width=w, height=h, duration=dur, thumb=thumb, progress=progreso, progress_args=(status, [time.time(),0], act))

        if res and vid_id and not calidad.startswith("html_"):
            if vid_id not in downloads_db: downloads_db[vid_id] = {}
            downloads_db[vid_id][ckey] = (res.audio or res.video).file_id
            guardar_db()

    except Exception as e:
        if status: await status.edit(f"❌ Error: {e}")
    finally:
        # Limpieza segura
        for f in [final, thumb, f"dl_{chat_id}_{ts}.jpg"]:
            if f and os.path.exists(f):
                try: os.remove(f)
                except: pass
        if status:
            try: await status.delete()
            except: pass

# --- MENÚS ---

def gen_kb(conf):
    c_html = "🟢" if conf['html_mode'] else "🔴"
    c_meta = "🟢" if conf['meta'] else "🔴"
    return InlineKeyboardMarkup([
        # [InlineKeyboardButton(f"🕵️ Sniffer (HTML): {c_html}", callback_data="toggle|html")], # Removed by user request
        [InlineKeyboardButton(f"📝 Metadatos: {c_meta}", callback_data="toggle|meta")],
        [InlineKeyboardButton(f"⚙️ Auto: {conf['q_auto'] or 'Off'}", callback_data="menu|auto"),
         InlineKeyboardButton(f"📌 Fija: {conf['q_fixed'] or 'Off'}p", callback_data="menu|fixed")],
        [InlineKeyboardButton(f"🌎 Lang: {conf['lang'].upper()}", callback_data="toggle|lang"),
         InlineKeyboardButton(f"🎵 Fmt: {conf['fmt'].upper()}", callback_data="toggle|fmt")]
    ])

@app.on_callback_query()
async def cb(c, q):
    data = q.data
    msg = q.message
    cid = msg.chat.id
    conf = get_config(cid)

    if data == "cancel": 
        await msg.delete()
        return

    if data.startswith("dl|"):
        d_storage = url_storage.get(cid)
        if not d_storage: return await q.answer("⚠️ Expirado", show_alert=True)
        
        url_target = d_storage['url']
        await msg.delete()
        # Pasamos el control a la descarga
        # Pasamos el control a la descarga (Concurrency Fix)
        asyncio.create_task(procesar_descarga(c, cid, url_target, data.split("|")[1], d_storage, msg))
        return

    if data == "toggle|html": conf['html_mode'] = not conf['html_mode']
    elif data == "toggle|meta": conf['meta'] = not conf['meta']
    elif data == "toggle|lang": conf['lang'] = 'es' if conf['lang'] == 'orig' else 'orig'
    elif data == "toggle|fmt": conf['fmt'] = 'mp3' if conf['fmt'] == 'mp4' else 'mp4'
    
    elif data == "menu|auto":
        return await msg.edit_text("🤖 **Auto**", reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Best", callback_data="set_auto|max")],
            [InlineKeyboardButton("Worst", callback_data="set_auto|min")],
            [InlineKeyboardButton("Off", callback_data="set_auto|off")],
            [InlineKeyboardButton("Back", callback_data="menu|main")]
        ]))
    
    elif data == "menu|fixed":
        return await msg.edit_text("📌 **Fixed**", reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("1080p", callback_data="set_q|1080"), InlineKeyboardButton("720p", callback_data="set_q|720")],
            [InlineKeyboardButton("480p", callback_data="set_q|480"), InlineKeyboardButton("360p", callback_data="set_q|360")],
            [InlineKeyboardButton("Off", callback_data="set_q|off"), InlineKeyboardButton("Back", callback_data="menu|main")]
        ]))

    elif "set_auto" in data:
        v = data.split("|")[1]
        conf['q_auto'] = None if v == "off" else v
        if v != "off": conf['q_fixed'] = None
    
    elif "set_q" in data:
        v = data.split("|")[1]
        conf['q_fixed'] = None if v == "off" else v
        if v != "off": conf['q_auto'] = None

    elif data == "menu|main": pass

    await msg.edit_text("⚙️ **Panel**", reply_markup=gen_kb(conf))

@app.on_message(filters.command("start"))
async def start(c, m):
    await m.reply_text("⚙️ **Configuración Bot Pro**", reply_markup=gen_kb(get_config(m.chat.id)))

@app.on_message(filters.command("menu"))
async def menu_help(c, m):
    help_text = (
        "📖 **Guía de Botones del Bot**\n\n"
        "Aquí tienes una explicación de cada función del panel:\n\n"
        "📝 **Metadatos (On/Off)**\n"
        "• 🟢 **Activo:** Añade Título, Resolución ⚙️, Duración ⏱ y Tags #️⃣ al video.\n"
        "• 🔴 **Inactivo:** Envía el video sin descripción extra.\n\n"
        "⚙️ **Auto (Best/Worst/Off)**\n"
        "• **Best:** Descarga automática la MEJOR calidad.\n"
        "• **Worst:** Descarga automática la calidad más LIGERA.\n"
        "• **Off:** Pregunta siempre qué calidad descargar.\n\n"
        "📌 **Fija (1080p, 720p...)**\n"
        "• Intenta forzar una resolución específica si existe.\n\n"
        "🌎 **Lang (ORIG/ES)**\n"
        "• **ES:** Traduce el título al Español 🇪🇸.\n"
        "• **ORIG:** Mantiene el título original.\n\n"
        "🎵 **Fmt (MP4/MP3)**\n"
        "• Prioridad de formato para descargas automáticas."
    )
    await m.reply_text(help_text)

# --- ANALIZADOR PRINCIPAL (ACTUALIZADO DIMENSIONES) ---

@app.on_message(filters.text & (filters.regex("http") | filters.regex("www")))
async def analyze(c, m):
    cid = m.chat.id
    url = limpiar_url(m.text.strip())
    conf = get_config(cid)
    
    wait_msg = await m.reply("🔎 **Analizando...**")
    btns = []
    html_links_data = []
    
    # Variables para control
    yt_dlp_error = None
    info = {}

    # 1. MODO PLAYWRIGHT SNIFFER (ELIMINADO)
    pass

    # 2. MODO YT-DLP
    try:
        opts = {'quiet':True, 'noplaylist':True, 'http_headers':{'User-Agent':'Mozilla/5.0'}}
        if "eporner" in url: opts['nocheckcertificate']=True
        
        info = await asyncio.get_running_loop().run_in_executor(None, lambda: yt_dlp.YoutubeDL(opts).extract_info(url, download=False))
        if 'entries' in info: info = info['entries'][0]
        
        formats = info.get('formats', [])
        # Agrupar formatos por resolución exacta (WxH)
        unique_formats = {}
        
        for f in formats:
            w = f.get('width')
            h = f.get('height')
            if not h or not w: continue
            
            res_key = f"{w}x{h}"
            sz = f.get('filesize') or f.get('filesize_approx') or 0
            
            # Nos quedamos con el formato de mayor peso para esa resolución (mejor bitrate)
            if res_key not in unique_formats or sz > unique_formats[res_key]['size']:
                unique_formats[res_key] = {'size': sz, 'h': h}
        
        # Ordenar por altura (height) de mayor a menor
        sorted_fmts = sorted(unique_formats.items(), key=lambda x: x[1]['h'], reverse=True)

        # Crear botones con Dimensiones Reales (Feature pedida)
        for res_key, data in sorted_fmts[:8]:
            sz_str = format_bytes(data['size'])
            icon = "🌟" if data['h'] >= 1080 else "📹"
            # res_key ya es "1920x1080"
            btns.append([InlineKeyboardButton(f"{icon} {res_key} • {sz_str}", callback_data=f"dl|{data['h']}")])

        btns.append([InlineKeyboardButton("🎵 MP3 Audio", callback_data="dl|mp3")])

    except Exception as e:
        yt_dlp_error = str(e)
        print(f"YT-DLP Error: {e}")

    btns.append([InlineKeyboardButton("❌ Cancelar", callback_data="cancel")])
    
    # Guardar datos
    url_storage[cid] = {
        'url': url, 
        'id': info.get('id') if info else None, 
        'titulo': info.get('title', 'Video Detectado'),
        'tags': info.get('tags', []),
        'html_links_data': html_links_data 
    }

    if not html_links_data and not info:
        await wait_msg.edit(f"❌ No se encontraron videos.\nError YT-DLP: {str(yt_dlp_error)[:50]}...")
        return

    await wait_msg.delete()
    tit = str(info.get('title', 'Resultado Multimedia'))[:50]
    
    texto_msg = f"🎬 **{tit}**"
    if html_links_data:
        texto_msg += "\n\n🕵️ **Enlaces Directos (Anti-Bloqueo):**"
        # Mostramos los primeros 2 enlaces directos para que el usuario pueda usarlos si falla el bot
        for d in html_links_data[:2]:
            texto_msg += f"\n🔗 [Enlace Directo]({d['url']})"
            
    texto_msg += "\n👇 **Selecciona Calidad:**"
    
    await m.reply(texto_msg, reply_markup=InlineKeyboardMarkup(btns), disable_web_page_preview=True)

if __name__ == "__main__":
    app.run()