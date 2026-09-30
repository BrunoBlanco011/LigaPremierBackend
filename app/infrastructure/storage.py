import logging

from storage3.exceptions import StorageApiError
from supabase import Client

from app.core.exceptions import AppError

logger = logging.getLogger(__name__)


class SupabaseFileStorage:
    def __init__(self, client: Client, bucket: str) -> None:
        self.client = client
        self.bucket = bucket

    def upload(self, path: str, content: bytes, content_type: str) -> str:
        bucket = self.client.storage.from_(self.bucket)
        try:
            bucket.upload(path, content, {"content-type": content_type, "upsert": "true", "cache-control": "3600"})
        except StorageApiError as exc:
            raise AppError(f"No se pudo subir el archivo: {exc.message}") from exc
        return bucket.get_public_url(path)

    def delete(self, path: str) -> None:
        # Borrar un archivo viejo nunca debe tumbar la operacion principal
        try:
            self.client.storage.from_(self.bucket).remove([path])
        except StorageApiError:
            logger.warning("No se pudo eliminar %s del bucket %s", path, self.bucket, exc_info=True)
