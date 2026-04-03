import pytest
from backend.downloader import download_and_decrypt


@pytest.mark.asyncio
async def test_download_empty_url():
    with pytest.raises(ValueError, match="Empty download URL"):
        await download_and_decrypt("", "/tmp/test.glb")


@pytest.mark.asyncio
async def test_download_invalid_url():
    with pytest.raises(ValueError):
        await download_and_decrypt("https://invalid.example.com/nonexistent.glb", "/tmp/test.glb")
