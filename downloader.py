import re
import math
import os
import time
import asyncio
import yt_dlp
import shutil
import subprocess
from pyrogram import enums
from config import LIMIT_2GB, HAS_FAST, DOWNLOAD_DIR, TOOLS_DIR, FAST_PATH
from database import get_config, downloads_db, guardar_db, add_active, remove_active
from utils import sel_cookie, traducir_texto
from tools_media import get_thumb, get_meta, get_audio_dur, progreso

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

    # --- ZONA DE CACHE (NO RE-DESCARGAR) ---
    if vid_id and vid_id in downloads_db and ckey in downloads_db[vid_id]:
        try:
            print(f"✨ Cache Hit: {vid_id} [{ckey}]")
            file_id = downloads_db[vid_id][ckey]
            
            res_str = f"{calidad}p" if calidad.isdigit() else calidad.upper()
            cap_cache = f"🎬 **{datos.get('titulo','Video')}**\n⚙️ {res_str} | ✨ (Reenviado al instante)"
            
            if calidad == "mp3": 
                await client.send_audio(chat_id, file_id, caption=cap_cache)
            else: 
                await client.send_video(chat_id, file_id, caption=cap_cache)
            return
        except Exception as e:
            print(f"⚠️ Cache inválido (Archivo borrado?): {e}")

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
        # Usamos N_m3u8DL-RE (Turbo) si:
        # 1. Existe el .exe en la carpeta.
        # 2. El enlace contiene .m3u8 (Clásico de JAV).
        # 3. No es una descarga de audio MP3.
        usar_turbo = HAS_RE and ".m3u8" in url_descarga and calidad != "mp3"

        engine_name = "Nativo (Estándar)"
        if usar_turbo: 
            engine_name = "Turbo (N_m3u8DL-RE)"
        elif HAS_FAST and not calidad.startswith("html_") and conf.get('fast_enabled', True):
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
                
                # Parsing de N_m3u8DL-RE output
                # Ejemplo: Progress: 45.5% | Speed: 5.2 MB/s ...
                if "Progress:" in line_str:
                    now_t = time.time()
                    if (now_t - last_edit) > 4:
                        last_edit = now_t
                        # Extraer % y Velocidad con Regex simple
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
        
        # --- MODO DIRECTO (FAST PURO) ---
        elif str(vid_id).startswith("direct_") and HAS_FAST:
             engine_name = "Fast (Directo)"
             await status.edit(f"⏳ **Descargando...**\n📥 Direct Link\n🚀 **Motor:** {engine_name}")
             
             final = f"{base_name}.mp4" # Asumimos MP4 por defecto en direct
             cookie_file = sel_cookie(url)
             
             cmd = [
                 FAST_PATH if os.path.exists(FAST_PATH) else "aria"+"2c", 
                 url,
                 "-o", f"dl_{chat_id}_{ts}.mp4", 
                 "-d", DOWNLOAD_DIR,
                 "-x", "16", "-s", "16", "-j", "1", "-k", "1M",
                 "--user-agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                 "--check-certificate=false",
                 "--allow-overwrite=true",
                 "--auto-file-renaming=false"
             ]
             
             if cookie_file:
                 cmd.extend(["--load-cookies", cookie_file])

             # Ejecutar
             process = await asyncio.create_subprocess_exec(*cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
             
             # Loop simple de progreso (leyendo stdout de fast es complejo, mejor solo esperar o leer chunks)
             # Fast interactive output no se lleva bien con PIPE.
             # Usaremos un timer simple para actualizar status "sigue vivo"
             
             start_t = time.time()
             while process.returncode is None:
                 try:
                     await asyncio.sleep(3)
                     elapsed = int(time.time() - start_t)
                     await status.edit(f"⏳ **Descargando...**\n🚀 **Motor:** Fast (Directo)\n⏱ Tiempo: {elapsed}s")
                 except: pass
                 
                 if process.returncode is not None: break
                 # Verificar si el proceso terminó
                 try: 
                    await asyncio.wait_for(process.wait(), timeout=0.1)
                 except: pass

             if os.path.exists(final):
                 pass # Éxito
             else:
                 # Si falló, intentar wget básico (requests)
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
            # Solo si está activado en config y existe el ejecutable
            if HAS_FAST and not calidad.startswith("html_") and conf.get('fast_enabled', True):
                print(f"🚀 Usando Fast para: {url_descarga}")
                opts.update({
                    'external_downloader': FAST_PATH if os.path.exists(FAST_PATH) else 'aria'+'2c',
                    'external_downloader_args': ['-x','16','-k','1M','-s','16']
                })

            # Twitter Fix
            if "twitter.com" in url_descarga or "x.com" in url_descarga:
                 opts['http_headers']['User-Agent'] = 'Mozilla/5.0 (Linux; Android 13; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Mobile Safari/537.36'

            loop = asyncio.get_running_loop()
            with yt_dlp.YoutubeDL(opts) as ydl:
                try:
                    await loop.run_in_executor(None, lambda: ydl.download([url_descarga]))

                except Exception as e:
                    # FIX: WinError 32 (El archivo está siendo usado)
                    # A veces Fast tarda en liberar el archivo antes de que yt-dlp lo renombre.
                    str_err = str(e)
                    
                    if "WinError 32" in str_err or "used by another process" in str_err:
                        print("⚠️ Detectado conflicto de archivos (WinError 32). Intentando recuperar...")
                        # ... (resto del código de recuperación) ...
                        await asyncio.sleep(2) # Esperamos a que se libere
                        
                        # Intentamos recuperar si el archivo final no existe pero el temp sí
                        posible_temp = f"{base_name}.temp.mp4"
                        posible_final = f"{base_name}.mp4"
                        
                        if not os.path.exists(posible_final) and os.path.exists(posible_temp):
                            try:
                                os.rename(posible_temp, posible_final)
                                print("✅ Archivo renombrado manualmente con éxito.")
                            except Exception as ren_err:
                                print(f"❌ Error al renombrar manual: {ren_err}")
                    else:
                        raise e # Si no es ninguno de los anteriores, lanzamos la excepción normal
            
            if calidad == "mp3": final = f"{base_name}.mp3"
            else:
                for e in ['.mp4', '.mkv', '.webm']:
                    if os.path.exists(base_name+e): 
                        final = base_name+e
                        break
        
        # --- SUBIDA A TELEGRAM ---
        if not final or not os.path.exists(final):
            await status.edit("❌ **Error de descarga.**\nEl enlace puede estar protegido (DRM) o expiró.")
            return
        
        file_size = os.path.getsize(final)
        # Límite global seguro (1.9GB)
        
        await status.edit("📝 **Procesando Metadatos...**")
        w, h, dur = 0, 0, 0
        thumb = None
        
        if final.lower().endswith(('.mp3', '.m4a')):
            dur = await get_audio_dur(final)
        else:
            thumb = await get_thumb(final, chat_id, ts)
            w, h, dur = await get_meta(final)
        
        files_to_send = [final]
        is_split = False
            
        # --- LÓGICA DE CORTE (SPLIT) ---
        if file_size > TG_LIMIT and calidad != "mp3":
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
            # Reutilizamos la lógica del Modo Party
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
            
            # Recalcular duración si es parte cortada
            cur_dur = dur
            if is_split:
                 _, _, cur_dur = await get_meta(f_path)
            
            cap = ""
            if conf['meta']:
                t = datos.get('titulo','Multimedia')
                if is_split: t += f" [Parte {i+1}/{len(files_to_send)}]"
                
                if conf['lang'] == 'es': t = await traducir_texto(t)
                tags = [f"#{x.replace(' ','_')}" for x in (datos.get('tags') or [])[:10]]
                res_str = f"{w}x{h}" if w else "Audio"
                cap = f"🎬 **{t}**\n⚙️ {res_str} | ⏱ {time.strftime('%H:%M:%S', time.gmtime(cur_dur))}\n{' '.join(tags)}"[:1024]

            act = enums.ChatAction.UPLOAD_AUDIO if calidad == "mp3" else (enums.ChatAction.UPLOAD_DOCUMENT if conf.get('doc_mode') else enums.ChatAction.UPLOAD_VIDEO)
            
            res = None
            try:
                if calidad == "mp3":
                     res = await client.send_audio(chat_id, f_path, caption=cap, duration=cur_dur, thumb=thumb, progress=progreso, progress_args=(status, [time.time(),0], act), reply_to_message_id=msg_orig.id)
                elif conf.get('doc_mode'):
                    res = await client.send_document(chat_id, f_path, caption=cap, thumb=thumb, progress=progreso, progress_args=(status, [time.time(),0], act), reply_to_message_id=msg_orig.id)
                else:
                    res = await client.send_video(chat_id, f_path, caption=cap, width=w, height=h, duration=cur_dur, thumb=thumb, progress=progreso, progress_args=(status, [time.time(),0], act), reply_to_message_id=msg_orig.id)
            except Exception as e:
                print(f"❌ Error subiendo parte {i+1}: {e}")
                # Si falla una parte, continuamos con las otras? Mejor notificar.
                await client.send_message(chat_id, f"❌ Error al subir parte {i+1}: {e}")

            # Solo guardamos en DB si NO es split y NO es m3u8 (dinámico)
            if res and vid_id and not calidad.startswith("html_") and not is_split and "m3u8" not in url:
                if vid_id not in downloads_db: downloads_db[vid_id] = {}
                # Intentar obtener file_id de audio, video o documento
                fid = None
                if res.audio: fid = res.audio.file_id
                elif res.video: fid = res.video.file_id
                elif res.document: fid = res.document.file_id
                
                if fid: downloads_db[vid_id][ckey] = fid
                guardar_db()
            
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