import hashlib
from io import BytesIO

from app.utils.hashing import hash_and_buffer


async def test_hash_and_buffer_small_file():
    payload = b"hello world"
    expected = hashlib.sha256(payload).hexdigest()

    digest, buf = await hash_and_buffer(BytesIO(payload))

    assert digest == expected
    assert buf.getvalue() == payload


async def test_hash_and_buffer_multi_chunk():
    payload = b"a" * (1024 * 1024 + 7)
    expected = hashlib.sha256(payload).hexdigest()

    digest, buf = await hash_and_buffer(BytesIO(payload))

    assert digest == expected
    assert len(buf.getvalue()) == len(payload)


async def test_hash_and_buffer_empty():
    digest, buf = await hash_and_buffer(BytesIO(b""))

    assert digest == hashlib.sha256(b"").hexdigest()
    assert buf.getvalue() == b""
