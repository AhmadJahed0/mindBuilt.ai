"""File storage abstraction. Same swappable-provider pattern as app/llm.py —
'local' works immediately with zero setup (a Docker volume, fine for dev),
'supabase' is the real cloud backend the architecture doc calls for, but
needs a Supabase project and credentials in .env before it'll run. Nothing
else in the ingestion pipeline should touch the filesystem or a cloud SDK
directly — go through save_file()/read_file() so switching providers later
never touches ingestion code again.
"""

import os

from app.config import settings


def save_file(key: str, content: bytes) -> str:
    """Stores the file under `key` (e.g. "3_report.pdf") and returns the
    storage_path to persist on the Document row."""
    if settings.storage_provider == "supabase":
        return _save_supabase(key, content)
    return _save_local(key, content)


def read_file(storage_path: str) -> bytes:
    if storage_path.startswith("supabase://"):
        return _read_supabase(storage_path)
    with open(storage_path, "rb") as f:
        return f.read()


def delete_file(storage_path: str):
    if storage_path.startswith("supabase://"):
        return _delete_supabase(storage_path)
    if os.path.exists(storage_path):
        os.remove(storage_path)


def _save_local(key: str, content: bytes) -> str:
    os.makedirs(settings.storage_path, exist_ok=True)
    path = os.path.join(settings.storage_path, key)
    with open(path, "wb") as f:
        f.write(content)
    return path


def _save_supabase(key: str, content: bytes) -> str:
    if not settings.supabase_url or not settings.supabase_service_key:
        raise RuntimeError(
            "STORAGE_PROVIDER=supabase but SUPABASE_URL / SUPABASE_SERVICE_KEY "
            "aren't set in .env. Create a Supabase project (supabase.com), a "
            "storage bucket, and add its URL + service role key before using "
            "this provider — until then, use STORAGE_PROVIDER=local."
        )
    from supabase import create_client

    client = create_client(settings.supabase_url, settings.supabase_service_key)
    bucket = settings.supabase_bucket
    client.storage.from_(bucket).upload(
        key, content, {"content-type": "application/octet-stream", "upsert": "true"}
    )
    return f"supabase://{bucket}/{key}"


def _read_supabase(storage_path: str) -> bytes:
    if not settings.supabase_url or not settings.supabase_service_key:
        raise RuntimeError("STORAGE_PROVIDER=supabase but Supabase credentials aren't configured in .env.")
    from supabase import create_client

    _, _, rest = storage_path.partition("supabase://")
    bucket, _, key = rest.partition("/")
    client = create_client(settings.supabase_url, settings.supabase_service_key)
    return client.storage.from_(bucket).download(key)


def _delete_supabase(storage_path: str):
    if not settings.supabase_url or not settings.supabase_service_key:
        raise RuntimeError("STORAGE_PROVIDER=supabase but Supabase credentials aren't configured in .env.")
    from supabase import create_client

    _, _, rest = storage_path.partition("supabase://")
    bucket, _, key = rest.partition("/")
    client = create_client(settings.supabase_url, settings.supabase_service_key)
    client.storage.from_(bucket).remove([key])
