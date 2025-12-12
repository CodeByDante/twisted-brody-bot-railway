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

async def download_image(session, url):
    """Descarga una imagen y retorna sus bytes."""
    try:
        async with session.get(url) as resp:
            if resp.status == 200:
                return await resp.read()
    except: pass
    return None

async def process_manga_download(client, chat_id, manga_data, format_type, status_msg):
    """
    Descarga, procesa y envía el manga.
    format_type: 'original', 'webp', 'png', 'jpg', 'pdf'
    """
    manga_id = manga_data['id']
    title = manga_data['title']
    
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

        total_imgs = 0
        dl_tasks = []
        
        # Seleccionar fuente según formato
        # Original, PNG, JPG, PDF -> Usamos 'original' (mejor calidad base)
        # WebP -> Usamos 'webp'
        use_source = 'original'
        if format_type == 'webp': use_source = 'webp'
        
        # Preparar lista de descargas
        # Aplanamos: Lista de (url, path_destino)
        # Estructura: tmp/Cap1/001.ext
        
        img_queue = []
        
        for ch in chapters:
            ch_safe = "".join([c for c in ch['title'] if c.isalnum() or c in " -_"]).strip()
            ch_dir = os.path.join(base_tmp, ch_safe)
            os.makedirs(ch_dir, exist_ok=True)
            
            src_list = ch[use_source]
            if not src_list and use_source == 'original': src_list = ch['webp'] # Fallback
            
            for idx, url in enumerate(src_list):
                ext = url.split('?')[0].split('.')[-1].lower()
                if len(ext) > 4: ext = 'jpg' # Fix extensiones raras
                
                fname = f"{idx+1:03d}.{ext}"
                dest_path = os.path.join(ch_dir, fname)
                img_queue.append((url, dest_path))
        
        total = len(img_queue)
        await status_msg.edit(f"⏳ **{title}**\n⬇️ Descargando {total} imágenes ({format_type.upper()})...")

        # 2. Descarga Concurrente (Lotes de 10)
        async with aiohttp.ClientSession() as session:
            for i in range(0, total, 10):
                batch = img_queue[i:i+10]
                tasks = []
                for url, path in batch:
                    async def dl_task(u=url, p=path):
                        b = await download_image(session, u)
                        if b:
                            with open(p, 'wb') as f: f.write(b)
                    tasks.append(dl_task())
                await asyncio.gather(*tasks)
                
                # Feedback visual cada 20%
                if i % 20 == 0:
                    pct = int((i/total)*100)
                    try: await status_msg.edit(f"⏳ **{title}**\n⬇️ Descargando... {pct}%")
                    except: pass
        
        # 3. Procesamiento / Conversión / Empaquetado
        await status_msg.edit(f"⏳ **{title}**\n⚙️ Procesando formato {format_type.upper()}...")
        
        # Si es PDF, juntamos todo en un solo PDF grande? O por capítulo?
        # Generalmente un PDF por manga completo puede ser gigante. 
        # Haremos UN archivo final (ZIP o PDF) que contenga todo, o un ZIP con carpetas?
        # El user dijo "Descargar ZIP" o "Descargar PDF". Asumimos UN archivo.
        
        final_file = None
        
        if format_type == 'pdf':
            # Juntar todas las imágenes ordenadas
            all_imgs_paths = []
            for ch in chapters:
                ch_safe = "".join([c for c in ch['title'] if c.isalnum() or c in " -_"]).strip()
                ch_dir = os.path.join(base_tmp, ch_safe)
                if not os.path.exists(ch_dir): continue
                
                imgs = sorted(os.listdir(ch_dir))
                for im in imgs:
                    all_imgs_paths.append(os.path.join(ch_dir, im))
            
            if all_imgs_paths:
                pdf_path = os.path.join(base_tmp, f"{title}.pdf")
                with open(pdf_path, "wb") as f:
                    f.write(img2pdf.convert(all_imgs_paths))
                final_file = pdf_path
                
        else:
            # ZIP (Original, WebP, PNG, JPG)
            # Primero convertir si hace falta
            if format_type in ['png', 'jpg']:
                for root, _, files in os.walk(base_tmp):
                    for file in files:
                        safe_path = os.path.join(root, file)
                        try:
                            # Abrir y convertir
                            with Image.open(safe_path) as im:
                                rgb_im = im.convert('RGB')
                                new_ext = '.png' if format_type == 'png' else '.jpg'
                                base_w = os.path.splitext(safe_path)[0]
                                new_path = base_w + new_ext
                                
                                rgb_im.save(new_path, quality=95 if format_type == 'jpg' else None)
                            
                            # Borrar original si es diferente
                            if new_path != safe_path: os.remove(safe_path)
                            
                        except Exception as e:
                            print(f"Error converting {file}: {e}")

            # Crear ZIP
            zip_path = os.path.join(DATA_DIR, f"{title} [{format_type.upper()}].zip")
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for root, _, files in os.walk(base_tmp):
                    for file in files:
                        abs_path = os.path.join(root, file)
                        # Estructura dentro del ZIP: Capítulo X/001.jpg
                        arc_name = os.path.relpath(abs_path, base_tmp)
                        zipf.write(abs_path, arc_name)
            
            final_file = zip_path

        # 4. Enviar
        if final_file and os.path.exists(final_file):
            await status_msg.edit(f"📤 **{title}**\nSubiendo archivo ({os.path.getsize(final_file)/1024/1024:.1f} MB)...")
            
            cap = f"📚 **{title}**\n👤 {manga_data['author']}\n📦 Formato: {format_type.upper()}"
            await client.send_document(chat_id, final_file, caption=cap)
            
            try: os.remove(final_file)
            except: pass
        else:
            await status_msg.edit("❌ Error al crear el archivo final.")

    except Exception as e:
        print(f"❌ Error Proceso: {e}")
        await status_msg.edit(f"❌ Error crítico: {e}")
        
    finally:
        # Limpieza
        try: shutil.rmtree(base_tmp)
        except: pass

