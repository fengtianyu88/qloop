"""MinIO object storage client utilities."""

import io
from datetime import timedelta

from minio import Minio
from minio.error import S3Error

from app.config import settings

# Create the MinIO client
minio_client = Minio(
    settings.MINIO_ENDPOINT,
    access_key=settings.MINIO_ACCESS_KEY,
    secret_key=settings.MINIO_SECRET_KEY,
    secure=settings.MINIO_SECURE,
)


def _ensure_bucket_exists() -> None:
    """Ensure the configured bucket exists; create it if missing."""
    try:
        if not minio_client.bucket_exists(settings.MINIO_BUCKET):
            minio_client.make_bucket(settings.MINIO_BUCKET)
    except S3Error as exc:
        # Re-raise so callers know the storage backend is unavailable,
        # but only if the bucket truly cannot be created.
        raise RuntimeError(
            f"Failed to ensure MinIO bucket '{settings.MINIO_BUCKET}' exists: {exc}"
        ) from exc


# Bucket is ensured lazily on first upload so that the application can
# start even when the MinIO backend is temporarily unavailable.
_bucket_ready: bool = False


def _ensure_bucket_lazy() -> None:
    """Lazily ensure the bucket exists on first actual use."""
    global _bucket_ready
    if not _bucket_ready:
        _ensure_bucket_exists()
        _bucket_ready = True


def minio_upload_file(
    object_name: str,
    data: bytes,
    length: int,
    content_type: str = "application/octet-stream",
) -> str:
    """Upload a file to MinIO.

    Args:
        object_name: The object name (path) within the bucket.
        data: The file content as bytes.
        length: The length of the data in bytes.
        content_type: The MIME content type.

    Returns:
        The object name that was uploaded.
    """
    _ensure_bucket_lazy()
    data_stream = io.BytesIO(data)
    minio_client.put_object(
        bucket_name=settings.MINIO_BUCKET,
        object_name=object_name,
        data=data_stream,
        length=length,
        content_type=content_type,
    )
    return object_name


def minio_download_file(object_name: str) -> bytes:
    """Download a file from MinIO.

    Args:
        object_name: The object name within the bucket.

    Returns:
        The file content as bytes.

    Raises:
        S3Error: If the object does not exist or download fails.
    """
    response = minio_client.get_object(
        bucket_name=settings.MINIO_BUCKET,
        object_name=object_name,
    )
    try:
        return response.read()
    finally:
        response.close()
        response.release_conn()


def minio_generate_presigned_url(
    object_name: str, expiry_hours: int = 168
) -> str:
    """Generate a presigned download URL for an object.

    Args:
        object_name: The object name within the bucket.
        expiry_hours: Number of hours until the URL expires (default 168 = 7 days).

    Returns:
        A presigned URL string.
    """
    url = minio_client.presigned_get_object(
        bucket_name=settings.MINIO_BUCKET,
        object_name=object_name,
        expires=timedelta(hours=expiry_hours),
    )
    return url


def minio_file_exists(object_name: str) -> bool:
    """Check whether an object exists in MinIO.

    Args:
        object_name: The object name within the bucket.

    Returns:
        True if the object exists, False otherwise.
    """
    try:
        minio_client.stat_object(
            bucket_name=settings.MINIO_BUCKET,
            object_name=object_name,
        )
        return True
    except S3Error:
        return False



def minio_delete_object(object_name: str) -> None:
    """Delete an object from MinIO.

    Args:
        object_name: The object name within the bucket.

    Raises:
        S3Error: If deletion fails (e.g., connection error).
    """
    minio_client.remove_object(
        bucket_name=settings.MINIO_BUCKET,
        object_name=object_name,
    )
