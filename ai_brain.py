import google.generativeai as genai
from config import GEMINI_API_KEY

has_ai = False
if GEMINI_API_KEY:
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        # Usamos flash o pro
        model = genai.GenerativeModel('gemini-2.0-flash-exp')
        has_ai = True
    except:
        print("⚠️ Error configurando Gemini AI")

async def ask_gemini(prompt):
    if not has_ai: return "⚠️ IA no configurada."
    
    try:
        chat = model.start_chat(history=[])
        # Contexto del sistema (Personalidad)
        system_prompt = (
            "Eres el asistente de este bot 'Twisted Brody'. "
            "Tu personalidad es útil, breve y un poco sarcástica. "
            "Hablas español. "
            "IMPORTANTE: SI EL USUARIO QUIERE DESCARGAR UN VIDEO Y PROPORCIONA UN LINK, "
            "TU RESPUESTA DEBE SER ÚNICA Y EXCLUSIVAMENTE: CMD_DL: <URL_DETECTADA>"
            "Ejemplo: CMD_DL: https://youtube.com/watch?v=123"
        )
        
        response = await chat.send_message_async(f"{system_prompt}\n\nUser: {prompt}")
        return response.text
    except Exception as e:
        return f"❌ Error IA: {e}"
