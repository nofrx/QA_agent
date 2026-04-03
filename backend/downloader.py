import os
import httpx
from backend.crypto import decrypt_glb, is_valid_glb


async def download_and_decrypt(url: str, output_path: str, on_progress=None, retries: int = 2) -> str:
    """Download GLB from URL, decrypt if needed, save to output_path."""
    if not url:
        raise ValueError("Empty download URL")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    last_error = None
    for attempt in range(retries + 1):
        try:
            async with httpx.AsyncClient(timeout=180.0, follow_redirects=True) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                encrypted_data = resp.content
            break
        except (httpx.TimeoutException, httpx.NetworkError) as e:
            last_error = e
            if attempt < retries:
                if on_progress:
                    await on_progress(f"  Retry {attempt + 1}/{retries} after network error...")
                continue
            raise ValueError(f"Download failed after {retries + 1} attempts: {e}")
        except httpx.HTTPStatusError as e:
            raise ValueError(f"HTTP {e.response.status_code} downloading {url}")

    size_mb = len(encrypted_data) / (1024 * 1024)
    if on_progress:
        await on_progress(f"  Downloaded {size_mb:.1f} MB")

    if len(encrypted_data) < 20:
        raise ValueError(f"Downloaded file too small ({len(encrypted_data)} bytes)")

    if is_valid_glb(encrypted_data):
        decrypted_data = encrypted_data
    else:
        decrypted_data = decrypt_glb(encrypted_data)

    if not is_valid_glb(decrypted_data):
        raise ValueError("Decryption failed — output is not valid glTF")

    with open(output_path, 'wb') as f:
        f.write(decrypted_data)

    return output_path
