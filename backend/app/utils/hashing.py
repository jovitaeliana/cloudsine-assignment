import hashlib
import inspect
from io import BytesIO


class _SyncReader:
    """Wraps a sync file-like so it presents the same async read() interface."""

    def __init__(self, f):
        self._f = f

    async def read(self, size: int = -1) -> bytes:
        return self._f.read(size)


async def hash_and_buffer(source, chunk_size: int = 64 * 1024) -> tuple[str, BytesIO]:
    """Stream a source into a BytesIO buffer while computing its SHA-256.

    Accepts either an async-read file-like (e.g. FastAPI UploadFile) or a
    sync file-like (e.g. BytesIO). Returns (hex_digest, buffer) with the
    buffer rewound to position 0.
    """
    reader = source if inspect.iscoroutinefunction(getattr(source, "read", None)) else _SyncReader(source)

    hasher = hashlib.sha256()
    buf = BytesIO()

    while True:
        chunk = await reader.read(chunk_size)
        if not chunk:
            break
        hasher.update(chunk)
        buf.write(chunk)

    buf.seek(0)
    return hasher.hexdigest(), buf
