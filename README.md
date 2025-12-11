# 🤖 Twisted Brody Bot Pro

Bot de Telegram avanzado para descargar videos de múltiples plataformas (X/Twitter, JAV, Pornhub, YouTube, etc.) con soporte para fragmentación de video (Party Mode), gestión de cookies y descarga acelerada.

## 🚀 Características
- **Descargas Multi-Sitio:** Soporte para cientos de webs vía `yt-dlp` y `gallery-dl`.
- **Modo Party (Cortador):** Corta videos por partes iguales, tiempo o rango manual (Ej: 10:00 - 10:30).
- **Modo Compresor:** Reduce el peso de videos (Ligero/Medio/Fuerte) usando FFmpeg.
- **JAV Turbo:** Extractor directo para sitios JAV (.m3u8) para máxima velocidad.
- **Aceleración Aria2:** Descargas utra-rápidas (16 conexiones por archivo).
- **Gestión de Cookies:** Soporte para cuentas premium/privadas.
- **Metadatos Inteligentes:** Opcional (Título, duración, resolución).

---

## 📱 Instalación en Termux (Android)

Sigue estos pasos para instalar el bot en tu móvil:

### 1. Preparar Termux
Si es la primera vez que usas Termux, ejecuta esto para dar acceso al almacenamiento:
```bash
termux-setup-storage
```

### 2. Clonar Repositorio
Copia y pega este comando para descargar el bot:
```bash
pkg install git -y
pkg install git -y
git clone https://github.com/CodeByDante/twisted-brody-bot
cd twisted-brody-bot
```

### 3. Instalación Automática
Ejecuta el script de instalación automática:
```bash
chmod +x setup_termux.sh
./setup_termux.sh
```

### 4. Configurar Tokens
Edita el archivo `config.py` con tus datos de Telegram:
```bash
nano config.py
```
*(Cambia `API_ID`, `API_HASH` y `BOT_TOKEN`)*.
Para guardar en nano: `CTRL+O`, `Enter`, `CTRL+X`.

### 5. Iniciar Bot
```bash
python main.py
```

---

## 💻 Instalación en Windows
1. Instalar [Python 3.10+](https://www.python.org/).
2. Instalar dependencias: `pip install -r requirements.txt`.
3. Ejecutar `python main.py`.

> **Nota:** El bot intentará usar las herramientas en la carpeta `tools/` si existen, o las del sistema.

---
## 🍪 Cookies (Opcional)
Para descargar de sitios que requieren login (Pornhub Premium, etc.), coloca tus archivos `.txt` de cookies en la carpeta `cookies/`. El bot busca nombres como:
- `cookies_pornhub.txt`
- `cookies_x.txt`
- `cookies_instagram.txt`
