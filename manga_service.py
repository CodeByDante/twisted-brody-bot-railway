import os
import shutil
import zipfile
import img2pdf
import json
import asyncio
from utils import descargar_galeria
from pyrogram import Client
from pyrogram.types import Message, InputMediaDocument

async def handle_comic_request(client: Client, msg: Message, data_str: str):
    """
    Maneja la solicitud de descarga de cómic/manga desde la Mini App.
    Payload esperado (JSON):
    {
      "action": "download_comic" | "download_comic_pdf",
      "manga_id": "...",
      "manga_title": "...",
      "format": "...",
      "url": "..."
    }
    """
    try:
        data = json.loads(data_str)
    except json.JSONDecodeError:
        print(f"❌ Error decodificando WebAppData: {data_str}")
        return

    action = data.get('action')
    url = data.get('url')
    title = data.get('manga_title', 'Manga_Descarga')
    
    # Notificar al usuario inmediatamente
    status_msg = await client.send_message(
        chat_id=msg.chat.id,
        text=f"⬇️ **Iniciando descarga de:** {title}\nPor favor espera..."
    )

    if action not in ['download_comic', 'download_comic_pdf']:
        await status_msg.edit("⚠️ Acción desconocida o no soportada.")
        return

    # 1. Descargar imágenes
    # Usamos descargar_galeria de utils, que usa gallery-dl internamente.
    # Esta función ya maneja la creación de carpetas temporales.
    print(f"📚 Manga Service: Descargando de {url}")
    images, temp_dir = await asyncio.get_running_loop().run_in_executor(
        None, lambda: descargar_galeria(url)
    )

    if not images:
        await status_msg.edit("❌ No se pudieron encontrar imágenes en el enlace proporcionado.")
        if temp_dir and os.path.exists(temp_dir):
            try: shutil.rmtree(temp_dir)
            except: pass
        return

    await status_msg.edit(f"✅ **{len(images)} imágenes descargadas.**\n🗜 Procesando archivo ({'PDF' if 'pdf' in action else 'ZIP'})...")

    # 2. Procesar según acción
    try:
        output_file = None
        
        if action == 'download_comic':
            # Crear ZIP
            output_file = f"{title}.zip"
            # Asegurar nombre de archivo válido
            output_file = "".join([c for c in output_file if c.isalnum() or c in (' ', '.', '_', '-')]).strip()
            zip_path = os.path.join(temp_dir, output_file)
            
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                for img_path in images:
                    zf.write(img_path, arcname=os.path.basename(img_path))
            
            output_file = zip_path

        elif action == 'download_comic_pdf':
            # Crear PDF
            output_file = f"{title}.pdf"
            output_file = "".join([c for c in output_file if c.isalnum() or c in (' ', '.', '_', '-')]).strip()
            pdf_path = os.path.join(temp_dir, output_file)
            
            # img2pdf requiere bytes o rutas de archivos
            # Asegurar que son jpg/png válido para img2pdf (a veces da guerra con alpha channels, pero probemos directo)
            try:
                with open(pdf_path, "wb") as f:
                    f.write(img2pdf.convert(images))
                output_file = pdf_path
            except Exception as e:
                print(f"Error img2pdf: {e}")
                # Fallback simple si img2pdf falla (poco probable con jpgs limpios)
                raise e

        # 3. Enviar archivo
        await status_msg.edit("📤 **Subiendo archivo...**")
        
        await client.send_document(
            chat_id=msg.chat.id,
            document=output_file,
            caption=f"📚 **{title}**\n🔗 {url}"
        )
        
        await status_msg.delete()

    except Exception as e:
        print(f"❌ Error procesando manga: {e}")
        await status_msg.edit(f"❌ Ocurrió un error al procesar el archivo:\n`{str(e)}`")
    finally:
        # Limpieza
        if temp_dir and os.path.exists(temp_dir):
            try: shutil.rmtree(temp_dir)
            except: pass
