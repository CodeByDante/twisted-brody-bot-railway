import aiohttp
import asyncio
import os
import shutil
import json
import zipfile
import img2pdf
from PIL import Image
from io import BytesIO
from config import DATA_DIR
from pyrogram.types import InputMediaPhoto, InputMediaDocument

FIREBASE_BASE_URL = "https://firestore.googleapis.com/v1/projects/twistedbrody-9d163/databases/(default)/documents"

async def get_manga_metadata(manga_id):
    """Obtiene título, autor y portada del manga desde Firebase."""
    url = f"{FIREBASE_BASE_URL}/mangas/{manga_id}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    print(f"❌ Error Metadata ({resp.status}): {await resp.text()}")
                    return None
                data = await resp.json()
                
                fields = data.get('fields', {})
                title = fields.get('title', {}).get('stringValue', 'Desconocido')
                author = fields.get('author', {}).get('stringValue', 'Desconocido')
                # La portada suele estar en 'cover' o 'image'
                cover = fields.get('cover', {}).get('stringValue') or fields.get('image', {}).get('stringValue')
                
                return {
                    'id': manga_id,
                    'title': title,
                    'author': author,
                    'cover': cover
                }
    except Exception as e:
        print(f"❌ Excepción Metadata: {e}")
        return None

async def get_manga_chapters(manga_id):
    """Obtiene los capítulos (imágenes) usando una Query a Firebase."""
    url = f"{FIREBASE_BASE_URL}:runQuery"
    
    # Query Body exacto proporcionado por el usuario
    payload = {
        "structuredQuery": {
            "from": [{ "collectionId": "chapters" }],
            "where": {
                "fieldFilter": {
                    "field": { "fieldPath": "manga_id" },
                    "op": "EQUAL",
                    "value": { "stringValue": manga_id }
                }
            }
        }
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as resp:
                if resp.status != 200:
                    print(f"❌ Error Chapters ({resp.status}): {await resp.text()}")
                    return []
                
                data = await resp.json()
                # data es una lista de documentos wrapper
                
                chapters = []
                for item in data:
                    doc = item.get('document', {})
                    if not doc: continue
                    
                    fields = doc.get('fields', {})
                    
                    # Extraer páginas originales
                    orig_pages = []
                    vals = fields.get('original_pages', {}).get('arrayValue', {}).get('values', [])
                    for v in vals:
                        if 'stringValue' in v: orig_pages.append(v['stringValue'])
                        
                    # Extraer páginas webp
                    webp_pages = []
                    vals = fields.get('pages', {}).get('arrayValue', {}).get('values', [])
                    for v in vals:
                        if 'stringValue' in v: webp_pages.append(v['stringValue'])
                        
                    ch_num = fields.get('number', {}).get('integerValue', '0')
                    ch_title = fields.get('title', {}).get('stringValue', f"Capítulo {ch_num}")
                    
                    chapters.append({
                        'title': ch_title,
                        'number': int(ch_num),
                        'original': orig_pages,
                        'webp': webp_pages
                    })
                
                # Ordenar por número
                chapters.sort(key=lambda x: x['number'])
                return chapters
                
    except Exception as e:
        print(f"❌ Excepción Chapters: {e}")
        return []

    except: pass
    return None

async def get_all_mangas_paginated():
    """Obtiene una lista ligera de TODOS los mangas (Title, ID, Cover) para el catálogo."""
    url = f"{FIREBASE_BASE_URL}:runQuery"
    # Query para traer solo campos necesarios y ordenar (simulado)
    # Firebase REST es limitado, traemos todo y filtramos en RAM (Para ~50 mangas está bien)
    payload = {
        "structuredQuery": {
            "from": [{ "collectionId": "mangas" }],
            "limit": 100 # Safety limit
        }
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as resp:
                if resp.status != 200: return []
                data = await resp.json()
                
                mangas = []
                for item in data:
                    doc = item.get('document', {})
                    if not doc: continue
                    
                    # ID está en name: .../documents/mangas/ID
                    full_name = doc.get('name', '')
                    mid = full_name.split('/')[-1]
                    
                    fields = doc.get('fields', {})
                    title = fields.get('title', {}).get('stringValue', 'Sin Título')
                    author = fields.get('author', {}).get('stringValue', 'Desconocido')
                    cover = fields.get('cover', {}).get('stringValue') or fields.get('image', {}).get('stringValue')
                    
                    mangas.append({
                        'id': mid,
                        'title': title, # Strip para limpieza
                        'author': author,
                        'cover': cover
                    })
                
                # Ordenar alfabéticamente
                mangas.sort(key=lambda x: x['title'])
                return mangas
    except Exception as e:
        print(f"Error Manga Pagination: {e}")
        return []

from database import global_config, save_manga_cache
async def sync_mangas_incremental(client, status_msg):
    """
    Sincronización Pasiva:
    1. Descarga lista de mangas.
    2. Compara con caché local.
    3. Descarga -> Sube al Dump Channel -> Guarda ID.
    """
    dump_id = global_config.get('dump_channel_id')
    if not dump_id:
        await status_msg.edit("⚠️ Error: No hay Canal Privado configurado.")
        return

    mangas = await get_all_mangas_paginated()
    if not mangas:
        await status_msg.edit("⚠️ No se encontraron mangas en Firebase.")
        return

    new_count = 0
    total_processed = 0
    
    for m in mangas:
        mid = m['id']
        # Clave base para IMAGENES DOCUMENTO (El nuevo estándar)
        # container='img', quality='original', doc_mode=True
        cache_key_img = f"{mid}|img|original|True"
        
        # Si YA lo tenemos, skip
        if cache_key_img in manga_cache:
            continue
            
        # Si NO lo tenemos, procedemos
        new_count += 1
        await status_msg.edit(f"🔄 **Sincronizando: {m['title']}**\n(Subiendo Galería de Documentos)...")
        
        try:
            # Reutilizamos la lógica de descarga pero FORZAMOS:
            # - container='img'
            # - quality='original'
            # - doc_mode=True (Para documentos individuales)
            # - group_mode=False (Uno por uno, más seguro para capturar IDs y evitar desorden en dump)
            
            await process_manga_download(
                client, 
                dump_id, # <--- ENVIAR AL CANAL PRIVADO (Proxy target)
                m, 
                'img', 
                'original', 
                status_msg, 
                doc_mode=True, 
                group_mode=False, # Uno a uno para garantizar orden y capture
                is_sync=True # SILENT MODE (No reenviar al usuario admin que ejecutó esto)
            )
            
            # Sleep Anti-Flood IMPORTANTE
            await asyncio.sleep(5)
            
        except Exception as e:
            print(f"Error syncing {mid}: {e}")
            await asyncio.sleep(2)
    
    await status_msg.edit(f"✅ **Sincronización Completada**\nNuevos Mangas procesados: {new_count}")

from database import manga_cache, save_manga_cache
from pyrogram.types import InputMediaPhoto, InputMediaDocument
from pyrogram.errors import FloodWait

async def download_image(session, url, retries=3):
    """Descarga una imagen con retries simples."""
    for i in range(retries):
        try:
            async with session.get(url, timeout=20) as resp:
                if resp.status == 200:
                    return await resp.read()
        except Exception as e:
            # print(f"Retry {i+1} for {url}: {e}")
            await asyncio.sleep(1)
    return None

async def process_manga_download(client, chat_id, manga_data, container, quality, status_msg, doc_mode=False, group_mode=True, is_sync=False):
    """
    Descarga, procesa y envía el manga.
    container: 'zip', 'pdf' o 'img'
    quality: 'original', 'webp', 'png', 'jpg'
    """
    manga_id = manga_data['id']
    title = manga_data['title']
    
    # --- CACHE CHECK ---
    cache_key = f"{manga_id}|{container}|{quality}|{doc_mode}"
    
    # 1. Intento Directo
    if cache_key in manga_cache:
        cached_data = manga_cache[cache_key]
    else:
        # 2. Smart Fallback: Si el usuario pide NORMAL (doc_mode=False) pero tenemos HQ (doc_mode=True)
        #    Usamos el archivo HQ.
        fallback_key = f"{manga_id}|{container}|{quality}|True"
        cached_data = manga_cache.get(fallback_key)
    
    if cached_data:
        found_in_cache = False
        
        try:
            if container in ['zip', 'pdf']:
                # cached_data should be a single file_id string
                if isinstance(cached_data, str):
                    await status_msg.edit(f"🚀 **{title}**\nEnviando desde caché...")
                    cap = f"📚 **{title}**\n👤 {manga_data['author']}\n📦 {container.upper()} | 🎨 {quality.upper()}"
                    await client.send_document(chat_id, cached_data, caption=cap)
                    await status_msg.delete()
                    return
            
            elif container == 'img':
                # cached_data should be a list of file_ids
                if isinstance(cached_data, list) and len(cached_data) > 0:
                    await status_msg.edit(f"🚀 **{title}**\nEnviando {len(cached_data)} imágenes desde caché...")
                    
                    if not group_mode:
                        # ENVIAR 1 a 1 (Cache)
                        for idx, fid in enumerate(cached_data):
                            if idx % 10 == 0:
                                try: await status_msg.edit(f"📤 **Enviando (Cache)...** {idx+1}/{len(cached_data)}")
                                except: pass
                            try:
                                if doc_mode: await client.send_document(chat_id, fid)
                                else: await client.send_photo(chat_id, fid)
                                await asyncio.sleep(0.3)
                            except FloodWait as e:
                                await asyncio.sleep(e.value + 1)
                                if doc_mode: await client.send_document(chat_id, fid)
                                else: await client.send_photo(chat_id, fid)
                            except Exception as e:
                                print(f"Error sending cached img {fid}: {e}")
                    else:
                        # ENVIAR AGRUPADO (Cache)
                        async def send_group_safe_cache(media_group):
                            while True:
                                try:
                                    await client.send_media_group(chat_id, media_group)
                                    return
                                except FloodWait as e:
                                    await asyncio.sleep(e.value + 1)
                                except Exception:
                                    return 

                        if doc_mode:
                            for i in range(0, len(cached_data), 10):
                                chunk = cached_data[i:i+10]
                                media = [InputMediaDocument(fid) for fid in chunk]
                                await send_group_safe_cache(media)
                                await asyncio.sleep(1.2)
                        else:
                            for i in range(0, len(cached_data), 10):
                                chunk = cached_data[i:i+10]
                                media = [InputMediaPhoto(fid) for fid in chunk]
                                try:
                                    await client.send_media_group(chat_id, media)
                                    await asyncio.sleep(1.2)
                                except FloodWait as e:
                                    await asyncio.sleep(e.value + 1)
                                    try: await client.send_media_group(chat_id, media)
                                    except: pass
                                except Exception: pass
                    
                    await status_msg.delete()
                    return

        except Exception as e:
            print(f"❌ Cache hit but failed to send: {e}. Falling back to download.")
            # Si falla el cache (e.g. file_id inválido), procedemos a descargar normal
            pass
            
    # --- END CACHE CHECK ---

    # Crear directorio temporal único
    import time
    timestamp = int(time.time())
    base_tmp = os.path.join(DATA_DIR, f"manga_{manga_id}_{timestamp}")
    os.makedirs(base_tmp, exist_ok=True)
    
    try:
        # 1. Obtener links
        await status_msg.edit(f"⏳ **{title}**\n🔍 Obteniendo lista de capítulos...")
        chapters = await get_manga_chapters(manga_id)
        
        if not chapters:
            await status_msg.edit("❌ No se encontraron capítulos o imágenes.")
            return

        # Seleccionar fuente inicial
        use_source = 'webp' if quality == 'webp' else 'original'
        
        img_queue = []
        for ch in chapters:
            ch_safe = "".join([c for c in ch['title'] if c.isalnum() or c in " -_"]).strip()
            ch_dir = os.path.join(base_tmp, ch_safe)
            os.makedirs(ch_dir, exist_ok=True)
            
            src_list = ch[use_source]
            if not src_list and use_source == 'original': src_list = ch['webp'] # Fallback
            
            for idx, url in enumerate(src_list):
                ext = url.split('?')[0].split('.')[-1].lower()
                if len(ext) > 4: ext = 'jpg'
                
                fname = f"{idx+1:03d}.{ext}"
                dest_path = os.path.join(ch_dir, fname)
                img_queue.append((url, dest_path))
        
        total = len(img_queue)
        await status_msg.edit(f"⏳ **{title}**\n⬇️ Descargando {total} imágenes ({quality.upper()})...")

        # 2. Descarga Concurrente
        async with aiohttp.ClientSession() as session:
            for i in range(0, total, 40):
                batch = img_queue[i:i+40]
                tasks = []
                for url, path in batch:
                    async def dl_task(u=url, p=path):
                        b = await download_image(session, u)
                        if b:
                            with open(p, 'wb') as f: f.write(b)
                    tasks.append(dl_task())
                await asyncio.gather(*tasks)
                
                if i % 20 == 0:
                    pct = int((i/total)*100)
                    try: await status_msg.edit(f"⏳ **{title}**\n⬇️ Descargando... {pct}%")
                    except: pass
        
        # 3. Conversión de Formato (si aplica)
        # Fix: img2pdf no soporta WebP. Telegram send_photo no soporta WebP con Alpha (a veces).
        # Si es PDF o IMG (Photo Mode) con WebP, forzamos conversión a JPG.
        force_jpg_for_pdf = (container == 'pdf')
        force_jpg_for_photo = (container == 'img' and not doc_mode and quality == 'webp')
        
        should_convert = quality in ['png', 'jpg'] or force_jpg_for_pdf or force_jpg_for_photo
        
        if should_convert:
            target_ext = f".{quality}" if quality in ['png', 'jpg'] else ".jpg"
            
            if force_jpg_for_pdf: 
                 await status_msg.edit(f"⏳ **{title}**\n⚙️ PDF: Convirtiendo imágenes a JPG compatible...")
            elif force_jpg_for_photo:
                 await status_msg.edit(f"⏳ **{title}**\n⚙️ IMG: Optimizando imágenes para envío rápido...")
            else:
                 await status_msg.edit(f"⏳ **{title}**\n⚙️ Convirtiendo a {quality.upper()}...")

            for root, _, files in os.walk(base_tmp):
                for file in files:
                    safe_path = os.path.join(root, file)
                    try:
                        fname, cur_ext = os.path.splitext(file)
                        if cur_ext.lower() == target_ext: continue

                        with Image.open(safe_path) as im:
                            rgb_im = im.convert('RGB')
                            new_path = os.path.join(root, fname + target_ext)
                            rgb_im.save(new_path, quality=95)
                        
                        if new_path != safe_path: os.remove(safe_path)
                    except Exception as e:
                        print(f"Error converting {file}: {e}")

        # 4. Empaquetado o Envío Directo
        from database import global_config
        dump_channel_id = global_config.get('dump_channel_id')
        
        # Helper para enviar/guardar
        async def upload_and_cache(file_path, caption, is_doc, c_key):
             # 1. Determinar destino de upload real (Dump si existe, sino Usuario)
             # Evitar bucle si el destino YA es el dump channel
             target_upload_chat = chat_id
             is_proxyING = False
             
             if dump_channel_id and str(chat_id) != str(dump_channel_id):
                 target_upload_chat = dump_channel_id
                 is_proxyING = True
                 
             # 2. Upload
             sent_msg = None
             if is_doc:
                 sent_msg = await client.send_document(target_upload_chat, file_path, caption=caption)
             else:
                 sent_msg = await client.send_photo(target_upload_chat, file_path, caption=caption)
                 
             # 3. Cachear
             fid = None
             if sent_msg:
                 if sent_msg.document: fid = sent_msg.document.file_id
                 elif sent_msg.photo: fid = sent_msg.photo.file_id
                 
                 if fid:
                     manga_cache[c_key] = fid
                     save_manga_cache()
                     
             # 4. Si hicimos Proxy, ahora entregamos al Usuario original
             if is_proxyING and fid:
                 if is_doc:
                     await client.send_document(chat_id, fid, caption=caption)
                 else:
                     await client.send_photo(chat_id, fid, caption=caption)
             
             return sent_msg

        # 4. Empaquetado o Envío Directo (IMG BATCH con PROXY)
        from database import global_config
        dump_channel_id = global_config.get('dump_channel_id')

        if container == 'img':
            await status_msg.edit(f"📤 **{title}**\nEnviando {total} imágenes...")
            
            # Recolectar todos los archivos finales ordenados
            all_files = []
            for ch in chapters:
                ch_safe = "".join([c for c in ch['title'] if c.isalnum() or c in " -_"]).strip()
                ch_dir = os.path.join(base_tmp, ch_safe)
                if not os.path.exists(ch_dir): continue
                imgs = sorted(os.listdir(ch_dir))
                for im in imgs:
                    all_files.append(os.path.join(ch_dir, im))

            if not all_files:
                return await status_msg.edit("❌ Error: No se descargaron imágenes.")
            
            # --- DETERMINAR DESTINO Y MODO PROXY ---
            # Si is_sync=True, el chat_id ES el dump channel, así que target_chat = chat_id.
            # Si is_sync=False, chat_id es el usuario. Si tenemos dump_id config, target_chat = dump_id.
            
            target_upload_chat = chat_id
            is_proxyING = False
            
            if dump_channel_id and str(chat_id) != str(dump_channel_id):
                 target_upload_chat = dump_channel_id
                 is_proxyING = True
            
            # Si estamos en Sync o Proxy, enviamos 1 a 1 para asegurar IDs
            # Lista para guardar file_ids
            sent_file_ids = []

            # Nota: Si group_mode=True y es proxy, es risky porque captura IDs de album es diff.
            # Forzamos group_mode=False si es is_proxyING o is_sync para asegurar cacheo robusto.
            use_group_mode = False if (is_proxyING or is_sync) else group_mode

            if not use_group_mode:
                # ENVIAR 1 a 1 (Lento pero Seguro para Cache)
                for idx, f in enumerate(all_files):
                    if idx % 5 == 0: await status_msg.edit(f"📤 **Enviando...** {idx+1}/{len(all_files)}")
                    try:
                        # Enviar al TARGET (Dump o User) with CAPTION
                        # Caption minimalista para no ensuciar, pero con ID para búsqueda
                        # ID debe ser searchable
                        img_cap = f"🆔 `{manga_id}`\n📚 {title} - {os.path.basename(f)}"
                        
                        msg = None
                        if doc_mode: msg = await client.send_document(target_upload_chat, f, caption=img_cap)
                        else: msg = await client.send_photo(target_upload_chat, f, caption=img_cap)
                        
                        if msg:
                             if msg.document: sent_file_ids.append(msg.document.file_id)
                             elif msg.photo: sent_file_ids.append(msg.photo.file_id)
                        
                        # Pausa anti-flood
                        await asyncio.sleep(0.5) 
                        
                    except FloodWait as e:
                        print(f"⏳ FloodWait: {e.value}s")
                        await asyncio.sleep(e.value + 1)
                    except Exception as e:
                        print(f"Error {f}: {e}")
            else:
                 # Group logic (Solo para usuario final directo sin cacheo estricto)
                 # Reverting to original IMG block just for context, but applying ZIP/PDF proxy below.
                 if doc_mode:
                    for i in range(0, len(all_files), 10):
                        chunk = all_files[i:i+10]
                        media = [InputMediaDocument(f) for f in chunk]
                        try:
                             msgs = await client.send_media_group(target_upload_chat, media)
                             if msgs:
                                for m in msgs:
                                    if m.document: sent_file_ids.append(m.document.file_id)
                             await asyncio.sleep(1.5)
                        except FloodWait as e: await asyncio.sleep(e.value + 1)
                        except: pass
                 else:
                    for i in range(0, len(all_files), 10):
                        chunk = all_files[i:i+10]
                        media = [InputMediaPhoto(f) for f in chunk]
                        try: 
                            msgs = await client.send_media_group(target_upload_chat, media)
                            if msgs:
                                for m in msgs:
                                    if m.photo: sent_file_ids.append(m.photo.file_id)
                            await asyncio.sleep(1.5)
                        except FloodWait as e: await asyncio.sleep(e.value + 1)
                        except: pass

            # --- SAVE IMG CACHE ---
            if sent_file_ids:
                manga_cache[cache_key] = sent_file_ids
                save_manga_cache()
            
            # --- DELIVERY PHASE (Si hicimos Proxy) ---
            # Si is_sync=True, YA TERMINAMOS (Solo queríamos subir al dump).
            # Si is_sync=False y is_proxyING=True (Usuario pidió, subimos a Dump), ahora reenviamos al usuario.
            
            if is_proxyING and not is_sync and sent_file_ids:
                # Reenviar al Usuario (chat_id original)
                await status_msg.edit("📤 **Reenviando al chat...**")
                
                # Optimización: Reenviar IDs? O usar send_photo con file_id?
                # Usar send_photo con file_id es más limpio.
                
                # Usar group_mode original del user request
                if group_mode:
                     # Reenviar como album
                     chunk_size = 10
                     for i in range(0, len(sent_file_ids), chunk_size):
                         chunk = sent_file_ids[i:i+chunk_size]
                         media = []
                         for fid in chunk:
                             if doc_mode: media.append(InputMediaDocument(fid))
                             else: media.append(InputMediaPhoto(fid))
                         try:
                             await client.send_media_group(chat_id, media)
                             await asyncio.sleep(1)
                         except: pass
                else:
                    # Reenviar 1 a 1
                    for fid in sent_file_ids:
                        try:
                            if doc_mode: await client.send_document(chat_id, fid)
                            else: await client.send_photo(chat_id, fid)
                            await asyncio.sleep(0.3)
                        except: pass

            await status_msg.delete()
            return

        # 4. Empaquetado (ZIP o PDF) - AQUÍ APLICAMOS LA PROXY
        await status_msg.edit(f"⏳ **{title}**\n📦 Creando archivo {container.upper()}...")
        final_file = None
        
        if container == 'pdf':
            all_imgs_paths = []
            for ch in chapters:
                ch_safe = "".join([c for c in ch['title'] if c.isalnum() or c in " -_"]).strip()
                ch_dir = os.path.join(base_tmp, ch_safe)
                if not os.path.exists(ch_dir): continue
                imgs = sorted(os.listdir(ch_dir))
                for im in imgs:
                    all_imgs_paths.append(os.path.join(ch_dir, im))
            
            if all_imgs_paths:
                pdf_path = os.path.join(DATA_DIR, f"{title} [{quality.upper()}].pdf")
                with open(pdf_path, "wb") as f:
                    f.write(img2pdf.convert(all_imgs_paths))
                final_file = pdf_path
                
        else:
            # ZIP
            zip_path = os.path.join(DATA_DIR, f"{title} [{quality.upper()}].zip")
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for root, _, files in os.walk(base_tmp):
                    for file in files:
                        abs_path = os.path.join(root, file)
                        arc_name = os.path.relpath(abs_path, base_tmp)
                        zipf.write(abs_path, arc_name)
            final_file = zip_path

        # 5. Enviar (CON PROXY AL DUMP)
        if final_file and os.path.exists(final_file):
            await status_msg.edit(f"📤 **{title}**\nSubiendo archivo ({os.path.getsize(final_file)/1024/1024:.1f} MB)...")
            
            cap = f"📚 **{title}**\n👤 {manga_data['author']}\n🆔 `{manga_id}`\n📦 {container.upper()} | 🎨 {quality.upper()}"
            
            # USA LA PROXY FUNCTION
            await upload_and_cache(final_file, cap, True, cache_key)
            
            try: os.remove(final_file)
            except: pass
        else:
            await status_msg.edit("❌ Error al crear el archivo final.")

    except asyncio.CancelledError:
        print(f"🛑 Descarga Cancelada: {title}")
        await status_msg.edit("🛑 **Descarga Cancelada.**")
        raise 

    except Exception as e:
        print(f"❌ Error Proceso: {e}")
        await status_msg.edit(f"❌ Error crítico: {e}")
        
    finally:
        try: shutil.rmtree(base_tmp)
        except: pass
        # Si es Sync, no borramos el mensaje de status pues el bucle padre lo usa
        if is_sync: pass 

