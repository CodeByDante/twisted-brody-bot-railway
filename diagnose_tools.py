import asyncio
import os
import sys

# Ensure project root is in path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from utils import descargar_galeria
from config import TOOLS_DIR

async def check_gallery_dl():
    print("--- Checking Gallery-DL ---")
    
    # Check executable
    tools_path = os.path.join(TOOLS_DIR, "gallery-dl.exe")
    pip_path = r"C:\Users\Gonzalo\AppData\Roaming\Python\Python311\Scripts\gallery-dl.exe"
    
    found = False
    if os.path.exists(tools_path):
        print(f"✅ Found in tools: {tools_path}")
        found = True
    elif os.path.exists(pip_path):
        print(f"✅ Found in pip: {pip_path}")
        found = True
    else:
        print("⚠️ Not found in standard paths. Relying on PATH.")
        
    # Check execution
    print("\n--- Testing Download (Dry Run) ---")
    test_url = "https://twitter.com/Twitter/status/1234567890" # Dummy URL, expectation is failure or specific error, but checking if binary runs
    
    # We just want to see if it tries to run without crashing python
    try:
        # Intentionally usage with invalid URL to check if binary launches
        print("Running dummy download check...")
        
        # Use simple version check
        exec_path = tools_path if os.path.exists(tools_path) else pip_path
        if not os.path.exists(exec_path):
             exec_path = "gallery-dl" # Fallback to PATH
             
        import subprocess
        # Use exec_path directly
        cmd = [exec_path, "--version"]
        print(f"Command: {cmd}")
        ver = subprocess.check_output(cmd, shell=True).decode()
        print(f"✅ Gallery-DL Version: {ver.strip()}")
        
    except Exception as e:
        print(f"❌ Error running gallery-dl: {e}")

if __name__ == "__main__":
    asyncio.run(check_gallery_dl())
