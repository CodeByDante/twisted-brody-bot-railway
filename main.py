
import asyncio
import yt_dlp
import time
import re
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto, InputMediaDocument, InputMediaVideo, WebAppInfo, MenuButtonWebApp
from config import API_ID, API_HASH, BOT_TOKEN, DATA_DIR, COOKIE_MAP
from database import get_config, url_storage, hashtag_db, can_download, cancel_all, add_active, remove_active
from utils import format_bytes, limpiar_url, sel_cookie, resolver_url_facebook, descargar_galeria, scan_channel_history
import shutil
import os # Asegurar os
from io import BytesIO
import aiohttp # Para descargar cover manual
# Extractor JAV (Requests + Base64)
from jav_extractor import extraer_jav_directo
# Sniffer Manual (Playwright - Solo si se activa botón)
# from sniffer import detectar_video_real # Eliminado 
from downloader import procesar_descarga
from manga_service import get_manga_metadata, process_manga_download, get_manga_chapters

print("🚀 Iniciando Bot Pro (JAV Turbo + FB Fix + Auto-Swap)...")

SESSION_PATH = os.path.join(DATA_DIR, "mi_bot_pro")
app = Client(SESSION_PATH, api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, workers=100)
BOT_USERNAME = None
print(f"🍪 Checking cookies dir: {os.listdir(os.path.join(DATA_DIR, '../cookies')) if os.path.exists(os.path.join(DATA_DIR, '../cookies')) else 'Missing cookies dir'}")

# --- MENÚ PRINCIPAL ---
def gen_kb(conf):
    # --- MODO PARTY (Exclusivo) ---
    if conf.get('party_mode'):
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Atrás (Salir Modo Party)", callback_data="menu|party_off")]
        ])





    c_html = "🟢" if conf['html_mode'] else "🔴"
    c_meta = "🟢" if conf['meta'] else "🔴"
    lang_flag = "🇪🇸" if conf.get('lang', 'es') == 'es' else "🇺🇸"
    
    txt_auto = "Desact."
    if conf['q_auto'] == 'max': txt_auto = "Máx"
    elif conf['q_auto'] == 'min': txt_auto = "Mín"
    
    fmt_icon = "🎵 MP3" if conf['fmt'] == 'mp3' else "📹 MP4"
    aria_icon = "🟢" if conf.get('fast_enabled', True) else "🔴"
    doc_icon = "🟢" if conf.get('doc_mode', False) else "🔴"
    group_icon = "🟢" if conf.get('group_mode', True) else "🔴"

    kb = [
        [# InlineKeyboardButton(f"🕵️ Sniffer (HTML): {c_html}", callback_data="toggle|html"), 
         InlineKeyboardButton(f"📝 Metadatos: {c_meta}", callback_data="toggle|meta")],
        
        [InlineKeyboardButton(f"🚀 Turbo: {aria_icon}", callback_data="toggle|fast"),
         InlineKeyboardButton(f"📄 Doc: {doc_icon}", callback_data="toggle|doc")],
        [InlineKeyboardButton(f"📚 Agrup: {group_icon}", callback_data="toggle|group")],

        # [InlineKeyboardButton(f"🔄 Comandos Replay: {replay_icon}", callback_data="toggle|replay")], # Eliminado
    ]
    
    # Botón condicional Agregado (Si aplica, pero replay_enabled ya no se usa, lo quitamos de config?)
    # Mejor quitar todo rastro de replay visual.

    kb.extend([
        [InlineKeyboardButton(f"⚙️ Auto: {txt_auto}", callback_data="menu|auto")],
        [InlineKeyboardButton(f"🌐 Idioma: {lang_flag}", callback_data="toggle|lang")],
        
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
        
        # Pasamos estado de fast
        d_storage['fast_enabled'] = conf.get('fast_enabled', True)
        
        asyncio.create_task(procesar_descarga(c, cid, url_target, data.split("|")[1], d_storage, msg))
        return

    if data == "toggle|html": conf['html_mode'] = not conf['html_mode']
    elif data == "toggle|meta": conf['meta'] = not conf['meta']
    elif data == "toggle|fast": conf['fast_enabled'] = not conf.get('fast_enabled', True)
    elif data == "toggle|doc": conf['doc_mode'] = not conf.get('doc_mode', False)
    elif data == "toggle|group": conf['group_mode'] = not conf.get('group_mode', True)
    # elif data == "toggle|replay": conf['replay_enabled'] = not conf.get('replay_enabled', False) # Eliminado
    elif data == "toggle|lang": conf['lang'] = 'es' if conf.get('lang', 'es') == 'orig' else 'orig'
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

    # --- HANDLERS MODO PARTY ---
    elif data == "menu|party_on":
        conf['party_mode'] = True
        await msg.edit_text("✂️ **Modo Party Activo**\n\nEnvía un video (archivo) y te preguntaré en cuántas partes cortarlo.", reply_markup=gen_kb(conf))
        return

    elif data == "menu|party_off":
        conf['party_mode'] = False
        await msg.edit_text("⚙️ **Panel de Configuración**", reply_markup=gen_kb(conf))
        return

    # --- SELECCION PARTY ---
    elif "party_sel" in data:
        mode = data.split("|")[1]
        cid = msg.chat.id
        
        # Actualizar estado
        if cid in url_storage:
             url_storage[cid]['party_step'] = 'wait_value'
             url_storage[cid]['mode'] = mode
             
        txt_map = {
            'parts': "🧩 **¿En cuántas partes?**\nEnvía el número (ej: 2, 3...)",
            'min': "⏱ **¿Cada cuántos MINUTOS?**\nEnvía los minutos (ej: 10, 30...)",
            'sec': "⏱ **¿Cada cuántos SEGUNDOS?**\nEnvía los segundos (ej: 30, 90...)",
            'range': "✂️ **¿Qué rango cortar?**\nEnvía los tiempos Inicio y Fin.\n\nEjemplos:\n• `10 - 20` (segundos 10 a 20)\n• `01:00 - 01:30` (Minuto 1 a 1:30)\n• `10:00 a 10:30`"
        }
        await msg.edit_text(txt_map.get(mode, "Error."))
        return
    # ---------------------------




        



    # --- MENÚ MANGA FLOW ---
    elif "manga_sel" in data:
        # data format: manga_sel|CONTAINER|QUALITY (ej: manga_sel|zip|webp)
        # o manga_sel|CONTAINER (ej: manga_sel|zip) -> Muestra submenu calidad
        
        parts = data.split("|")
        
        cid = msg.chat.id
        st = url_storage.get(cid)
        if not st or 'manga_data' not in st:
            return await q.answer("⚠️ La sesión expiró. Reenvía el link.", show_alert=True)
        manga_data = st['manga_data']

        # CASO 1: Selección de Contenedor (ZIP o PDF)
        if len(parts) == 2:
            container = parts[1] # zip o pdf
            
            # Generar Submenú de Calidades
            import copy
            kb_quality = InlineKeyboardMarkup([
                [InlineKeyboardButton("💎 Original", callback_data=f"manga_sel|{container}|original")],
                [InlineKeyboardButton("⚡ WebP (Optimizado)", callback_data=f"manga_sel|{container}|webp")],
                [InlineKeyboardButton("🖼 PNG", callback_data=f"manga_sel|{container}|png"),
                 InlineKeyboardButton("📸 JPG", callback_data=f"manga_sel|{container}|jpg")],
                [InlineKeyboardButton("🔙 Atrás", callback_data="manga_back")]
            ])
            
            icon = "📦"
            txt_cont = "ZIP"
            if container == "pdf":
                icon = "📄"
                txt_cont = "PDF"
            elif container == "img":
                icon = "🖼"
                txt_cont = "Imágenes"
            
            await msg.edit_text(
                f"{icon} **Selecciona Calidad para {txt_cont}:**\n\n"
                f"📌 **{manga_data['title']}**",
                reply_markup=kb_quality
            )
            return

        # CASO 2: Selección Final (Contenedor + Calidad)
        elif len(parts) == 3:
            container = parts[1]
            fmt = parts[2]
            
            # Ack callback
            await q.answer(f"Descargando {container.upper()} ({fmt})...")
            await msg.delete()
            
            status_msg = await c.send_message(cid, f"⏳ **Iniciando descarga {container.upper()} [{fmt.upper()}]...**")
            
            # Ejecutar en background task
            # Pasamos container y fmt a la función
            task = asyncio.create_task(process_manga_download(
                c, cid, manga_data, container, fmt, status_msg, 
                doc_mode=conf.get('doc_mode', False),
                group_mode=conf.get('group_mode', True)
            ))
            add_active(cid, status_msg.id, task)
            task.add_done_callback(lambda t: remove_active(cid, status_msg.id))
            return
    
    elif data == "manga_back":
        cid = msg.chat.id
        st = url_storage.get(cid)
        if not st or 'manga_data' not in st:
             return await msg.delete() # Expiró

        meta = st['manga_data']
        # Restaurar Menú Principal
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📦 Descargar ZIP", callback_data="manga_sel|zip"),
             InlineKeyboardButton("📄 Descargar PDF", callback_data="manga_sel|pdf")],
            [InlineKeyboardButton("🖼 Ver Imágenes", callback_data="manga_sel|img")],
            [InlineKeyboardButton("🔙 Cancelar", callback_data="cancel")]
        ])
        
        txt = (f"📚 **Manga Encontrado**\n\n"
               f"📌 **Título:** {meta['title']}\n"
               f"👤 **Autor:** {meta['author']}\n\n"
               f"Elige el tipo de archivo:")
        
        # Intentar editar con la foto si es posible, o crear nuevo mensaje si necesitamos foto
        # Al editar mensaje con foto, usamos InputMediaPhoto si ya tenía foto.
        # Simplificación: Editamos solo texto/markup. La foto se queda.
        try:
            await msg.edit_caption(caption=txt, reply_markup=kb)
        except:
             # Si no tenía caption (era texto puro), editamos texto
             await msg.edit_text(txt, reply_markup=kb)
        return

    elif data == "menu|main": pass
    elif data == "start": pass # Para el botón de volver del start

    elif data == "menu|main": pass
    elif data == "start": pass # Para el botón de volver del start

    # --- CATALOGO MANGA HANDLERS ---
    elif data.startswith("catalog|"):
        from manga_service import get_all_mangas_paginated, get_manga_metadata
        
        mode = data.split("|")[1]
        
        if mode == "home" or mode == "nav":
            # catalog|nav|PAGE_INDEX
            page = 0
            if mode == "nav": page = int(data.split("|")[2])
            
            # Obtener lista (Cachear esto en memoria sería ideal, pero por ahora directo)
            # Como es paginado visual, traemos todo y mostramos 1.
            # OPTIMIZACIÓN: Guardar lista en url_storage para no pedir a Firebase en cada click
            
            st = url_storage.get(cid)
            mangas = []
            if st and 'catalog_list' in st:
                mangas = st['catalog_list']
            else:
                await q.answer("🔄 Cargando catálogo...", show_alert=False)
                mangas = await get_all_mangas_paginated()
                if not mangas:
                     return await q.answer("⚠️ Catálogo vacío o error de conexión.", show_alert=True)
                # Save to session (expire after X time? For now keep it simple)
                if not st: url_storage[cid] = {}
                url_storage[cid]['catalog_list'] = mangas
            
            # Validar índice
            if page < 0: page = len(mangas) - 1
            if page >= len(mangas): page = 0
            
            current = mangas[page]
            
            # Botonera
            # [ ⬅️ ] [ 1/50 ] [ ➡️ ]
            # [ 📥 VER MANGA ]
            # [ 🔍 Buscar ] [ 🔙 Salir ]
            
            kb = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("⬅️", callback_data=f"catalog|nav|{page-1}"),
                    InlineKeyboardButton(f"{page+1} / {len(mangas)}", callback_data="ignore"),
                    InlineKeyboardButton("➡️", callback_data=f"catalog|nav|{page+1}")
                ],
                [InlineKeyboardButton("📥 VER MANGA", callback_data=f"catalog|sel|{current['id']}")],
                [InlineKeyboardButton("🔍 Buscar", callback_data="catalog|search"),
                 InlineKeyboardButton("🔙 Salir", callback_data="menu|main")]
            ])
            
            txt = (f"📚 **Twisted Brody Manga Flow**\n\n"
                   f"📌 **{current['title']}**\n"
                   f"👤 {current['author']}")
            
            # Intentar mostrar portada
            cover_url = current.get('cover')
            if cover_url and cover_url.startswith("http"):
                 try:
                     # Si el mensaje actual YA tiene foto, editamos la media
                     # Si no, borramos y enviamos nuevo (más seguro visualmente)
                     # Para "navegación fluida", idealmente usamos InputMediaPhoto
                     media = InputMediaPhoto(cover_url, caption=txt)
                     
                     try:
                         await msg.edit_media(media, reply_markup=kb)
                     except:
                         # Si falla (ej. mensaje texto), borrar y enviar
                         await msg.delete()
                         await c.send_photo(cid, cover_url, caption=txt, reply_markup=kb)
                 except Exception as e:
                     # Fallback texto
                     await msg.edit_text(txt, reply_markup=kb)
            else:
                await msg.edit_text(txt, reply_markup=kb)
            return

        elif mode == "sel":
            mid = data.split("|")[2]
            # Recuperar metadata full (si hace falta) o usar la lista
            # Reutilizamos el flujo de "manga_sel"
            # Necesitamos poner 'manga_data' en storage
            
            st = url_storage.get(cid)
            mangas = st.get('catalog_list', [])
            target = next((m for m in mangas if m['id'] == mid), None)
            
            if not target: return await q.answer("⚠️ Error seleccionando.", show_alert=True)
            
            url_storage[cid]['manga_data'] = target
            
            # Disparar menú de descarga (reutilizando lógica existente)
            # Llamamos al handler de "manga_back" para mostrar el menú inicial de opciones
            # Hack: Modificamos callback data y relanzamos? O replicamos código?
            # Replicamos código limpio:
            
            kb_dl = InlineKeyboardMarkup([
                [InlineKeyboardButton("📦 Descargar ZIP", callback_data="manga_sel|zip"),
                 InlineKeyboardButton("📄 Descargar PDF", callback_data="manga_sel|pdf")],
                [InlineKeyboardButton("🖼 Ver Imágenes", callback_data="manga_sel|img")],
                [InlineKeyboardButton("🔙 Volver al Catálogo", callback_data=f"catalog|home")]
            ])
            
            txt_dl = (f"📚 **{target['title']}**\n"
                     f"👤 {target['author']}\n\n"
                     f"⬇️ **Selecciona formato:**")
            
            await msg.edit_caption(txt_dl, reply_markup=kb_dl)
            return

    # --- HANDLER SYNC SETUP BUTTON REMOVED ---
    elif data == "setup_dump":
        return await q.answer("❌ Función desactivada.", show_alert=True)

    await msg.edit_text("⚙️ **Panel de Configuración**", reply_markup=gen_kb(conf))

@app.on_message(filters.command("start"))
async def start(c, m):
    try:
        from pyrogram.types import MenuButtonDefault
        await c.set_chat_menu_button(
            chat_id=m.chat.id,
            menu_button=MenuButtonDefault()
        )
    except Exception as e:
        print(f"⚠️ Error setting menu button: {e}")
    
    await m.reply_text("⚙️ **Configuración Bot Pro**", reply_markup=gen_kb(get_config(m.chat.id)))

# --- SYNC MASTER COMMAND REMOVED ---
# --- EXPLICIT SETUP COMMAND REMOVED ---
# --- RECOVER COMMAND REMOVED ---
# --- SETUP FORWARD LISTENER REMOVED ---

@app.on_message(filters.command("menu"))
async def menu_help(c, m):
    help_text = (
        "📖 **Guía de Botones del Bot**\n\n"
        "Aquí tienes una explicación de cada función del panel:\n\n"
        "📝 **Metadatos (On/Off)**\n"
        "• 🟢 **Activo:** Añade Título, Resolución ⚙️, Duración ⏱ y Tags #️⃣ al video.\n"
        "• 🔴 **Inactivo:** Envía el video sin descripción extra.\n\n"
        "🚀 **Fast (Ultra Velocidad)**\n"
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

# Scan command removed

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



# --- MANGA MINI APP HANDLER ---
@app.on_message(filters.service & filters.create(lambda _, __, m: m.web_app_data is not None))
async def web_app_data_handler(c, m):
    print(f"📦 Recibido WebAppData: {m.web_app_data.data}")
    from manga_service import handle_comic_request
    await handle_comic_request(c, m, m.web_app_data.data)

# --- PARTY MODE HANDLERS ---
@app.on_message(filters.video | filters.document)
async def party_video_handler(c, m):
    cid = m.chat.id
    conf = get_config(cid)
    
    if not conf.get('party_mode'):
        m.continue_propagation()
        return

    # Si es documento, filtrar por video pero ser flexible
    if m.document and m.document.mime_type and not m.document.mime_type.startswith("video"):
         m.continue_propagation()
         return 

    wait = await m.reply("⬇️ **Descargando video para Party Mode...**", quote=True)
    temp_dir = os.path.join(DATA_DIR, f"party_{cid}")
    if not os.path.exists(temp_dir): os.makedirs(temp_dir, exist_ok=True)
    
    fpath = await c.download_media(m, file_name=os.path.join(temp_dir, "input.mp4"))
    await wait.delete()
    
    if not fpath:
        await m.reply("❌ Error descargando.")
        return

    url_storage[cid] = {'party_step': 'wait_mode', 'file': fpath}
    
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("⏱ Minutos", callback_data="party_sel|min"),
         InlineKeyboardButton("⏱ Segundos", callback_data="party_sel|sec")],
        [InlineKeyboardButton("🧩 Partes", callback_data="party_sel|parts")],
        [InlineKeyboardButton("✂️ Rango (Manual)", callback_data="party_sel|range")],
        [InlineKeyboardButton("🔙 Cancelar", callback_data="menu|party_off")]
    ])
    
    await m.reply("✂️ **Modo Party: ¿Cómo quieres cortar?**", quote=True, reply_markup=kb)



@app.on_message(filters.text & ~filters.regex(r"^/"))
async def party_text_handler(c, m):
    cid = m.chat.id
    conf = get_config(cid)
    
    if not conf.get('party_mode'):
        m.continue_propagation()
        return

    st = url_storage.get(cid)
    if not st or st.get('party_step') != 'wait_value':
        m.continue_propagation()
        return

    mode = st.get('mode', 'parts')
    
    try:
        # Lógica especial para RANGE
        if mode == 'range':
            # Parser simple: busca dos grupos de tiempos
            # Separadores comunes: "-", " a ", " to "
            import re
            txt = m.text.lower().replace(" a ", "-").replace(" to ", "-").strip()
            # Split
            parts_txt = txt.split("-")
            if len(parts_txt) != 2: raise ValueError("Formato inválido")
            
            start_t = parts_txt[0].strip()
            end_t = parts_txt[1].strip()
            
            # Simple check
            if not start_t or not end_t: raise ValueError("Tiempos vacíos")
            
            val = (start_t, end_t) # Guardamos tupla
            
        else:
            val = float(m.text.strip())
            if val <= 0: raise ValueError
            if mode == 'parts': val = int(val)
    except:
        await m.reply(f"❌ **Formato Incorrecto**\nPara {mode} revisa el ejemplo.")
        return

    from utils import split_video_generic, get_video_metadata, format_bytes
    fpath = st['file']
    w_orig, h_orig = get_video_metadata(fpath)
    
    # Estimación básica
    msg_txt = f"✂️ **Procesando corte ({mode}={val})...**"
    if mode == 'parts':
         total_size = os.path.getsize(fpath)
         est = format_bytes(total_size / val)
         msg_txt += f"\n⚖️ **Peso estimado:** ~{est} c/u"
    
    await m.reply(msg_txt)
    
    # BRANCH LÓGICA
    if mode == 'range':
        from utils import cut_video_range
        start_t, end_t = val
        cut_path = await asyncio.get_running_loop().run_in_executor(None, lambda: cut_video_range(fpath, start_t, end_t))
        
        parts = [cut_path] if cut_path else []
    else:
        parts = await asyncio.get_running_loop().run_in_executor(None, lambda: split_video_generic(fpath, mode, val))
    
    if parts:
        await m.reply(f"✅ **Generadas {len(parts)} partes.** Subiendo...")
        for p in parts:
            await c.send_video(cid, p, width=w_orig, height=h_orig)
            try: os.remove(p)
            except: pass
    else:
        await m.reply("❌ Error al cortar. (Verifica duración/formato)")
        
    try: os.remove(fpath)
    except: pass
    url_storage.pop(cid, None)

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
    
    wait_msg = await m.reply("⬇️ **Descargando...**", quote=True)
    
    # 1. FIX FACEBOOK
    if "facebook.com" in url or "fb.watch" in url:
        await wait_msg.edit("🔄 **Normalizando enlace de Facebook...**")
        url = await resolver_url_facebook(url)

    conf = get_config(cid)
    btns = []
    html_links_data = [] 
    info = {}
    yt_dlp_error = None

    # --- MANGA FLOW DETECTOR ---
    if "twisted-brody-manga-flow.vercel.app" in url:
        if "#manga/" not in url:
            return await wait_msg.edit("⚠️ Link de Manga Flow inválido (Falta #manga/ID).")
            
        manga_id = url.split("#manga/")[1].split("?")[0].strip()
        await wait_msg.edit("🔍 **Buscando Manga en Firebase...**")
        
        meta = await get_manga_metadata(manga_id)
        
        if not meta:
            return await wait_msg.edit("❌ No se encontró el manga (Error API o ID inválido).")
            
        # Guardar en Storage para el callback
        url_storage[cid] = {'manga_data': meta}
        
        # Borrar mensaje de espera
        await wait_msg.delete()

        # --- AUTO MODE CHECK ---
        # Si Auto = Max, descargamos ZIP Original directo
        if conf.get('q_auto') == 'max':
             status_msg = await c.send_message(cid, f"⚙️ **Auto-Max detectado:** Iniciando descarga ZIP Original...")
             # Start download directly
             task = asyncio.create_task(process_manga_download(
                c, cid, meta, 'zip', 'original', status_msg, 
                doc_mode=conf.get('doc_mode', False),
                group_mode=conf.get('group_mode', True)
             ))
             add_active(cid, status_msg.id, task)
             task.add_done_callback(lambda t: remove_active(cid, status_msg.id))
             return
        # -----------------------
        
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📦 Descargar ZIP", callback_data="manga_sel|zip"),
             InlineKeyboardButton("📄 Descargar PDF", callback_data="manga_sel|pdf")],
            [InlineKeyboardButton("🖼 Ver Imágenes", callback_data="manga_sel|img")],
            [InlineKeyboardButton("🔙 Cancelar", callback_data="cancel")]
        ])
        
        txt = (f"📚 **Manga Encontrado**\n\n"
               f"📌 **Título:** {meta['title']}\n"
               f"👤 **Autor:** {meta['author']}\n\n"
               f"Elige el tipo de archivo:")
        
        valid_cover = meta.get('cover') and meta['cover'].startswith("http")
        
        # --- SMART COVER FALLBACK ---
        # Si no hay portada explícita, usar la primera página del Cap 1
        if not valid_cover:
             try:
                 chapters = await get_manga_chapters(manga_id)
                 if chapters:
                     first_ch = chapters[0]
                     # Try original then webp
                     if first_ch.get('original'):
                         meta['cover'] = first_ch['original'][0]
                         valid_cover = True
                     elif first_ch.get('webp'):
                         meta['cover'] = first_ch['webp'][0]
                         valid_cover = True
                     
                     # Actualizar storage con la nueva cover
                     url_storage[cid]['manga_data'] = meta
             except: pass

        if valid_cover:
            # FIX: Descargar imagen localmente para evitar WebpageMediaEmpty o errores de URL de Telegram
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(meta['cover']) as resp:
                        if resp.status == 200:
                            photo_bytes = BytesIO(await resp.read())
                            photo_bytes.name = "cover.jpg" # Ayuda a Pyrogram a detectar formato
                            await c.send_photo(cid, photo_bytes, caption=txt, reply_markup=kb)
                        else:
                            # Fallback si falla descarga (403/404)
                             await c.send_message(cid, txt, reply_markup=kb)
            except Exception as e:
                print(f"⚠️ Error enviando cover {meta['cover']}: {e}")
                await c.send_message(cid, txt, reply_markup=kb)
        else:
            await c.send_message(cid, txt, reply_markup=kb)
        return

    # --- FUNCIÓN INTERNAL: FALLBACK GALERÍA ---
    async def process_gallery_fallback():
        is_twitter = "twitter.com" in url or "x.com" in url
        is_facebook = any(d in url for d in ["facebook.com", "m.facebook.com", "fb.com", "fb.watch"])
        is_pinterest = "pinterest" in url or "pin.it" in url
        
        if not (is_twitter or is_facebook or is_pinterest):
            return False

        site_name = "X/Twitter"
        if is_facebook: site_name = "Facebook"
        if is_pinterest: site_name = "Pinterest"
        
        print(f"🐦 Fallback: Detectado {site_name}. Intentando Gallery-DL...")
        # await wait_msg.edit(f"🐦 **No se detectó video.**\n📸 Probando {site_name} (Imágenes)...") # Silenciado a petición del usuario
        
        # Usar rutas absolutas de COOKIE_MAP
        cookie_file = COOKIE_MAP.get('x.com') if is_twitter else (COOKIE_MAP.get('facebook') if is_facebook else None)
        
        g_files, g_tmp = await asyncio.get_running_loop().run_in_executor(
            None, lambda: descargar_galeria(url, cookie_file)
        )
        
        if g_files:
            try:
                # Modificado a petición usuaria: Mensaje directo sin previo aviso de conteo
                txt_status = "⬇️ **Descargando imagen...**" if len(g_files) == 1 else f"⬇️ **Descargando {len(g_files)} imágenes...**"
                await wait_msg.edit(txt_status)
                
                def get_media_item(fpath):
                    is_p_video = fpath.lower().endswith(('.mp4', '.mkv', '.webm', '.mov'))
                    if conf.get('doc_mode'): return InputMediaDocument(fpath)
                    elif is_p_video: return InputMediaVideo(fpath)
                    else: return InputMediaPhoto(fpath)

                if len(g_files) > 1:
                    media_group = [get_media_item(f) for f in g_files[:10]] 
                    await c.send_media_group(cid, media_group, reply_to_message_id=m.id)
                    if len(g_files) > 10: await c.send_message(cid, f"⚠️ Se enviaron los primeros 10 de {len(g_files)} archivos.")
                else:
                    fpath = g_files[0]
                    is_p_video = fpath.lower().endswith(('.mp4', '.mkv', '.webm', '.mov'))
                     
                    cap = ""
                    if conf.get('meta'):
                        if conf.get('doc_mode'): cap = f"📁 {site_name}\n🔗 {url}"
                        elif is_p_video: cap = f"🎬 {site_name}\n🔗 {url}"
                        else: cap = f"📸 {site_name}\n🔗 {url}"

                    if conf.get('doc_mode'): await c.send_document(cid, fpath, caption=cap, reply_to_message_id=m.id)
                    elif is_p_video: await c.send_video(cid, fpath, caption=cap, reply_to_message_id=m.id)
                    else: await c.send_photo(cid, fpath, caption=cap, reply_to_message_id=m.id)

                await wait_msg.delete()
                return True
            except Exception as e:
                print(f"❌ Error Gallery fallback: {e}")
                return False
            finally:
                if g_tmp and os.path.exists(g_tmp):
                    try: shutil.rmtree(g_tmp)
                    except: pass
        return False

    # -----------------------------------------------------------


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
            opts['http_headers'] = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'}

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
                 # 2. Fallback Gallery (Twitter/X Imágenes)
                 if await process_gallery_fallback():
                     return

                 # 3. Fallback: Link Directo
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
                    # Si no es nada de lo anterior, lanzamos el error
                    raise e
        except asyncio.TimeoutError:
            print("❌ Timeout en YT-DLP.")
            await wait_msg.edit("❌ **Error: Tiempo de espera agotado.**\nLa página tarda demasiado en responder.")
            return

        # --- FALLBACK: Si info es None ---
        if info is None:
             if await process_gallery_fallback(): return

             if any(x in url for x in ['.m3u8', '.mp4', 'phncdn', 'surrit']): # Added surrit just in case
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
    # Si esta en modo Auto o si el formato predefinido es MP3
    if info and (conf['q_auto'] or conf.get('fmt') == 'mp3'):
        target_q = None
        
        if conf.get('fmt') == 'mp3':
            target_q = 'mp3'
        elif sorted_fmts:
            if conf['q_auto'] == 'max': target_q = str(sorted_fmts[0][1]['h'])
            elif conf['q_auto'] == 'min': target_q = str(sorted_fmts[-1][1]['h'])
        
        if target_q:
            temp_data = { 
                'url': url, 
                'id': info.get('id'), 
                'titulo': info.get('title'), 
                'tags': [], 
                'html_links_data': html_links_data,
                'fast_enabled': conf.get('fast_enabled', True) # IMPORTANTE: Pasar estado de Fast
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
                # BotCommand("inicio", "🚀 Reiniciar Panel (Alias)"),
                BotCommand("menu", "📖 Guía de Ayuda y Funciones"),
                # BotCommand("scan", "🔄 Escanear Canal (Admin)"),
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