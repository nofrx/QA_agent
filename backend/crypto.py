import numpy as np
from ctypes import c_int32


def _int32(n: int) -> int:
    return c_int32(n).value


def _generate_key_vectorized(n: int) -> np.ndarray:
    """Generate XOR key stream using Xorshift32 PRNG, vectorized in chunks."""
    key = np.zeros(n, dtype=np.uint8)
    rng_state = _int32(n)

    # Process in chunks for progress on large files
    chunk_size = 1_000_000
    for start in range(0, n, chunk_size):
        end = min(start + chunk_size, n)
        for i in range(start, end):
            rng_state = _int32(rng_state ^ _int32(rng_state << 13))
            rng_state = _int32(rng_state ^ _int32(rng_state >> 17))
            rng_state = _int32(rng_state ^ _int32(rng_state << 5))
            key[i] = rng_state & 0xFF

    return key


def decrypt_glb(data: bytes) -> bytes:
    """Decrypt XOR/Xorshift32-encrypted GLB data. Returns bytes."""
    if is_valid_glb(data):
        return data

    arr = np.frombuffer(data, dtype=np.uint8).copy()
    n = len(arr)
    key = _generate_key_vectorized(n)
    decrypted = np.bitwise_xor(arr, key)
    return decrypted.tobytes()


def is_valid_glb(data: bytes) -> bool:
    """Check if data starts with glTF magic bytes."""
    return len(data) >= 4 and data[:4] == b'glTF'
