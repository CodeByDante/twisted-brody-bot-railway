import google.generativeai as genai
from config import GEMINI_API_KEY
import asyncio

genai.configure(api_key=GEMINI_API_KEY)

candidates = [
    "gemini-1.5-flash",
    "gemini-1.5-flash-latest",
    "gemini-1.5-flash-001",
    "gemini-1.0-pro",
    "gemini-pro",
    "gemini-2.0-flash-exp"
]

async def test():
    print("Testing models...")
    for model_name in candidates:
        try:
            print(f"Testing: {model_name}")
            model = genai.GenerativeModel(model_name)
            response = await model.generate_content_async("Hello")
            print(f"✅ SUCCESS: {model_name}")
            print(f"Response: {response.text}")
            return # Stop at first success
        except Exception as e:
            print(f"❌ FAILED: {model_name} -> {e}")

asyncio.run(test())
