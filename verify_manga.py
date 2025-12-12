import asyncio
from unittest.mock import AsyncMock, MagicMock
from manga_service import handle_comic_request
import json
import os

async def test_manga_flow():
    print("🚀 Starting Manga Flow Verification...")

    # Mock Client and Message
    mock_client = AsyncMock()
    mock_msg = MagicMock()
    mock_msg.chat.id = 123456789
    
    # Mock status message for editing
    mock_status_msg = AsyncMock()
    mock_client.send_message.return_value = mock_status_msg

    # 1. Test ZIP Download (Action: download_comic)
    # Using a known safe gallery-dl supported URL (or generic if possible)
    # Since I don't want to actually download huge files, I will mock descargar_galeria if possible, 
    # BUT I actually want to test the library integration. 
    # I'll use a specific small gallery or just rely on the fallback logic if URL fails?
    # Let's try to mock the 'descargar_galeria' in mang_service to return local dummy files.
    
    print("\n--- TEST 1: ZIP Generation ---")
    
    # Create dummy images
    os.makedirs("test_images", exist_ok=True)
    os.makedirs("test_images_tmp_dir", exist_ok=True)
    img_paths = []
    import PIL.Image
    
    for i in range(3):
        path = f"test_images/img_{i}.jpg"
        img = PIL.Image.new('RGB', (100, 100), color = (73, 109, 137))
        img.save(path)
        img_paths.append(os.path.abspath(path))
        
    # Monkeypatch utils.descargar_galeria inside manga_service? 
    # Hard to patch inside imported module dynamically without reload. 
    # I'll just mock the result of the executor call if I can, or better:
    # I'll just temporarily swap the function in the module.
    
    import manga_service
    # import utils # No longer needed for patching if we patch the destination
    
    # Mocking descargar_galeria locally in manga_service
    original_downloader = manga_service.descargar_galeria
    # Use side_effect to ensure it returns the tuple when called
    manga_service.descargar_galeria = MagicMock(side_effect=lambda u: (img_paths, "test_images_tmp_dir"))
    
    # Mock shutil.rmtree to prevent deletion of temp files during verification
    original_rmtree = manga_service.shutil.rmtree
    manga_service.shutil.rmtree = MagicMock()
    
    print(f"DEBUG: Dummy images: {img_paths}")
    
    # Payload
    payload = json.dumps({
        "action": "download_comic",
        "manga_id": "test_id",
        "manga_title": "Test Manga ZIP",
        "url": "https://example.com/gallery"
    })
    
    await handle_comic_request(mock_client, mock_msg, payload)
    
    # Verify calls
    mock_client.send_message.assert_called()
    print("✅ Initial status sent.")
    mock_client.send_document.assert_called()
    args = mock_client.send_document.call_args
    print(f"✅ send_document called with: {args}")
    
    uploaded_file = args[1]['document']
    if uploaded_file.endswith(".zip") and os.path.exists(uploaded_file):
        print(f"✅ ZIP file created at: {uploaded_file}")
    else:
        print("❌ ZIP file creation failed or not found.")

    # 2. Test PDF Download
    print("\n--- TEST 2: PDF Generation ---")
    os.makedirs("test_images_tmp_dir", exist_ok=True) # Recreate dir as it was deleted by previous run
    payload_pdf = json.dumps({
        "action": "download_comic_pdf",
        "manga_id": "test_id_pdf",
        "manga_title": "Test Manga PDF",
        "url": "https://example.com/gallery"
    })
    
    # Reset mock
    mock_client.reset_mock()
    mock_client.send_message.return_value = mock_status_msg
    
    await handle_comic_request(mock_client, mock_msg, payload_pdf)
    
    mock_client.send_document.assert_called()
    args_pdf = mock_client.send_document.call_args
    uploaded_pdf = args_pdf[1]['document']
    
    if uploaded_pdf.endswith(".pdf") and os.path.exists(uploaded_pdf):
        print(f"✅ PDF file created at: {uploaded_pdf}")
    else:
        print("❌ PDF file creation failed.")

    # Cleanup
    manga_service.descargar_galeria = original_downloader
    manga_service.shutil.rmtree = original_rmtree
    import shutil
    shutil.rmtree("test_images")
    if os.path.exists("test_images_tmp_dir"):
        shutil.rmtree("test_images_tmp_dir")

    print("\n✅ Verification Complete.")

if __name__ == "__main__":
    asyncio.run(test_manga_flow())
