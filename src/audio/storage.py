"""Audio storage — upload generated audio and return accessible URLs.

Two implementations:
- LocalStorageProvider: saves to a local directory (development)
- S3StorageProvider: uploads to AWS S3 (production, requires boto3)

Usage:
    storage = get_storage()
    url = storage.upload(audio_bytes, key="eiffel_tower.mp3")
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Protocol, runtime_checkable


class StorageError(Exception):
    """Raised when audio storage fails."""


@runtime_checkable
class StorageProvider(Protocol):
    """Interface for audio file storage backends."""

    @property
    def name(self) -> str: ...

    def upload(self, data: bytes, key: str) -> str:
        """Upload audio bytes and return a URL/path to access them."""
        ...

    def exists(self, key: str) -> bool:
        """Check if a file exists at the given key."""
        ...

    def delete(self, key: str) -> bool:
        """Delete a file. Returns True if it existed."""
        ...


class LocalStorageProvider:
    """Store audio files on the local filesystem.

    Files are saved under AUDIO_STORAGE_PATH (default: ./audio_store/).
    URLs are returned as /api/v1/audio/files/{key} for serving via the API.
    """

    def __init__(self) -> None:
        self._base = Path(
            os.getenv("AUDIO_STORAGE_PATH", "audio_store")
        ).resolve()
        self._base.mkdir(parents=True, exist_ok=True)

    @property
    def name(self) -> str:
        return "local"

    @property
    def base_path(self) -> Path:
        return self._base

    def upload(self, data: bytes, key: str) -> str:
        # Reject null bytes (could bypass path checks on some OSes)
        if "\x00" in key:
            raise StorageError("Invalid storage key: null bytes not allowed")

        filepath = self._base / key
        # Prevent path traversal — resolved path must stay under base
        resolved_base = self._base.resolve()
        resolved_path = filepath.resolve()
        if not str(resolved_path).startswith(str(resolved_base) + os.sep) and resolved_path != resolved_base:
            raise StorageError("Invalid storage key: path traversal detected")

        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_bytes(data)
        return f"/api/v1/audio/files/{key}"

    def exists(self, key: str) -> bool:
        return (self._base / key).exists()

    def delete(self, key: str) -> bool:
        filepath = self._base / key
        if filepath.exists():
            filepath.unlink()
            return True
        return False


class S3StorageProvider:
    """Upload audio files to AWS S3.

    Requires boto3 and AWS credentials (via env vars or IAM role).
    Set AWS_S3_BUCKET env var.
    """

    def __init__(self) -> None:
        self._bucket = os.getenv("AWS_S3_BUCKET")
        if not self._bucket:
            raise StorageError("AWS_S3_BUCKET not set")
        try:
            import boto3
            self._s3 = boto3.client("s3")
        except ImportError:
            raise StorageError("boto3 not installed — run: pip install boto3")

    @property
    def name(self) -> str:
        return "s3"

    def upload(self, data: bytes, key: str) -> str:
        self._s3.put_object(
            Bucket=self._bucket,
            Key=key,
            Body=data,
            ContentType="audio/mpeg",
        )
        return f"s3://{self._bucket}/{key}"

    def exists(self, key: str) -> bool:
        try:
            self._s3.head_object(Bucket=self._bucket, Key=key)
            return True
        except self._s3.exceptions.ClientError:
            return False

    def delete(self, key: str) -> bool:
        try:
            self._s3.delete_object(Bucket=self._bucket, Key=key)
            return True
        except Exception:
            return False


def get_storage(name: str | None = None) -> StorageProvider:
    """Return a storage provider by name.

    Falls back to AUDIO_STORAGE env var, then to 'local'.
    """
    storage_name = name or os.getenv("AUDIO_STORAGE", "local")
    if storage_name == "s3":
        return S3StorageProvider()
    if storage_name == "local":
        return LocalStorageProvider()
    raise ValueError(f"Unknown storage provider: '{storage_name}'. Available: local, s3")
