import re
import base64
import requests
import os
import urllib.parse

# Headers simulando Chrome en Windows (Menos sospechoso para Cloudflare con Cookies)
JAV_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
    'Referer': 'https://www.google.com/',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'none',
    'Sec-Fetch-User': '?1'
}

def load_cookies(filename):
    """Carga cookies desde archivo Netscape."""
    cookies = {}
    if os.path.exists(filename):
        try:
            with open(filename, 'r') as f:
                for line in f:
                    if line.strip().startswith('#') or not line.strip(): continue
                    parts = line.strip().split('\t')
                    if len(parts) >= 7:
                        cookies[parts[5]] = parts[6]
        except: pass
    return cookies

def decode_base64(s):
    try:
        return base64.b64decode(s + '=' * (-len(s) % 4)).decode('utf-8')
    except: return None

def find_m3u8_deep(text):
    """Busca cualquier cosa que parezca un m3u8 en el texto sucio."""
    candidates = set()
    
    # 1. Patrón clásico http...m3u8
    matches = re.findall(r'(https?://[^\s"\'<>]+?\.m3u8[^\s"\'<>]*)', text)
    for m in matches:
        # Limpiar escapes de JSON
        clean = m.replace('\\/', '/')
        candidates.add(clean)
        
    # 2. Patrón Base64 común en JAV (file: "...")
    b64_matches = re.findall(r'file\s*:\s*["\']([a-zA-Z0-9+/=]{20,})["\']', text)
    for b in b64_matches:
        decoded = decode_base64(b)
        if decoded and 'http' in decoded and '.m3u8' in decoded:
            candidates.add(decoded)
            
    return candidates

def extraer_jav_directo(url):
    print(f"⚡ [JAV Turbo] Atacando: {url}")
    session = requests.Session()
    
    # Cargar cookies (CRUCIAL para javxxx)
    c = load_cookies('cookies_jav.txt')
    if not c: c = load_cookies('cookies_pornhub.txt') # Fallback
    session.cookies.update(c)
    
    final_links = []
    seen = set()
    
    try:
        # Petición principal
        r = session.get(url, headers=JAV_HEADERS, timeout=15)
        if r.status_code in [403, 503]:
            print(f"❌ Cloudflare bloqueo (HTTP {r.status_code}). Las cookies pueden estar vencidas.")
            return []
            
        html = r.text
        
        # 1. BÚSQUEDA DIRECTA EN EL HTML PRINCIPAL
        found_urls = find_m3u8_deep(html)
        for u in found_urls:
            if u not in seen:
                seen.add(u)
                final_links.append({'url': u, 'size': 0, 'res': 'JAV Direct (Main)'})

        # 2. BÚSQUEDA DE IFRAMES (El video suele estar aquí)
        # Buscamos cualquier iframe
        iframes = re.findall(r'<iframe[^>]+src=["\']([^"\']+)["\']', html)
        
        for iframe_src in iframes:
            if not iframe_src.startswith('http'): 
                if iframe_src.startswith('//'): iframe_src = 'https:' + iframe_src
                else: continue
            
            # Ignorar publicidad obvia
            if 'ads' in iframe_src or 'banner' in iframe_src: continue
            
            print(f"⚡ Escaneando Iframe: {iframe_src}")
            
            # Si encontramos un iframe, lo guardamos como 'Posible Video'
            # Esto sirve para que si fallamos en extraer el m3u8, al menos le demos a yt-dlp el link del iframe
            if iframe_src not in seen:
                seen.add(iframe_src)
                # Lo agregamos con baja prioridad, se sobrescribirá si encontramos el m3u8 dentro
                final_links.append({'url': iframe_src, 'size': 0, 'res': 'Iframe Player (YT-DLP)'})

            try:
                # Entramos al iframe
                headers_frame = JAV_HEADERS.copy()
                headers_frame['Referer'] = url
                r_frame = session.get(iframe_src, headers=headers_frame, timeout=10)
                
                # Buscamos m3u8 dentro del iframe
                frame_m3u8s = find_m3u8_deep(r_frame.text)
                for u in frame_m3u8s:
                    if u not in seen:
                        seen.add(u)
                        # ¡Bingo! Encontramos el video real dentro del iframe
                        final_links.insert(0, {'url': u, 'size': 0, 'res': 'JAV Stream (Extracted)'})
            except: 
                pass

    except Exception as e:
        print(f"⚠️ Error JAV Extractor: {e}")

    # Ordenar: Los .m3u8 extraídos van primero, los iframes crudos al final
    return sorted(final_links, key=lambda x: 0 if '.m3u8' in x['url'] or '.mp4' in x['url'] else 1)