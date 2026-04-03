import os
import httpx
from backend.crypto import decrypt_glb, is_valid_glb

async def download_and_decrypt(url: str, output_path: str, on_progress=None) -> str:
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        encrypted_data = resp.content
    if on_progress:
        await on_progress(f"Downloaded {len(encrypted_data) / 1024 / 1024:.1f} MB")
    if is_valid_glb(encrypted_data):
        decrypted_data = encrypted_data
    else:
        decrypted_data = decrypt_glb(encrypted_data)
    if not is_valid_glb(decrypted_data):
        raise ValueError(f"Decryption failed — output is not valid glTF")
    with open(output_path, 'wb') as f:
        f.write(decrypted_data)
    if on_progress:
        await on_progress(f"Saved to {output_path}")
    return output_path

async def download_sku_models(cloudfront_base, raw_filename, touchedup_filename, autoshadow_filename, output_dir, on_progress=None):
    raw_path = os.path.join(output_dir, "raw_scan.glb")
    touchedup_path = os.path.join(output_dir, "touched_up.glb")
    autoshadow_path = os.path.join(output_dir, "autoshadow.glb")
    if on_progress: await on_progress("Downloading raw scan...")
    await download_and_decrypt(f"{cloudfront_base}/{raw_filename}", raw_path, on_progress)
    if on_progress: await on_progress("Downloading touched-up model...")
    await download_and_decrypt(f"{cloudfront_base}/{touchedup_filename}", touchedup_path, on_progress)
    if on_progress: await on_progress("Downloading autoshadow model...")
    await download_and_decrypt(f"{cloudfront_base}/{autoshadow_filename}", autoshadow_path, on_progress)
    return raw_path, touchedup_path, autoshadow_path
