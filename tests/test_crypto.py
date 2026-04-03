import numpy as np
from backend.crypto import decrypt_glb, is_valid_glb

def test_decrypt_known_gltf_magic():
    """Encrypt known glTF data, then decrypt and verify magic bytes."""
    original = b'glTF' + b'\x02\x00\x00\x00' + b'\x00' * 100
    n = len(original)
    data = np.frombuffer(original, dtype=np.uint8).copy()
    rng_state = np.int32(n)
    key = np.zeros(n, dtype=np.uint8)
    for i in range(n):
        rng_state = np.int32(rng_state ^ np.int32(rng_state << np.int32(13)))
        rng_state = np.int32(rng_state ^ np.int32(rng_state >> np.int32(17)))
        rng_state = np.int32(rng_state ^ np.int32(rng_state << np.int32(5)))
        key[i] = int(rng_state) & 0xFF
    encrypted = np.bitwise_xor(data, key).tobytes()

    decrypted = decrypt_glb(encrypted)
    assert decrypted[:4] == b'glTF'
    assert decrypted == original

def test_is_valid_glb():
    assert is_valid_glb(b'glTF\x02\x00\x00\x00')
    assert not is_valid_glb(b'\x00\x00\x00\x00')
    assert not is_valid_glb(b'')

def test_decrypt_already_valid():
    """If data is already valid glTF, return as-is."""
    data = b'glTF' + b'\x02\x00\x00\x00' + b'\x00' * 100
    result = decrypt_glb(data)
    assert result == data
