FROM python:3.10-slim

# Instalar ffmpeg y dependencias del sistema
# Instalar ffmpeg y utilidades
RUN apt-get update && apt-get install -y ffmpeg curl wget

# N_m3u8DL-RE (Turbo) eliminado para evitar errores de build (404)
# El bot usará yt-dlp nativo automáticamente.

# Carpeta de trabajo
WORKDIR /app

# Copiar archivos del bot
COPY . .

# Instalar dependencias de Python
RUN pip install --no-cache-dir -r requirements.txt

# Instalar Navegadores para Playwright (ELIMINADO)
# RUN playwright install chromium --with-deps

# Ejecutar el bot
CMD ["python", "main.py"]
