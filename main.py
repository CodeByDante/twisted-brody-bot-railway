
import asyncio
import yt_dlp
import time
import re
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto, InputMediaDocument, InputMediaVideo
from config import API_ID, API_HASH, BOT_TOKEN
from database import get_config, url_storage, hashtag_db, can_download, cancel_all
from utils import format_bytes, limpiar_url, sel_cookie, resolver_url_facebook, descargar_galeria, scan_channel_history
import shutil
import os # Asegurar os
# Extractor JAV (Requests + Base64)
from jav_extractor import extraer_jav_directo
# Sniffer Manual (Playwright - Solo si se activa botón)
# from sniffer import detectar_video_real # Eliminado 
from downloader import procesar_descarga

print("🚀 Iniciando Bot Pro (JAV Turbo + FB Fix + Auto-Swap)...")

app = Client("mi_bot_pro", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, workers=100)
BOT_USERNAME = None

# --- MENÚ PRINCIPAL ---
def gen_kb(conf):
    c_html = "🟢" if conf['html_mode'] else "🔴"
    c_meta = "🟢" if conf['meta'] else "🔴"
    
    txt_auto = "Desact."
    if conf['q_auto'] == 'max': txt_auto = "Máx"
    elif conf['q_auto'] == 'min': txt_auto = "Mín"
    
    lang_icon = "🇪🇸 ES" if conf['lang'] == 'es' else "🇺🇸 Orig"
    fmt_icon = "🎵 MP3" if conf['fmt'] == 'mp3' else "📹 MP4"
    aria_icon = "🟢" if conf.get('aria2_enabled', True) else "🔴"
    doc_icon = "🟢" if conf.get('doc_mode', False) else "🔴"
    replay_icon = "🟢" if conf.get('replay_enabled', False) else "🔴"

    kb = [
        [# InlineKeyboardButton(f"🕵️ Sniffer (HTML): {c_html}", callback_data="toggle|html"), 
         InlineKeyboardButton(f"📝 Metadatos: {c_meta}", callback_data="toggle|meta")],
        
        [InlineKeyboardButton(f"🚀 Aria2: {aria_icon}", callback_data="toggle|aria2"),
         InlineKeyboardButton(f"📄 Doc: {doc_icon}", callback_data="toggle|doc")],

        [InlineKeyboardButton(f"🔄 Comandos Replay: {replay_icon}", callback_data="toggle|replay")],
    ]
    
    # Botón condicional para agregar al canal
    if conf.get('replay_enabled') and BOT_USERNAME:
        kb.append([InlineKeyboardButton("➕ Agregar a Canal", url=f"https://t.me/{BOT_USERNAME}?startchannel&admin=post_messages+edit_messages+delete_messages")])

    kb.extend([
        [InlineKeyboardButton(f"⚙️ Auto: {txt_auto}", callback_data="menu|auto"),
         InlineKeyboardButton(f"🌎 Idioma: {lang_icon}", callback_data="toggle|lang")],
        
        [InlineKeyboardButton(f"📦 Formato: {fmt_icon}", callback_data="toggle|fmt")]
    ])
    
    return InlineKeyboardMarkup(kb)

@app.on_callback_query()
async def cb(c, q):
    data = q.data
    msg = q.message
    cid = msg.chat.id
    conf = get_config(cid)

    if data == "cancel": 
        url_storage.pop(cid, None) # Limpiar RAM
        await msg.delete()
        return

    if data.startswith("dl|"):
        d_storage = url_storage.get(cid)
        if not d_storage: return await q.answer("⚠️ El enlace expiró. Reenvía el link.", show_alert=True)
        
        url_target = d_storage['url']
        await msg.delete()
        
        # Limpiar RAM antes de descargar, ya tenemos los datos en d_storage
        url_storage.pop(cid, None)
        
        # Pasamos estado de aria2
        d_storage['aria2_enabled'] = conf.get('aria2_enabled', True)
        
        asyncio.create_task(procesar_descarga(c, cid, url_target, data.split("|")[1], d_storage, msg))
        return

    if data == "toggle|html": conf['html_mode'] = not conf['html_mode']
    elif data == "toggle|meta": conf['meta'] = not conf['meta']
    elif data == "toggle|aria2": conf['aria2_enabled'] = not conf.get('aria2_enabled', True)
    elif data == "toggle|doc": conf['doc_mode'] = not conf.get('doc_mode', False)
    elif data == "toggle|replay": conf['replay_enabled'] = not conf.get('replay_enabled', False)
    elif data == "toggle|lang": conf['lang'] = 'es' if conf['lang'] == 'orig' else 'orig'
    elif data == "toggle|fmt": conf['fmt'] = 'mp3' if conf['fmt'] == 'mp4' else 'mp4'
    
    elif data == "menu|auto":
        return await msg.edit_text("⚙️ **Auto-Descarga**", reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🌟 Máxima Calidad", callback_data="set_auto|max")],
            [InlineKeyboardButton("📉 Mínimo Peso", callback_data="set_auto|min")],
            [InlineKeyboardButton("🔴 Desactivar", callback_data="set_auto|off")],
            [InlineKeyboardButton("🔙 Volver", callback_data="menu|main")]
        ]))
    
    elif "set_auto" in data:
        v = data.split("|")[1]
        conf['q_auto'] = None if v == "off" else v

    elif data == "menu|main": pass
    elif data == "start": pass # Para el botón de volver del start

    await msg.edit_text("⚙️ **Panel de Configuración**", reply_markup=gen_kb(conf))

@app.on_message(filters.command(["start", "inicio"]))
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
        "🚀 **Aria2 (Ultra Velocidad)**\n"
        "• 🟢 **Activo:** Descarga usando 16 conexiones simultáneas (Turbo).\n"
        "• 🔴 **Inactivo:** Modo estándar (Monohilo de yt-dlp).\n\n"
        "📄 **Modo Documento**\n"
        "• 🟢 **Activo:** Envía el archivo como documento (sin compresión/preview).\n"
        "• 🔴 **Inactivo:** Envía como video (streamable).\n\n"
        "⚡ **Modo Turbo (Automático)**\n"
        "• Se activa solo para enlaces `.m3u8` (Jav/Surrit).\n"
        "• Usa un motor especial optimizado para streams.\n\n"
        "📊 **Monitor de Progreso**\n"
        "• Verás en vivo: Porcentaje %, Velocidad ⚡ y Tiempo Restante ⏳.\n"
        "• Se actualiza cada ~4 segundos.\n\n"
        "⚙️ **Auto (Máx/Mín/Desact.)**\n"
        "• **Máx:** Descarga automática la MEJOR calidad.\n"
        "• **Mín:** Descarga automática la calidad más LIGERA.\n"
        "• **Desact.:** Pregunta siempre qué calidad descargar.\n\n"
        "📌 **Detalles Extra**\n"
        "• **Límite 2GB:** Te avisará si el archivo supera el límite de Telegram.\n"
        "• **(~):** Indica que el peso es estimado porque la web no lo dió.\n\n"
        "🌐 **Páginas Soportadas (Principales):**\n"
        "• 🟧 Pornhub (Premium/Cookies)\n"
        "• ❌ Xvideos, Eporner, RedTube\n"
        "• 📱 TikTok, Instagram, Facebook\n"
        "• 🐦 Twitter/X.com\n"
        "• 🇯🇵 JAV (MissAV, JavGuru, Jable...)\n"
        "• ▶️ YouTube (+Shorts)\n"
        "• ☁️ **Nube:** G-Drive, Mediafire, Dropbox (Públicos)\n"
        "• 🎞️ **Anime:** StreamWish, Voe, YourUpload"
    )
    await m.reply_text(help_text)

@app.on_message(filters.command("scan"))
async def scan_command(c, m):
    msg = await m.reply_text("🔄 **Iniciando escaneo del canal...**\n(Esto puede tardar si hay muchos mensajes)")
    try:
        count = await scan_channel_history(c, m.chat.id)
        await msg.edit(f"✅ **Escaneo completado.**\n\n📌 Mensajes con #Hashtags indexados: **{count}**")
    except Exception as e:
        await msg.edit(f"❌ Error escaneando: {e}")

@app.on_message(filters.command("cancel"))
async def cancel_command(c, m):
    count = await cancel_all(m.chat.id)
    url_storage.pop(m.chat.id, None)
    if count > 0:
        await m.reply(f"🛑 **Se cancelaron {count} descargas activas.**\nCola limpia.")
    else:
        await m.reply("🤷‍♂️ No tienes descargas activas.")

@app.on_message(filters.regex(r"^/(\w+)"))
async def hashtag_replay_handler(c, m):
    tag = m.matches[0].group(1).lower()
    
    # 1. PRIMERO: Ignorar comandos reservados (debe pasar a sus handlers específicos)
    if tag in ['start', 'inicio', 'menu', 'scan', 'help', 'settings', 'dl', 'cancel']:
        return
    
    # 2. Verificar si está habilitado
    cid = m.chat.id
    conf = get_config(cid)
    if not conf.get('replay_enabled'):
        return

    # 3. Buscar en DB
    if tag in hashtag_db:
        items = hashtag_db[tag]
        total = len(items)
        status_msg = await m.reply_text(f"🔄 **Encontrados {total} videos para #{tag}**\nReenviando en lotes...")
        
        # 4. Reenvío por lotes
        batch_size = 100
        
        from collections import defaultdict
        
        # Dividir en chunks de 100
        for i in range(0, total, batch_size):
            batch = items[i:i+batch_size]
            
            # Agrupar este batch por chat_id
            batches_by_chat = defaultdict(list)
            for item in batch:
                batches_by_chat[item['chat']].append(item['id'])
            
            for chat_origin, ids in batches_by_chat.items():
                try:
                    await c.forward_messages(
                        chat_id=cid,
                        from_chat_id=chat_origin,
                        message_ids=ids
                    )
                    await asyncio.sleep(1) # Pequeña pausa entre sub-lotes
                except Exception as e:
                    print(f"❌ Error re-enviando batch: {e}")
            
            await asyncio.sleep(4) # Pausa entre lotes grandes para evitar FloodWait
            
        await status_msg.edit(f"✅ **Reenvío de #{tag} finalizado.**")

@app.on_message(filters.text & (filters.regex("http") | filters.regex("www")))
async def analyze(c, m):
    cid = m.chat.id
    
    # --- ANTI-SPAM CHECK ---
    ok, err = can_download(cid)
    if not ok:
        return await m.reply(err, quote=True)
    # -----------------------

    # Clean previous data to prevent mix-ups
    url_storage.pop(cid, None)
    
    msg_txt = m.text
    # Detectar URL
    url_regex = r"(https?://\S+)"
    match = re.search(url_regex, msg_txt)
    if not match: return
    
    url = limpiar_url(match.group(1))
    
    wait_msg = await m.reply("🔎 **Analizando enlace...**", quote=True)
    
    # 1. FIX FACEBOOK
    if "facebook.com" in url or "fb.watch" in url:
        await wait_msg.edit("🔄 **Normalizando enlace de Facebook...**")
        url = await resolver_url_facebook(url)

    conf = get_config(cid)
    btns = []
    html_links_data = [] 
    info = {}
    yt_dlp_error = None

    # -----------------------------------------------------------
    # 1.5. MODO GALERIA (X/Twitter/Facebook/Pinterest)
    # -----------------------------------------------------------
    is_twitter = "twitter.com" in url or "x.com" in url
    is_facebook = any(d in url for d in ["facebook.com", "m.facebook.com", "fb.com", "fb.watch"])
    is_pinterest = "pinterest" in url or "pin.it" in url

    if is_twitter or is_facebook or is_pinterest:
        site_name = "X/Twitter"
        if is_facebook: site_name = "Facebook"
        if is_pinterest: site_name = "Pinterest"
        
        print(f"🐦 Detectado enlace de {site_name}. Usando Gallery-DL...")
        await wait_msg.edit(f"🐦 **Procesando {site_name} con Gallery-DL...**")
        
        cookie_file = "cookies_x.txt" if is_twitter else ("cookies_facebook.txt" if is_facebook else None)
        
        # Ejecutar en thread aparte para no bloquear
        g_files, g_tmp = await asyncio.get_running_loop().run_in_executor(
            None, lambda: descargar_galeria(url, cookie_file)
        )
        
        if g_files:
            try:
                await wait_msg.edit(f"📸 **Encontrados {len(g_files)} archivos.**\nSubiendo...")
                
                # Función helper para determinar tipo de medio
                def get_media_item(fpath):
                    is_video = fpath.lower().endswith(('.mp4', '.mkv', '.webm', '.mov'))
                    if conf.get('doc_mode'):
                        return InputMediaDocument(fpath)
                    elif is_video:
                         return InputMediaVideo(fpath)
                    else:
                         return InputMediaPhoto(fpath)

                # Crear MediaGroup si hay más de 1, o enviar simple
                if len(g_files) > 1:
                    media_group = [get_media_item(f) for f in g_files[:10]] 
                    await c.send_media_group(cid, media_group, reply_to_message_id=m.id)
                    
                    if len(g_files) > 10:
                        await c.send_message(cid, f"⚠️ Se enviaron los primeros 10 de {len(g_files)} archivos.")
                else:
                    fpath = g_files[0]
                    is_video = fpath.lower().endswith(('.mp4', '.mkv', '.webm', '.mov'))
                    if conf.get('doc_mode'):
                        await c.send_document(cid, fpath, caption=f"📁 Archivo de {site_name}\n🔗 {url}", reply_to_message_id=m.id)
                    elif is_video:
                        await c.send_video(cid, fpath, caption=f"🎬 Video de {site_name}\n🔗 {url}", reply_to_message_id=m.id)
                    else:
                        await c.send_photo(cid, fpath, caption=f"📸 Imagen de {site_name}\n🔗 {url}", reply_to_message_id=m.id)
                
                await wait_msg.delete()
            except Exception as e:
                print(f"❌ Error crítico enviando galería: {e}")
                await wait_msg.edit(f"❌ Error enviando archivos: {e}")
            finally:
                # Limpiar siempre
                if g_tmp and os.path.exists(g_tmp):
                    try: shutil.rmtree(g_tmp)
                    except: pass
            return # TERMINAMOS AQUÍ, no seguir a yt-dlp
        else:
            print(f"⚠️ Gallery-DL no encontró archivos en {site_name}. Intentando descarga estándar...")
            await wait_msg.edit("⚠️ No se encontró galería. Intentando modo video estándar...")

    # -----------------------------------------------------------
    # 2. JAV TURBO (Extracción Directa)
    # -----------------------------------------------------------
    jav_domains = ["javxxx", "jav.guru", "missav", "javdb", "savr-", "jable", "avgle"]
    is_jav = any(d in url.lower() for d in jav_domains)

    if is_jav: # Solo si no tenemos ya algo (ej. twitter img)
        await wait_msg.edit("⚡ **Modo JAV Turbo activado**\n🔓 Buscando video real...")
        try:
            # Ejecutamos el extractor ligero
            html_links_data = await asyncio.get_running_loop().run_in_executor(None, lambda: extraer_jav_directo(url))
            
            if html_links_data:
                best_link = html_links_data[0]['url']
                print(f"✅ JAV Turbo: Enlace encontrado: {best_link}")
                
                # --- TRUCO CRÍTICO ---
                # Si encontramos un enlace directo (.m3u8) o un iframe player,
                # REEMPLAZAMOS la url principal para que YT-DLP analice ESO y no la web original.
                # Esto soluciona el "Unsupported URL" en javxxx.me
                if best_link != url:
                    url = best_link
                    
        except Exception as e:
            print(f"⚠️ JAV Turbo Error: {e}")

    # 3. SNIFFER MANUAL (ELIMINADO)
    pass

    # 4. YT-DLP
    async def extraer(target_url, mode="desktop"):
        # HEMOS ACTIVADO LOGS (quiet: False) PARA VER EL ERROR REAL EN CONSOLA
        opts = {'quiet': False, 'verbose': True, 'ignoreerrors': True, 'noplaylist': True}
        
        # Headers por defecto (Desktop)
        # Headers por defecto (Desktop)
        if mode == "desktop":
            # Forzamos User-Agent de Chrome (Actualizado por usuario)
            opts['http_headers'] = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36'}
            
            c_file = sel_cookie(target_url)
            if c_file: 
                print(f"🍪 Cookies detectadas: {c_file}")
                opts['cookiefile'] = c_file
            else:
                print("⚠️ NO se detectaron cookies para esta URL.")

        # Headers Móvil Legacy (Para mbasic)
        elif mode == "mobile_legacy":
            opts['http_headers'] = {'User-Agent': 'Mozilla/5.0 (Linux; Android 4.4.2; Nexus 4 Build/KOT49H) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/34.0.1847.114 Mobile Safari/537.36'}
        
        # Twitter/X Fix: Usar UA de Desktop para coincidir con las cookies
        if "twitter.com" in target_url or "x.com" in target_url:
            opts['http_headers'] = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}

        if "eporner" in target_url: opts['nocheckcertificate'] = True
        
        # Vimeo Fix: Referer
        if "vimeo.com" in target_url:
             opts['http_headers']['Referer'] = target_url

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, lambda: yt_dlp.YoutubeDL(opts).extract_info(target_url, download=False))

    try:
        try:
            print(f"⏳ Iniciando extracción YT-DLP para: {url}")
            # Intento normal
            info = await asyncio.wait_for(extraer(url, mode="desktop"), timeout=60)
            print("✅ Extracción finalizada con éxito.")
        except Exception as e:
            err_str = str(e)
            # Reintento Facebook mbasic
            if "facebook" in url and ("Cannot parse" in err_str or "cookies" in err_str or "404" in err_str or "Not Found" in err_str):
                mbasic_url = url.replace("www.facebook.com", "mbasic.facebook.com").replace("video.php", "watch")
                if "mbasic" not in mbasic_url: mbasic_url = mbasic_url.replace("https://facebook.com", "https://mbasic.facebook.com")
                
                print(f"⚠️ FB Falló. Usando mbasic: {mbasic_url}")
                await wait_msg.edit("⚠️ **Usando método alternativo...**")
                info = await extraer(mbasic_url, mode="mobile_legacy")
            else:
                 # --- FALLBACK: Link Directo ---
                if any(x in url for x in ['.m3u8', '.mp4', 'phncdn']):
                   print(f"⚠️ Fallback: Error YT-DLP ignorado por ser Link Directo: {e}")
                   ts_fb = int(time.time())
                   info = {
                       'id': f"direct_{ts_fb}",
                       'title': 'Archivo Directo (Fallback)',
                       'url': url,
                       'ext': 'mp4',
                       'formats': [] 
                   }
                   yt_dlp_error = None
                else:
                   raise e
        except asyncio.TimeoutError:
            print("❌ Timeout en YT-DLP.")
            await wait_msg.edit("❌ **Error: Tiempo de espera agotado.**\nLa página tarda demasiado en responder.")
            return

        # --- FALLBACK: Si info es None (ignoreerrors=True) ---
        if info is None and any(x in url for x in ['.m3u8', '.mp4', 'phncdn', 'surrit']): # Added surrit just in case
             print(f"⚠️ Fallback: YT-DLP devolvió None. Usando Modo Directo.")
             ts_fb = int(time.time())
             info = {
                 'id': f"direct_{ts_fb}",
                 'title': 'Archivo Directo (Fallback)',
                 'url': url,
                 'ext': 'mp4',
                 'formats': [] 
             }
        
        if info and 'entries' in info: info = info['entries'][0]
        
        formats = info.get('formats', []) if info else []
        unique_formats = {}
        
        for f in formats:
            w = f.get('width')
            h = f.get('height')
            if not h or not w: continue
            
            res_key = f"{w}x{h}"
            
            # Cálculo de peso forzado
            sz = f.get('filesize') or f.get('filesize_approx') or 0
            if sz == 0:
                tbr = f.get('tbr') or 0
                dur = info.get('duration') or 0
                if tbr > 0 and dur > 0:
                    sz = int((tbr * 1024 * dur) / 8)
            
            if res_key not in unique_formats or sz > unique_formats[res_key]['size']:
                unique_formats[res_key] = {'size': sz, 'h': h, 'w': w}
        
        sorted_fmts = sorted(unique_formats.items(), key=lambda x: x[1]['h'], reverse=True)

        is_direct_hit = False

        # CASO ESPECIAL: Enlace Directo (Ej: .m3u8 único sin lista de formatos)
        if info and not sorted_fmts and info.get('url'):
            is_direct_hit = True
            h = info.get('height') or 720
            w = info.get('width') or 1280
            sz = info.get('filesize') or 0
            
            # Si no hay peso, intentamos estimarlo dinámicamente según resolución
            is_estimated = False
            if sz == 0:
                dur = info.get('duration') or 0
                if dur > 0:
                    is_estimated = True
                    # Bitrate estimado según calidad (KB/s)
                    bitrate = 150 # 480p o menos
                    if h >= 1080: bitrate = 600 # ~5 Mbps
                    elif h >= 720: bitrate = 300 # ~2.5 Mbps
                    
                    sz = int(dur * bitrate * 1024) 

            sz_text = f"~{format_bytes(sz)}" if is_estimated else format_bytes(sz)
            btns.append([InlineKeyboardButton(f"⚡ Directo {w}x{h} ({sz_text})", callback_data=f"dl|{h}")])
            # Forzamos que 'formats' tenga algo para que downloader sepa qué hacer si se usa lógica de auto
            unique_formats[f"{w}x{h}"] = {'size': sz, 'h': h, 'w': w}
            sorted_fmts = [(f"{w}x{h}", {'size': sz, 'h': h, 'w': w})]

        if not is_direct_hit:
            for res_key, data in sorted_fmts[:8]:
                sz = data['size']
                h = data['h']
                w = data['w']
                sz_str = format_bytes(sz)
                
                label = "SD"
                if h >= 2160: label = "4K"
                elif h >= 1440: label = "2K"
                elif h >= 1080: label = "FHD"
                elif h >= 720: label = "HD"
                
                btn_text = f"{w} x {h} ({sz_str}) {label}"
                btns.append([InlineKeyboardButton(btn_text, callback_data=f"dl|{h}")])

        btns.append([InlineKeyboardButton("🎵 Audio MP3", callback_data="dl|mp3")])

    except Exception as e:
        import traceback
        yt_dlp_error = f"{str(e)}\n\n{traceback.format_exc()}"
        print(f"YT-DLP Error Full: {yt_dlp_error}")

    # Agregar botones de JAV Turbo / Sniffer al principio
    if html_links_data:
        for i, data in enumerate(html_links_data):
            size_str = format_bytes(data['size'])
            res_str = data['res']
            icon = "📺" if "m3u8" in data['url'] else "📥"
            btns.insert(0, [InlineKeyboardButton(f"{icon} {res_str} • {size_str}", callback_data=f"dl|html_{i}")])

    btns.append([InlineKeyboardButton("❌ Cancelar", callback_data="cancel")])
    
    # Auto Download
    if info and conf['q_auto']:
        target_q = None
        if sorted_fmts:
            if conf['q_auto'] == 'max': target_q = str(sorted_fmts[0][1]['h'])
            elif conf['q_auto'] == 'min': target_q = str(sorted_fmts[-1][1]['h'])
        
        if target_q:
            temp_data = { 
                'url': url, 
                'id': info.get('id'), 
                'titulo': info.get('title'), 
                'tags': [], 
                'html_links_data': html_links_data,
                'aria2_enabled': conf.get('aria2_enabled', True) # IMPORTANTE: Pasar estado de Aria2
            }
            await wait_msg.delete()
            # Limpiamos antes de auto-descarga
            url_storage.pop(cid, None)
            asyncio.create_task(procesar_descarga(c, cid, url, target_q, temp_data, m))
            return

    # Guardar sesión
    url_storage[cid] = {
        'url': url, 
        'id': info.get('id') if info else None, 
        'titulo': info.get('title', 'Video Detectado') if info else 'Video Detectado',
        'tags': info.get('tags', []) if info else [],
        'html_links_data': html_links_data 
    }

    if not html_links_data and not info:
        await wait_msg.edit(f"❌ **No se encontraron videos.**\n\nError: {str(yt_dlp_error)[:100]}")
        url_storage.pop(cid, None) # Limpiar
        return

    await wait_msg.delete()
    tit = str(info.get('title', 'Resultado Multimedia'))[:50]
    if not info and html_links_data: tit = "Video Encontrado (Extractor)"
    
    texto_msg = f"🎬 **{tit}**"
    if html_links_data: texto_msg += "\n\n⚡ **Enlaces Directos Detectados:**"
    texto_msg += "\n👇 **Selecciona Calidad:**"
    
    await m.reply(texto_msg, reply_markup=InlineKeyboardMarkup(btns), quote=True, disable_web_page_preview=True)

if __name__ == "__main__":
    from pyrogram import idle
    from pyrogram.types import BotCommand

    async def start_bot():
        global BOT_USERNAME
        print("🚀 Iniciando Twisted Brody Bot Pro...")
        await app.start()
        
        # Obtener username del bot para deep links
        try:
            me = await app.get_me()
            BOT_USERNAME = me.username
            print(f"✅ Bot conectado como @{BOT_USERNAME}")
        except Exception as e:
            print(f"⚠️ Error obteniendo info del bot: {e}")
        
        # Registrar comandos en la API de Telegram
        try:
            await app.set_bot_commands([
                BotCommand("start", "⚙️ Configuración y Estado"),
                BotCommand("inicio", "🚀 Reiniciar Panel (Alias)"),
                BotCommand("menu", "📖 Guía de Ayuda y Funciones"),
                BotCommand("scan", "🔄 Escanear Canal (Admin)"),
                BotCommand("cancel", "🛑 Cancelar descargas activas")
            ])
            print("✅ Comandos registrados con éxito.")
        except Exception as e:
            print(f"⚠️ Error al registrar comandos: {e}")

        print("🤖 Bot Corriendo y Esperando mensajes...")
        await idle()
        await app.stop()

    import asyncio
    app.run(start_bot())