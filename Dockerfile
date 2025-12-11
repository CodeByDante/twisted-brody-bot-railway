FROM python:3.10-slim

# Instalar ffmpeg y dependencias del sistema
# Instalar ffmpeg y utilidades
RUN apt-get update && apt-get install -y ffmpeg curl wget

# Descargar N_m3u8DL-RE (Turbo) para Linux
RUN wget https://github.com/nilaoda/N_m3u8DL-RE/releases/download/v0.2.0/N_m3u8DL-RE_v0.2.0_linux-amd64_20230628.tar.gz && \
    tar -xzf N_m3u8DL-RE_v0.2.0_linux-amd64_20230628.tar.gz && \
    mv N_m3u8DL-RE_v0.2.0_linux-amd64/N_m3u8DL-RE /usr/local/bin/N_m3u8DL-RE && \
    chmod +x /usr/local/bin/N_m3u8DL-RE && \
    rm -rf N_m3u8DL-RE*

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
