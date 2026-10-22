from httpx import Timeout
from supabase import create_client, Client

from app.core.config import settings


def get_supabase_client() -> Client:
    """
    สร้าง Supabase Client สำหรับใช้ภายใน Backend
    โดยใช้ Service Role เพื่อเข้าถึงข้อมูลโปรไฟล์และโควตา
    """
    client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)

    storage_timeout = float(settings.STORAGE_DOWNLOAD_TIMEOUT_SECONDS)
    client.storage._client.timeout = Timeout(storage_timeout)

    postgrest_timeout = float(settings.SUPABASE_POSTGREST_TIMEOUT_SECONDS)
    if hasattr(client, "postgrest") and hasattr(client.postgrest, "session"):
        client.postgrest.session.timeout = Timeout(postgrest_timeout)

    return client