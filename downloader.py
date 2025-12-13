import re
import math
import os
import time
import asyncio
import yt_dlp
import shutil
import subprocess
import aiohttp
from pyrogram import enums
from config import LIMIT_2GB, HAS_FAST, DOWNLOAD_DIR, TOOLS_DIR, FAST_PATH
from database import get_config, downloads_db, guardar_db, add_active, remove_active
from utils import sel_cookie, traducir_texto
from tools_media import get_thumb, get_meta, get_audio_dur, progreso
from firebase_service import get_cached_file, save_cached_file

# Límite real de Telegram para dividir (1.9 GB para ir seguros)
TG_LIMIT = int(1.9 * 1024 * 1024 * 1024)

# Detectamos si tienes la herramienta Turbo instalada (Cross-Platform)
# Priorizamos tools/
RE_NAME = "N_m3u8DL-RE.exe" if os.name == 'nt' else "N_m3u8DL-RE"
RE_PATH = os.path.join(TOOLS_DIR, RE_NAME)

if not os.path.exists(RE_PATH):
    RE_PATH = shutil.which("N_m3u8DL-RE") 
    if not RE_PATH:
         if os.path.exists("N_m3u8DL-RE.exe"): RE_PATH = "N_m3u8DL-RE.exe"
         elif os.path.exists("N_m3u8DL-RE"): RE_PATH = "./N_m3u8DL-RE"

HAS_RE = RE_PATH is not None and os.path.exists(RE_PATH)

async def get_mediafire_link(url):
    """
    Extracts the direct download link from a Mediafire URL.
    Attempts to find the main download button via Regex.
    """
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers={"User-Agent": "Mozilla/5.0"}) as resp:
                if resp.status != 200: return None
                text = await resp.text()
                
                # Buscar el link en el aria-label o href del botón de descarga
                # Pattern: href="h..." id="downloadButton"
                match = re.search(r'href="([^"]+)"\s+id="downloadButton"', text)
                if match:
                    return match.group(1)
                
                # Fallback: buscar aria-label="Download file"
                match2 = re.search(r'href="([^"]+)"[^>]+aria-label="Download file"', text)
                if match2:
                    return match2.group(1)
                
    except Exception as e:
        print(f"Error scraping Mediafire: {e}")
    return None

async def get_yourupload_link(url):
    """
    Extracts the direct video link from a YourUpload URL.
    YourUpload is known for simple protection or direct embed.
    """
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Referer": url
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, allow_redirects=True) as resp:
                if resp.status != 200: return None
                text = await resp.text()
                
                # 1. Check og:video (Easiest)
                match_og = re.search(r'property="og:video"\s+content="([^"]+)"', text)
                if match_og: return match_og.group(1)
                
                # 2. Check jwplayer setup
                match_jw = re.search(r"file\s*:\s*['\"]([^'\"]+)['\"]", text)
                if match_jw:
                    link = match_jw.group(1)
                    if link.startswith("/"): return "https://www.yourupload.com" + link
                    return link
                
                # 3. Direct source tag
                match_src = re.search(r'<source\s+src="([^"]+)"', text)
                if match_src:
                    link = match_src.group(1)
                    if link.startswith("/"): return "https://www.yourupload.com" + link
                    return link

    except Exception as e:
        print(f"Error scraping YourUpload: {e}")
    return None

async def procesar_descarga(client, chat_id, url, calidad, datos, msg_orig):
    conf = get_config(chat_id)
    vid_id = datos.get('id')
    
    final = None
    thumb = None
    ts = int(time.time())
    status = None
    # Usar directorio de descargas
    base_name = os.path.join(DOWNLOAD_DIR, f"dl_{chat_id}_{ts}")

    url_descarga = url
    ckey = calidad
    
    # Si viene del Sniffer/JAV Extractor
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

    # --- ZONA DE CACHE (FIREBASE) ---
    cached_fid = None
    if vid_id:
        cached_fid = await get_cached_file(vid_id, ckey)

    if cached_fid:
        try:
            print(f"✨ Firebase Cache Hit: {vid_id} [{ckey}]")
            file_id = cached_fid
            
            res_str = f"{calidad}p" if calidad.isdigit() else calidad.upper()
            cap_cache = f"🎬 **{datos.get('titulo','Video')}**\n⚙️ {res_str} | ✨ (Reenviado al instante)"
            
            if calidad == "mp3": 
                await client.send_audio(chat_id, file_id, caption=cap_cache)
            else:
                try:
                    await client.send_video(chat_id, file_id, caption=cap_cache)
                except:
                    await client.send_document(chat_id, file_id, caption=cap_cache)
            return
        except Exception as e:
            print(f"⚠️ Cache inválido o borrado: {e}")

    # Register Task for Anti-Spam / Cancellation
    curr_task = asyncio.current_task()
    add_active(chat_id, msg_orig.id, curr_task)

    try:
        # Variables de control de progreso
        last_edit = 0
        start_time = time.time()
        loop = asyncio.get_running_loop()
        
        def progress_hook(d):
            nonlocal last_edit
            now = time.time()
            
            # Filtro Anti-Flood (Editar cada 4 segundos máx o al finalizar)
            if d['status'] == 'finished' or (now - last_edit) > 4:
                last_edit = now
                
                # Extraer datos de YT-DLP / Fast
                percent = d.get('_percent_str', '0%').strip()
                # Limpiar caracteres ANSI si Fast los mete
                percent = re.sub(r'\x1b\[[0-9;]*m', '', percent)
                
                speed = d.get('_speed_str', 'N/A').strip()
                eta = d.get('_eta_str', 'N/A').strip()
                
                # Fallback simple si no hay speed string
                if speed == 'N/A' and d.get('speed'):
                    speed = format_bytes(d.get('speed')) + "/s"
                    
                try:
                    msg_text = (
                        f"⏳ **Descargando...**\n"
                        f"📥 {calidad}\n"
                        f"🚀 **Motor:** {engine_name}\n\n"
                        f"📊 **{percent}** | ⚡ **{speed}** | ⏳ **{eta}**"
                    )
                    # FIX: Ejecutar la corrutina en el loop principal de forma segura desde el hilo de yt-dlp
                    asyncio.run_coroutine_threadsafe(status.edit(msg_text), loop)
                except: pass

        status = await client.send_message(chat_id, f"⏳ **Descargando...**\n📥 {calidad}")
        
        # --- LOGICA DE SELECCIÓN DE MOTOR ---
        engine_name = "Nativo (Estándar)"
        is_direct_download = False
        mediafire_link = None
        yourupload_link = None
        
        # 1. Mediafire Check
        if "mediafire.com" in url_descarga:
            await status.edit(f"⏳ **Mediafire Check...**\n🔍 Buscando enlace directo...")
            mf_link = await get_mediafire_link(url_descarga)
            if mf_link:
                url_descarga = mf_link
                engine_name = "Mediafire (Directo)"
                is_direct_download = True
                mediafire_link = True
            else:
                pass 

        # 2. YourUpload Check
        elif "yourupload.com" in url_descarga:
             await status.edit(f"⏳ **YourUpload Check...**\n🔍 Buscando video directo...")
             yu_link = await get_yourupload_link(url_descarga)
             if yu_link:
                 url_descarga = yu_link
                 engine_name = "YourUpload (Directo)"
                 is_direct_download = True
                 yourupload_link = True
             else:
                 pass

        # 3. Turbo Check
        usar_turbo = HAS_RE and ".m3u8" in url_descarga and calidad != "mp3" and not mediafire_link and not yourupload_link

        if usar_turbo: 
            engine_name = "Turbo (N_m3u8DL-RE)"
        elif is_direct_download or (HAS_FAST and not calidad.startswith("html_") and conf.get('fast_enabled', True)):
            if not is_direct_download: 
                 engine_name = "Fast (Ultra)"

        await status.edit(f"⏳ **Descargando...**\n📥 {calidad}\n🚀 **Motor:** {engine_name}")

        if usar_turbo:
            # Es mucho más rápido que yt-dlp para unir segmentos
            cmd = [
                RE_PATH,
                url_descarga,
                "--save-name", base_name,
                "--save-dir", ".",       # Guardar en carpeta actual
                "--tmp-dir", "tmp",      # Temporales
                "--no-log",              # No llenar la consola
                "--auto-select",         # Elegir mejor video/audio auto
                "--check-segments-count", "false", # No verificar cada segmento (Más velocidad)
                "--thread-count", "16",  # 16 Hilos de descarga
                "--download-retry-count", "10" # Reintentar si falla un trozo
            ]
            
            # Ejecutamos el proceso CON PIPE para leer salida
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            # Loop para leer progreso de Turbo
            while True:
                line = await process.stdout.readline()
                if not line: break
                
                line_str = line.decode('utf-8', errors='ignore').strip()
                
                if "Progress:" in line_str:
                    now_t = time.time()
                    if (now_t - last_edit) > 4:
                        last_edit = now_t
                        p_match = re.search(r'Progress:\s*([\d\.]+%?)', line_str)
                        s_match = re.search(r'Speed:\s*([\d\.]+\s*\w+/s)', line_str)
                        
                        perc = p_match.group(1) if p_match else "..."
                        spd = s_match.group(1) if s_match else "..."
                        
                        try:
                            await status.edit(
                                f"⏳ **Descargando...**\n"
                                f"📥 {calidad}\n"
                                f"🚀 **Motor:** {engine_name}\n\n"
                                f"📊 **{perc}** | ⚡ **{spd}**"
                            )
                        except: pass
            
            await process.wait()
            
            # Buscamos qué archivo creó (puede ser mp4 o mkv)
            for ext in ['.mp4', '.mkv', '.ts']:
                if os.path.exists(f"{base_name}{ext}"):
                    final = f"{base_name}{ext}"
                    break
        
        # --- MODO DIRECTO (FAST/MEDIAFIRE PURO) ---
        elif is_direct_download or (str(vid_id).startswith("direct_") and HAS_FAST):
             
             # En modo directo, el nombre final no siempre es MP4. 
             # Si es mediafire, intentamos adivinar extensión o usar temp name
             temp_out = f"dl_{chat_id}_{ts}_temp"
             
             cookie_file = sel_cookie(url)
             
             cmd = [
                 FAST_PATH if os.path.exists(FAST_PATH) else "aria"+"2c", 
                 url_descarga,
                 "-o", f"dl_{chat_id}_{ts}_temp", 
                 "-d", DOWNLOAD_DIR,
                 "-x", "16", "-s", "16", "-j", "1", "-k", "1M",
                 "--user-agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                 "--check-certificate=false",
                 "--allow-overwrite=true",
                 "--auto-file-renaming=false"
             ]
             
             if yourupload_link:
                 cmd.extend(["--header", f"Referer: {url}"])
             
             if cookie_file:
                 cmd.extend(["--load-cookies", cookie_file])

             # Ejecutar
             process = await asyncio.create_subprocess_exec(*cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
             
             # Loop simple de progreso
             start_t = time.time()
             while process.returncode is None:
                 try:
                     await asyncio.sleep(3)
                     elapsed = int(time.time() - start_t)
                     await status.edit(f"⏳ **Descargando...**\n🚀 **Motor:** {engine_name}\n⏱ Tiempo: {elapsed}s")
                 except: pass
                 
                 if process.returncode is not None: break
                 try: 
                    await asyncio.wait_for(process.wait(), timeout=0.1)
                 except: pass

             final_temp = os.path.join(DOWNLOAD_DIR, temp_out)
             if os.path.exists(final_temp):
                 # Intentar detectar extensión real si podemos (usando libmagic o simplemente renombrando si Mediafire redirigió a un archivo con ext)
                 # En este caso simple, si sabemos que es mediafire, el link solía tener el nombre.
                 # Pero aria2 guarda con el nombre que le dimos.
                 
                 # Estrategia: Ver si file es Video o ZIP
                 # Renombramos a algo seguro por ahora, luego decidiremos si es Video o Doc
                 final = final_temp
             else:
                 # Fallback wget basico?
                 pass

        else:
            # --- MODO CLÁSICO (YT-DLP) ---
            # Para YouTube, Facebook, Twitter, etc.
            opts = {
                'outtmpl': f"{base_name}.%(ext)s",
                'quiet': True, 
                'no_warnings': True, 
                'max_filesize': LIMIT_2GB,
                'progress_hooks': [progress_hook], # HOOK AÑADIDO
                'http_headers': {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36'}
            }

            if calidad == "mp3":
                opts.update({'format': 'bestaudio/best', 'postprocessors': [{'key': 'FFmpegExtractAudio','preferredcodec': 'mp3'}]})
            elif calidad.isdigit():
                 opts['format'] = f"bv*[height<={calidad}]+ba/b[height<={calidad}] / best"
            else:
                 opts['format'] = 'best'
            opts['merge_output_format'] = 'mp4'

            cookie_file = sel_cookie(url_descarga)
            if cookie_file: opts['cookiefile'] = cookie_file

            # --- FAST: ACELERADOR DE DESCARGAS ---
            if HAS_FAST and not calidad.startswith("html_") and conf.get('fast_enabled', True):
                print(f"🚀 Usando Fast para: {url_descarga}")
                opts.update({
                    'external_downloader': FAST_PATH if os.path.exists(FAST_PATH) else 'aria'+'2c',
                    'external_downloader_args': ['-x','16','-k','1M','-s','16']
                })

            # Twitter Fix
            if "twitter.com" in url_descarga or "x.com" in url_descarga:
                 opts['http_headers']['User-Agent'] = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'

            loop = asyncio.get_running_loop()
            with yt_dlp.YoutubeDL(opts) as ydl:
                try:
                    await loop.run_in_executor(None, lambda: ydl.download([url_descarga]))

                except Exception as e:
                    # FIX: WinError 32 (El archivo está siendo usado)
                    str_err = str(e)
                    
                    if "WinError 32" in str_err or "used by another process" in str_err:
                        print("⚠️ Detectado conflicto de archivos (WinError 32). Intentando recuperar...")
                        await asyncio.sleep(2) 
                        
                        posible_temp = f"{base_name}.temp.mp4"
                        posible_final = f"{base_name}.mp4"
                        
                        if not os.path.exists(posible_final) and os.path.exists(posible_temp):
                            try:
                                os.rename(posible_temp, posible_final)
                                print("✅ Archivo renombrado manualmente con éxito.")
                            except Exception as ren_err:
                                print(f"❌ Error al renombrar manual: {ren_err}")
                    else:
                        raise e 
            
            if calidad == "mp3": final = f"{base_name}.mp3"
            else:
                for e in ['.mp4', '.mkv', '.webm']:
                    if os.path.exists(base_name+e): 
                        final = base_name+e
                        break
        
        # --- POST-PROCESADO: DETECCION DE TIPO Y RENOMBRAMIENTO ---
        if not final or not os.path.exists(final):
            await status.edit("❌ **Error de descarga.**\nEl enlace puede estar protegido o expiró.")
            return
        
        # Si venimos de descarga directa sin extensión clara
        # Intentamos detectar si es video por firma o simplemente asumimos Documento si no parece video
        is_video = False
        
        # Lista de extensiones de video comunes
        vid_exts = ['.mp4', '.mkv', '.avi', '.mov', '.webm', '.flv', '.m4v']
        
        # Detectar extensión actual
        _, ext = os.path.splitext(final)
        if ext.lower() in vid_exts:
            is_video = True
        elif is_direct_download:
            # Si descargamos de mediafire, a veces el archivo no tiene extensión si usamos aria2 con output fijo
            # Intentar ver si el nombre original del link tenía extensión
            # O simplemente ver si es reproducible.
            
            # Simple check: Si el usuario pidió MP3, es audio.
            if calidad == "mp3": is_video = False
            else:
                # Si no tiene extensión, intentar renombrar con la del link original si existe
                if not ext:
                    # Intento muy básico de sacar nombre del url mediafire original
                    # url: .../file/xyz/Nombre_Archivo.rar/file
                    possible_name = url.split('/')[-2] if '/file/' in url else "downloaded_file"
                    if '.' in possible_name:
                        new_ext = os.path.splitext(possible_name)[1]
                        new_final = final + new_ext
                        os.rename(final, new_final)
                        final = new_final
                        ext = new_ext
                
                # YOURUPLOAD FIX: Forzar .mp4 si viene de yourupload y no tiene ext
                if yourupload_link and not ext:
                    new_final = final + ".mp4"
                    os.rename(final, new_final)
                    final = new_final
                    is_video = True
                elif ext.lower() in vid_exts: is_video = True
                else: is_video = False

        # Forzar is_video si yt-dlp fue usado exitosamente (generalmente descarga videos), salvo mp3
        if not is_direct_download and calidad != "mp3":
            is_video = True

        file_size = os.path.getsize(final)
        await status.edit("📝 **Procesando Metadatos...**")
        w, h, dur = 0, 0, 0
        thumb = None
        
        # SI ES VIDEO O AUDIO
        if is_video or final.lower().endswith(('.mp3', '.m4a')):
            if final.lower().endswith(('.mp3', '.m4a')):
                dur = await get_audio_dur(final)
            else:
                thumb = await get_thumb(final, chat_id, ts)
                w, h, dur = await get_meta(final)
        else:
            # ES DOCUMENTO (ZIP, RAR, ETC)
            # No sacamos thumb ni meta de video
            pass
        
        files_to_send = [final]
        is_split = False
            
        # --- LÓGICA DE CORTE (SPLIT) - SOLO SI ES VIDEO ---
        # Si es un ZIP de 3GB, Telegram permite hasta 2GB (4GB con Premium, bot tiene 2GB limit por API a veces)
        # Si es Documento > 2GB, fallará. Split de ZIPs es complejo.
        # Por ahora solo cortamos VIDEO.
        if is_video and file_size > TG_LIMIT and calidad != "mp3":
            from utils import split_video_generic, format_bytes
            
            sz_fmt = format_bytes(file_size)
            num_parts = int(-(-file_size // TG_LIMIT)) 
            est_part_size = format_bytes(file_size / num_parts)

            await status.edit(
                f"✂️ **Video Grande Detectado ({sz_fmt})**\n"
                f"🔪 Cortando en **{num_parts} partes** de ~**{est_part_size}**\n"
                "⏳ Por favor espera..."
            )
            
            loop = asyncio.get_running_loop()
            new_files = await loop.run_in_executor(None, lambda: split_video_generic(final, 'parts', num_parts))
            
            if new_files:
                files_to_send = new_files
                is_split = True
                try: os.remove(final) 
                except: pass

        # --- BUCLE DE SUBIDA ---
        for i, f_path in enumerate(files_to_send):
            msg_label = f"📤 **Subiendo Parte {i+1}/{len(files_to_send)}...**" if is_split else "📤 **Subiendo...**"
            await status.edit(msg_label)
            
            cur_dur = dur
            if is_split:
                 _, _, cur_dur = await get_meta(f_path)
            
            cap = ""
            # Caption solo si conf tiene meta activado
            if conf['meta']:
                t = datos.get('titulo','Archivo')
                # Si es mediafire y tenemos filename en path, usarlo
                if is_direct_download: t = os.path.basename(f_path)
                
                if is_split: t += f" [Parte {i+1}/{len(files_to_send)}]"
                
                if conf['lang'] == 'es' and not is_direct_download: t = await traducir_texto(t) # Traducir solo si no es filename literal
                
                tags = [f"#{x.replace(' ','_')}" for x in (datos.get('tags') or [])[:10]]
                res_str = f"{w}x{h}" if w else ("Audio" if calidad=="mp3" else "Archivo")
                cap = f"🎬 **{t}**\n⚙️ {res_str}"
                if cur_dur: cap += f" | ⏱ {time.strftime('%H:%M:%S', time.gmtime(cur_dur))}"
                if tags: cap += f"\n{' '.join(tags)}"
                cap = cap[:1024]

            act = enums.ChatAction.UPLOAD_AUDIO if calidad == "mp3" else (enums.ChatAction.UPLOAD_VIDEO if is_video else enums.ChatAction.UPLOAD_DOCUMENT)
            
            res = None
            try:
                # DECISIÓN FINAL DE ENVÍO
                if calidad == "mp3":
                     res = await client.send_audio(chat_id, f_path, caption=cap, duration=cur_dur, thumb=thumb, progress=progreso, progress_args=(status, [time.time(),0], act), reply_to_message_id=msg_orig.id)
                elif is_video and not conf.get('doc_mode'):
                    # ENVIAR COMO VIDEO
                    res = await client.send_video(chat_id, f_path, caption=cap, width=w, height=h, duration=cur_dur, thumb=thumb, progress=progreso, progress_args=(status, [time.time(),0], act), reply_to_message_id=msg_orig.id)
                else:
                    # ENVIAR COMO DOCUMENTO (ZIP, RAR, o Video si doc_mode activo)
                    res = await client.send_document(chat_id, f_path, caption=cap, thumb=thumb, progress=progreso, progress_args=(status, [time.time(),0], act), reply_to_message_id=msg_orig.id)
            except Exception as e:
                print(f"❌ Error subiendo parte {i+1}: {e}")
                await client.send_message(chat_id, f"❌ Error al subir parte {i+1}: {e}")

            # Guardar en Firebase (y DB local si se quiere, por ahora solo Firebase)
            if res and vid_id and not calidad.startswith("html_") and not is_split and "m3u8" not in url:
                fid = None
                if res.audio: fid = res.audio.file_id
                elif res.video: fid = res.video.file_id
                elif res.document: fid = res.document.file_id
                
                if fid:
                    await save_cached_file(vid_id, ckey, fid, meta=datos)
            
            if is_split:
                try: os.remove(f_path)
                except: pass

    except Exception as e:
        print(f"Excepción: {e}")
        if status: await status.edit(f"❌ Error: {e}")
    finally:
        remove_active(chat_id, msg_orig.id) # Cleanup Anti-Spam
        for f in [final, thumb, f"dl_{chat_id}_{ts}.jpg"]:
            if f and os.path.exists(f):
                try: os.remove(f)
                except: pass
        if status:
            try: await status.delete()
            except: pass