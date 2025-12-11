#!/bin/bash

echo "🚀 Iniciando Instalación Twisted Brody Bot en Termux..."

# 1. Actualizar repositorios e instalar paquetes base
echo "📦 Instalando dependencias del sistema..."
pkg update -y && pkg upgrade -y
pkg install -y python ffmpeg aria2 git rust binutils build-essential openssl-tool libjpeg-turbo typelib

# 2. Instalar dependencias de Python
echo "🐍 Instalando librerías de Python..."
# Fix cryptg/tgcrypto build issues on Termux
export CFLAGS="-Wno-deprecated-declarations -Wno-unreachable-code"
pip install --upgrade pip
pip install wheel
pip install -r requirements.txt

# 3. Configurar Gallery-DL para Termux (Aria2)
echo "⚙️ Configurando Gallery-DL + Aria2..."
# Sobrescribimos gallery-dl.conf para usar la ruta de aria2 en Termux
cat > gallery-dl.conf <<EOL
{
    "downloader": {
        "program": "aria2c",
        "args": ["-x", "16", "-s", "16", "-j", "16", "-k", "1M"]
    }
}
EOL

# 4. Crear carpetas necesarias
mkdir -p cookies data downloads tools

echo "✅ Instalación Completa."
echo "ℹ️  Para iniciar el bot ejecuta: python main.py"
