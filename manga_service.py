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
from firebase_service import get_cached_file, save_cached_file

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

async def process_manga_download(client, chat_id, manga_data, container, quality, status_msg, doc_mode=False, group_mode=True):
    """
    Descarga, procesa y envía el manga.
    container: 'zip', 'pdf' o 'img'
    quality: 'original', 'webp', 'png', 'jpg'
    """
    manga_id = manga_data['id']
    title = manga_data['title']
    
    # Crear directorio temporal único
    import time
    timestamp = int(time.time())
    base_tmp = os.path.join(DATA_DIR, f"manga_{manga_id}_{timestamp}")
    os.makedirs(base_tmp, exist_ok=True)
    
    try:
        # 0. KEY GENERATION & CACHE CHECK
        # Key format: manga_{id} // Field: {container}_{quality} (e.g. zip_original, img_webp)
        cache_key = f"{container}_{quality}"
        if doc_mode: cache_key += "_doc"
        
        cached_data = await get_cached_file(f"manga_{manga_id}", cache_key)
        
        if cached_data:
            await status_msg.edit(f"✨ **{title}**\n⚡ Enviando desde memoria (instantáneo)...")
            try:
                if isinstance(cached_data, list):
                    # ALBUM CACHE (Images)
                    if group_mode:
                        for i in range(0, len(cached_data), 10):
                            chunk = cached_data[i:i+10]
                            media = []
                            for fid in chunk:
                                if doc_mode: media.append(InputMediaDocument(fid))
                                else: media.append(InputMediaPhoto(fid))
                            try:
                                await client.send_media_group(chat_id, media)
                                await asyncio.sleep(1)
                            except FloodWait as fw: await asyncio.sleep(fw.value + 1)
                            except: pass
                    else:
                        for fid in cached_data:
                            try:
                                if doc_mode: await client.send_document(chat_id, fid)
                                else: await client.send_photo(chat_id, fid)
                                await asyncio.sleep(0.3)
                            except FloodWait as fw: await asyncio.sleep(fw.value + 1)
                            except: pass
                else:
                    # SINGLE FILE CACHE (ZIP/PDF)
                    cap = f"🎬 **{title}**\n👤 {manga_data.get('author','?')}\n✨ (Desde Memoria)"
                    await client.send_document(chat_id, cached_data, caption=cap)
                
                await status_msg.delete()
                return # EXIT SUCCESS
            except Exception as e:
                print(f"⚠️ Cache read failed: {e}")
                # Fallback to download if cache fail (e.g. invalid IDs)

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

        # 4. Empaquetado o Envío
        
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
            
            # --- ENVIAR AL USUARIO Y CAPTURAR FILE IDs ---
            sent_file_ids = []
            
            if group_mode:
                # Album Fotos/Docs
                for i in range(0, len(all_files), 10):
                    chunk = all_files[i:i+10]
                    media = []
                    for f in chunk:
                        if doc_mode: media.append(InputMediaDocument(f))
                        else: media.append(InputMediaPhoto(f))
                    
                    try:
                        # Capturar resultado
                        sent_msgs = await client.send_media_group(chat_id, media)
                        if sent_msgs:
                            for m in sent_msgs:
                                if m.photo: sent_file_ids.append(m.photo.file_id)
                                elif m.document: sent_file_ids.append(m.document.file_id)
                            
                        await asyncio.sleep(2) # Increased delay to prevent flood
                    except FloodWait as e:
                        await asyncio.sleep(e.value + 2)
                        # Retry once
                        try:
                            sent_msgs = await client.send_media_group(chat_id, media)
                            if sent_msgs:
                                for m in sent_msgs:
                                    if m.photo: sent_file_ids.append(m.photo.file_id)
                                    elif m.document: sent_file_ids.append(m.document.file_id)
                        except: pass
                    except Exception as e:
                        print(f"Error sending chunk {i}: {e}")
            else:
                # 1 a 1 Fotos/Docs
                for f in all_files:
                    try:
                        m = None
                        if doc_mode: m = await client.send_document(chat_id, f)
                        else: m = await client.send_photo(chat_id, f)
                        
                        if m:
                             if m.photo: sent_file_ids.append(m.photo.file_id)
                             elif m.document: sent_file_ids.append(m.document.file_id)
                             
                        await asyncio.sleep(0.3)
                    except FloodWait as e: await asyncio.sleep(e.value + 1)
                    except: pass

            # SAVE TO CACHE (List of IDs)
            if sent_file_ids:
                await save_cached_file(f"manga_{manga_id}", cache_key, sent_file_ids, meta={'title': title})

            await status_msg.delete()
            return
        
        # ZIP o PDF
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

        # Enviar Archivo Final
        if final_file and os.path.exists(final_file):
            await status_msg.edit(f"📤 **{title}**\nSubiendo archivo ({os.path.getsize(final_file)/1024/1024:.1f} MB)...")
            
            cap = f"📚 **{title}**\n👤 {manga_data['author']}\n🆔 `{manga_id}`\n📦 {container.upper()} | 🎨 {quality.upper()}"
            
            try:
                msg = await client.send_document(chat_id, final_file, caption=cap, progress=progreso, progress_args=(status_msg, [time.time(),0], "Subiendo..."))
                
                # SAVE CACHE (Single File ID)
                if msg and msg.document:
                     await save_cached_file(f"manga_{manga_id}", cache_key, msg.document.file_id, meta={'title': title})
            
            except Exception as e:
                print(f"Error sending doc: {e}")
                await status_msg.edit(f"❌ Error al subir: {e}")
            
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

