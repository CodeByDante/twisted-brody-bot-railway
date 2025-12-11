import os
import json
import time
import asyncio
import subprocess
from pyrogram import enums
from config import HAS_FFMPEG

# --- FUNCIONES DE MEDIA (FFMPEG) ---

async def get_thumb(path, cid, ts):
    out = f"t_{cid}_{ts}.jpg"
    if HAS_FFMPEG:
        try:
            # Extrae un frame en el segundo 2
            cmd = [
                "ffmpeg", "-i", path, "-ss", "00:00:02", 
                "-vframes", "1", out, "-y"
            ]
            process = await asyncio.create_subprocess_exec(
                *cmd, 
                stdout=subprocess.DEVNULL, 
                stderr=subprocess.DEVNULL
            )
            await process.wait()
            
            if os.path.exists(out): 
                return out
        except Exception as e:
            print(f"Error thumb: {e}")
    return None

async def get_meta(path):
    if not HAS_FFMPEG: return 0, 0, 0
    try:
        cmd = [
            "ffprobe", "-v", "error", "-select_streams", "v:0", 
            "-show_entries", "stream=width,height,duration", 
            "-of", "json", path
        ]
        process = await asyncio.create_subprocess_exec(
            *cmd, 
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        stdout, _ = await process.communicate()
        
        d = json.loads(stdout)
        s = d['streams'][0]
        return int(s.get('width', 0)), int(s.get('height', 0)), int(float(s.get('duration', 0)))
    except:
        return 0, 0, 0

async def get_audio_dur(path):
    try:
        cmd = [
            "ffprobe", "-v", "error", 
            "-show_entries", "format=duration", 
            "-of", "json", path
        ]
        process = await asyncio.create_subprocess_exec(
            *cmd, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE
        )
        stdout, _ = await process.communicate()
        return int(float(json.loads(stdout)['format']['duration']))
    except:
        return 0

async def progreso(cur, tot, msg, times, act):
    now = time.time()
    if (now - times[1]) > 4 or cur == tot:
        times[1] = now
        try:
            await msg._client.send_chat_action(msg.chat.id, act)
            per = cur * 100 / tot
            mb_cur = cur / 1024 / 1024
            mb_tot = tot / 1024 / 1024
            txt = f"📤 **Subiendo...**\n📊 {per:.1f}% | 📦 {mb_cur:.1f}/{mb_tot:.1f} MB"
            await msg.edit_text(txt)
        except: 
            pass