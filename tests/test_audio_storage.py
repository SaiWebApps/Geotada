"""Unit tests for audio storage providers."""

from __future__ import annotations

import pytest

from src.audio.storage import (
    LocalStorageProvider,
    StorageError,
    StorageProvider,
    get_storage,
)


@pytest.fixture
def local_storage(tmp_path, monkeypatch):
    monkeypatch.setenv("AUDIO_STORAGE_PATH", str(tmp_path))
    return LocalStorageProvider()


class TestLocalStorage:
    def test_implements_protocol(self, local_storage):
        assert isinstance(local_storage, StorageProvider)

    def test_name(self, local_storage):
        assert local_storage.name == "local"

    def test_upload_and_exists(self, local_storage):
        url = local_storage.upload(b"audio data", "test.mp3")
        assert "/api/v1/audio/files/test.mp3" in url
        assert local_storage.exists("test.mp3")

    def test_upload_creates_subdirectories(self, local_storage):
        local_storage.upload(b"data", "beats/poi/test.mp3")
        assert local_storage.exists("beats/poi/test.mp3")

    def test_delete(self, local_storage):
        local_storage.upload(b"data", "to_delete.mp3")
        assert local_storage.delete("to_delete.mp3")
        assert not local_storage.exists("to_delete.mp3")

    def test_delete_nonexistent(self, local_storage):
        assert not local_storage.delete("nonexistent.mp3")

    def test_exists_false_for_missing(self, local_storage):
        assert not local_storage.exists("nope.mp3")

    def test_readback(self, local_storage):
        local_storage.upload(b"exact bytes", "readback.mp3")
        data = (local_storage.base_path / "readback.mp3").read_bytes()
        assert data == b"exact bytes"


class TestGetStorage:
    def test_default_is_local(self, tmp_path, monkeypatch):
        monkeypatch.delenv("AUDIO_STORAGE", raising=False)
        monkeypatch.setenv("AUDIO_STORAGE_PATH", str(tmp_path))
        s = get_storage()
        assert s.name == "local"

    def test_explicit_local(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AUDIO_STORAGE_PATH", str(tmp_path))
        s = get_storage("local")
        assert s.name == "local"

    def test_s3_without_bucket_raises(self, monkeypatch):
        monkeypatch.delenv("AWS_S3_BUCKET", raising=False)
        with pytest.raises(StorageError, match="AWS_S3_BUCKET not set"):
            get_storage("s3")

    def test_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown storage provider"):
            get_storage("unknown")
