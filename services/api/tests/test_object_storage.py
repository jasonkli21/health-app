from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch
from uuid import UUID

import pytest
from google.api_core.exceptions import GoogleAPICallError
from health_api.integrations.object_storage import (
    GCSObjectStorage,
    LocalObjectStorage,
    ObjectNotFound,
    ObjectStorageUnavailable,
    ObjectTooLarge,
)

OWNER_ID = UUID("00000000-0000-0000-0000-000000000111")
OTHER_OWNER_ID = UUID("00000000-0000-0000-0000-000000000222")


def test_local_storage_round_trip_is_owner_scoped_and_preserves_metadata(tmp_path: Path) -> None:
    storage = LocalObjectStorage(tmp_path / "objects", max_size_bytes=32)
    ref = storage.put(OWNER_ID, "Text/Plain", b"private synthetic content")

    stored = storage.get(OWNER_ID, ref.object_id)
    assert stored.data == b"private synthetic content"
    assert stored.ref == ref
    with pytest.raises(ObjectNotFound):
        storage.get(OTHER_OWNER_ID, ref.object_id)
    assert storage.delete(OTHER_OWNER_ID, ref.object_id) is False
    assert storage.delete(OWNER_ID, ref.object_id) is True
    assert storage.delete(OWNER_ID, ref.object_id) is False


def test_local_storage_rejects_traversal_size_and_unsafe_content_type(tmp_path: Path) -> None:
    storage = LocalObjectStorage(tmp_path / "objects", max_size_bytes=4)
    with pytest.raises(TypeError, match="UUID"):
        storage.get(OWNER_ID, "../../outside")  # type: ignore[arg-type]
    with pytest.raises(ObjectTooLarge):
        storage.put(OWNER_ID, "text/plain", b"12345")
    with pytest.raises(ValueError, match="media type"):
        storage.put(OWNER_ID, "text/plain\r\nX-Evil: yes", b"x")
    assert not (tmp_path / "outside").exists()


def test_local_storage_refuses_symlinked_owner_directory(tmp_path: Path) -> None:
    root = tmp_path / "objects"
    outside = tmp_path / "outside"
    outside.mkdir()
    owners = root / "owners"
    owner_dir = owners / OWNER_ID.hex
    owner_dir.mkdir(parents=True)
    (owner_dir / "objects").symlink_to(outside, target_is_directory=True)
    storage = LocalObjectStorage(root, max_size_bytes=128)

    with pytest.raises(ObjectStorageUnavailable):
        storage.put(OWNER_ID, "text/plain", b"must not escape")
    assert list(outside.iterdir()) == []


def test_local_storage_refuses_symlinked_parent_of_configured_root(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / "redirect").symlink_to(outside, target_is_directory=True)
    storage = LocalObjectStorage(tmp_path / "redirect" / "objects", max_size_bytes=128)

    with pytest.raises(ObjectStorageUnavailable):
        storage.put(OWNER_ID, "text/plain", b"must not escape configured root")
    assert list(outside.iterdir()) == []


def test_local_storage_rejects_symlinked_object_file(tmp_path: Path) -> None:
    storage = LocalObjectStorage(tmp_path / "objects", max_size_bytes=128)
    ref = storage.put(OWNER_ID, "text/plain", b"temporary")
    object_path = (
        tmp_path / "objects" / "owners" / OWNER_ID.hex / "objects" / f"{ref.object_id.hex}.blob"
    )
    target = tmp_path / "private-outside"
    target.write_bytes(b"sensitive unrelated file")
    object_path.unlink()
    object_path.symlink_to(target)

    with pytest.raises(ObjectStorageUnavailable):
        storage.get(OWNER_ID, ref.object_id)
    assert target.read_bytes() == b"sensitive unrelated file"


def test_local_storage_removes_partial_object_when_write_fails(tmp_path: Path) -> None:
    storage = LocalObjectStorage(tmp_path / "objects", max_size_bytes=128)
    with (
        patch(
            "health_api.integrations.object_storage.os.fsync",
            side_effect=OSError("synthetic disk failure"),
        ),
        pytest.raises(ObjectStorageUnavailable),
    ):
        storage.put(OWNER_ID, "text/plain", b"synthetic")
    object_directory = tmp_path / "objects" / "owners" / OWNER_ID.hex / "objects"
    assert list(object_directory.iterdir()) == []


class FakeNotFound(GoogleAPICallError):
    def __init__(self) -> None:
        super().__init__("missing")
        self.code = 404


class FakeBlob:
    def __init__(self, name: str, objects: dict[str, dict[str, Any]]) -> None:
        self.name = name
        self.objects = objects
        self.generation: int | None = None
        self.size: int | None = None
        self.content_type: str | None = None
        self.calls: list[dict[str, Any]] = []

    def upload_from_string(self, data: bytes, **kwargs: Any) -> None:
        self.calls.append(kwargs)
        if self.name in self.objects:
            raise RuntimeError("would overwrite existing generation")
        self.objects[self.name] = {
            "data": data,
            "content_type": kwargs["content_type"],
            "generation": 7,
        }

    def reload(self, **kwargs: Any) -> None:
        self.calls.append(kwargs)
        try:
            saved = self.objects[self.name]
        except KeyError as exc:
            raise FakeNotFound from exc
        self.size = len(saved["data"])
        self.generation = saved["generation"]
        self.content_type = saved["content_type"]

    def download_as_bytes(self, **kwargs: Any) -> bytes:
        self.calls.append(kwargs)
        assert kwargs["if_generation_match"] == self.generation
        return self.objects[self.name]["data"]

    def delete(self, **kwargs: Any) -> None:
        self.calls.append(kwargs)
        assert kwargs["if_generation_match"] == self.generation
        del self.objects[self.name]


class FakeBucket:
    def __init__(self) -> None:
        self.objects: dict[str, dict[str, Any]] = {}
        self.blobs: list[FakeBlob] = []

    def blob(self, name: str) -> FakeBlob:
        blob = FakeBlob(name, self.objects)
        self.blobs.append(blob)
        return blob


class FakeClient:
    def __init__(self) -> None:
        self.bucket_instance = FakeBucket()

    def bucket(self, _name: str) -> FakeBucket:
        return self.bucket_instance


def test_gcs_adapter_uses_owner_prefix_generation_preconditions_and_timeout() -> None:
    client = FakeClient()
    storage = GCSObjectStorage(
        "synthetic-private-bucket", max_size_bytes=32, client=client, timeout_seconds=3
    )
    ref = storage.put(OWNER_ID, "text/plain", b"synthetic cloud bytes")
    saved_name = next(iter(client.bucket_instance.objects))
    assert saved_name == f"owners/{OWNER_ID.hex}/objects/{ref.object_id.hex}.blob"
    put_kwargs = client.bucket_instance.blobs[0].calls[0]
    assert put_kwargs == {
        "content_type": "text/plain",
        "if_generation_match": 0,
        "timeout": 3,
        "retry": None,
    }

    stored = storage.get(OWNER_ID, ref.object_id)
    assert stored.data == b"synthetic cloud bytes"
    assert stored.ref == ref
    get_calls = client.bucket_instance.blobs[-1].calls
    assert all(call["timeout"] == 3 and call["retry"] is None for call in get_calls)
    assert get_calls[-1]["if_generation_match"] == 7

    assert storage.delete(OWNER_ID, ref.object_id) is True
    assert storage.delete(OWNER_ID, ref.object_id) is False
    with pytest.raises(ObjectNotFound):
        storage.get(OTHER_OWNER_ID, ref.object_id)


def test_gcs_outage_is_sanitized_and_payload_bound_is_checked() -> None:
    class FailingBlob(FakeBlob):
        def upload_from_string(self, data: bytes, **kwargs: Any) -> None:
            raise GoogleAPICallError("do-not-leak-this-payload")

    class FailingBucket(FakeBucket):
        def blob(self, name: str) -> FailingBlob:
            blob = FailingBlob(name, self.objects)
            self.blobs.append(blob)
            return blob

    class FailingClient(FakeClient):
        def __init__(self) -> None:
            self.bucket_instance = FailingBucket()

    storage = GCSObjectStorage("synthetic-private-bucket", max_size_bytes=4, client=FailingClient())
    with pytest.raises(ObjectTooLarge):
        storage.put(OWNER_ID, "text/plain", b"12345")
    with pytest.raises(ObjectStorageUnavailable) as raised:
        storage.put(OWNER_ID, "text/plain", b"x")
    assert "do-not-leak-this-payload" not in str(raised.value)
