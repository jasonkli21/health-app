"""Private, bounded object-storage adapters for local development and GCS."""

from __future__ import annotations

import errno
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol
from uuid import UUID, uuid4

from google.api_core.exceptions import GoogleAPICallError
from google.auth.exceptions import GoogleAuthError

if TYPE_CHECKING:
    from health_api.config.settings import Settings


class ObjectStorageError(Exception):
    """Sanitized storage failure safe to translate at an API boundary."""


class ObjectNotFound(ObjectStorageError):
    """An object is missing from this owner's namespace."""


class ObjectTooLarge(ObjectStorageError):
    """An object exceeds the configured transfer bound."""


class ObjectStorageUnavailable(ObjectStorageError):
    """The adapter or its backing service is unavailable."""


class ObjectCleanupPending(ObjectStorageError):
    """A bounded owner-prefix cleanup batch completed and more work remains."""


@dataclass(frozen=True)
class StoredObjectRef:
    object_id: UUID
    content_type: str
    size_bytes: int


@dataclass(frozen=True)
class StoredObject:
    ref: StoredObjectRef
    data: bytes


class ObjectStorage(Protocol):
    def put(self, owner_id: UUID, content_type: str, data: bytes) -> StoredObjectRef: ...

    def get(self, owner_id: UUID, object_id: UUID) -> StoredObject: ...

    def delete(self, owner_id: UUID, object_id: UUID) -> bool: ...

    def delete_owner(self, owner_id: UUID) -> None: ...


_CONTENT_TYPE = re.compile(r"[A-Za-z0-9!#$&^_.+-]+/[A-Za-z0-9!#$&^_.+-]+\Z")
_LOCAL_HEADER = b"PHO1"
_DIRECTORY_FLAGS = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
_FILE_FLAGS = os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)


def _validated_content_type(content_type: str) -> str:
    if len(content_type) > 128 or not _CONTENT_TYPE.fullmatch(content_type):
        raise ValueError("content_type must be a simple media type")
    return content_type.lower()


def _object_name(object_id: UUID) -> str:
    if not isinstance(object_id, UUID):
        raise TypeError("object_id must be a UUID")
    return f"{object_id.hex}.blob"


def _namespace(owner_id: UUID, object_id: UUID) -> str:
    if not isinstance(owner_id, UUID):
        raise TypeError("owner_id must be a UUID")
    return f"owners/{owner_id.hex}/objects/{_object_name(object_id)}"


class LocalObjectStorage:
    """Local adapter using dirfd-relative, no-follow operations under one root."""

    def __init__(self, root: Path, *, max_size_bytes: int) -> None:
        self.root = Path(os.path.abspath(root))
        self.max_size_bytes = max_size_bytes

    def put(self, owner_id: UUID, content_type: str, data: bytes) -> StoredObjectRef:
        normalized_type = _validated_content_type(content_type)
        if len(data) > self.max_size_bytes:
            raise ObjectTooLarge
        object_id = uuid4()
        name = _object_name(object_id)
        objects_fd = self._open_owner_objects(owner_id, create=True)
        created = False
        try:
            fd = os.open(
                name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | _FILE_FLAGS,
                0o600,
                dir_fd=objects_fd,
            )
            created = True
            with os.fdopen(fd, "wb", closefd=True) as stream:
                media_type = normalized_type.encode("ascii")
                stream.write(_LOCAL_HEADER + bytes([len(media_type)]) + media_type)
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            return StoredObjectRef(object_id, normalized_type, len(data))
        except ObjectStorageError:
            if created:
                self._unlink_if_present(objects_fd, name)
            raise
        except OSError:
            if created:
                self._unlink_if_present(objects_fd, name)
            raise ObjectStorageUnavailable from None
        finally:
            os.close(objects_fd)

    def get(self, owner_id: UUID, object_id: UUID) -> StoredObject:
        name = _object_name(object_id)
        objects_fd = self._open_owner_objects(owner_id, create=False)
        try:
            try:
                fd = os.open(name, os.O_RDONLY | _FILE_FLAGS, dir_fd=objects_fd)
            except FileNotFoundError:
                raise ObjectNotFound from None
            with os.fdopen(fd, "rb", closefd=True) as stream:
                metadata = os.fstat(stream.fileno())
                if not stat.S_ISREG(metadata.st_mode):
                    raise ObjectStorageUnavailable
                if metadata.st_size > self.max_size_bytes + 133:
                    raise ObjectTooLarge
                header = stream.read(len(_LOCAL_HEADER) + 1)
                if len(header) != len(_LOCAL_HEADER) + 1 or header[:4] != _LOCAL_HEADER:
                    raise ObjectStorageUnavailable
                media_length = header[4]
                media_type = stream.read(media_length).decode("ascii")
                normalized_type = _validated_content_type(media_type)
                data = stream.read(self.max_size_bytes + 1)
                if len(data) > self.max_size_bytes:
                    raise ObjectTooLarge
            return StoredObject(StoredObjectRef(object_id, normalized_type, len(data)), data)
        except ObjectStorageError:
            raise
        except (UnicodeError, ValueError):
            raise ObjectStorageUnavailable from None
        except OSError as exc:
            if exc.errno == errno.ELOOP:
                raise ObjectStorageUnavailable from None
            raise ObjectStorageUnavailable from None
        finally:
            os.close(objects_fd)

    def delete(self, owner_id: UUID, object_id: UUID) -> bool:
        name = _object_name(object_id)
        try:
            objects_fd = self._open_owner_objects(owner_id, create=False)
        except ObjectNotFound:
            return False
        try:
            try:
                os.unlink(name, dir_fd=objects_fd)
                return True
            except FileNotFoundError:
                return False
            except OSError as exc:
                if exc.errno == errno.ELOOP:
                    raise ObjectStorageUnavailable from None
                raise ObjectStorageUnavailable from None
        finally:
            os.close(objects_fd)

    def delete_owner(self, owner_id: UUID) -> None:
        """Delete at most 1,000 opaque objects; retries safely finish larger namespaces."""
        try:
            objects_fd = self._open_owner_objects(owner_id, create=False)
        except ObjectNotFound:
            return
        try:
            names: list[str] = []
            more_objects = False
            with os.scandir(objects_fd) as entries:
                for entry in entries:
                    if not re.fullmatch(r"[0-9a-f]{32}\.blob", entry.name):
                        raise ObjectStorageUnavailable
                    if len(names) == 1000:
                        more_objects = True
                        break
                    names.append(entry.name)
            batch = names
            for name in batch:
                try:
                    os.unlink(name, dir_fd=objects_fd)
                except FileNotFoundError:
                    continue
                except OSError:
                    raise ObjectStorageUnavailable from None
            if more_objects:
                raise ObjectCleanupPending
        except OSError:
            raise ObjectStorageUnavailable from None
        finally:
            os.close(objects_fd)

    def _open_owner_objects(self, owner_id: UUID, *, create: bool) -> int:
        if not isinstance(owner_id, UUID):
            raise TypeError("owner_id must be a UUID")
        root_fd = self._open_root_directory(create=create)

        owners_fd: int | None = None
        owner_fd: int | None = None
        try:
            owners_fd = self._open_directory(root_fd, "owners", create=create)
            owner_fd = self._open_directory(owners_fd, owner_id.hex, create=create)
            return self._open_directory(owner_fd, "objects", create=create)
        except OSError as exc:
            if not create and exc.errno == errno.ENOENT:
                raise ObjectNotFound from None
            raise ObjectStorageUnavailable from None
        finally:
            if owner_fd is not None:
                os.close(owner_fd)
            if owners_fd is not None:
                os.close(owners_fd)
            os.close(root_fd)

    @staticmethod
    def _open_directory(parent_fd: int, name: str, *, create: bool) -> int:
        if create:
            try:
                os.mkdir(name, mode=0o700, dir_fd=parent_fd)
            except FileExistsError:
                pass
        return os.open(name, _DIRECTORY_FLAGS, dir_fd=parent_fd)

    def _open_root_directory(self, *, create: bool) -> int:
        """Walk the configured absolute root without following any symlink."""
        current_fd = os.open("/", _DIRECTORY_FLAGS)
        try:
            for component in self.root.parts[1:]:
                try:
                    next_fd = self._open_directory(current_fd, component, create=create)
                except OSError as exc:
                    if not create and exc.errno == errno.ENOENT:
                        raise ObjectNotFound from None
                    raise ObjectStorageUnavailable from None
                os.close(current_fd)
                current_fd = next_fd
            return current_fd
        except BaseException:
            os.close(current_fd)
            raise

    @staticmethod
    def _unlink_if_present(parent_fd: int, name: str) -> None:
        try:
            os.unlink(name, dir_fd=parent_fd)
        except OSError:
            pass


class GCSObjectStorage:
    """GCS adapter using application default credentials and bounded operations."""

    # Leave one configured call timeout for listing, then keep the worst-case
    # sequential cleanup step below the 300-second Cloud Run request ceiling.
    _OWNER_CLEANUP_REQUEST_BUDGET_SECONDS = 240

    def __init__(
        self,
        bucket_name: str,
        *,
        max_size_bytes: int,
        project_id: str | None = None,
        client: Any | None = None,
        timeout_seconds: int = 10,
    ) -> None:
        if client is None:
            try:
                # google-cloud-storage currently ships without PEP 561 metadata.
                from google.cloud import storage  # type: ignore[import-untyped]

                client = storage.Client(project=project_id)
            except (ImportError, GoogleAPICallError, GoogleAuthError, ValueError, TimeoutError):
                raise ObjectStorageUnavailable from None
        self._bucket = client.bucket(bucket_name)
        self.max_size_bytes = max_size_bytes
        self.timeout_seconds = timeout_seconds

    def put(self, owner_id: UUID, content_type: str, data: bytes) -> StoredObjectRef:
        normalized_type = _validated_content_type(content_type)
        if len(data) > self.max_size_bytes:
            raise ObjectTooLarge
        object_id = uuid4()
        blob = self._bucket.blob(_namespace(owner_id, object_id))
        try:
            blob.upload_from_string(
                data,
                content_type=normalized_type,
                if_generation_match=0,
                timeout=self.timeout_seconds,
                retry=None,
            )
        except (GoogleAPICallError, GoogleAuthError, OSError, TimeoutError, ValueError):
            raise ObjectStorageUnavailable from None
        return StoredObjectRef(object_id, normalized_type, len(data))

    def get(self, owner_id: UUID, object_id: UUID) -> StoredObject:
        blob = self._bucket.blob(_namespace(owner_id, object_id))
        try:
            blob.reload(timeout=self.timeout_seconds, retry=None)
            size = int(blob.size)
            generation = int(blob.generation)
            if size > self.max_size_bytes:
                raise ObjectTooLarge
            data = blob.download_as_bytes(
                if_generation_match=generation,
                timeout=self.timeout_seconds,
                retry=None,
            )
        except ObjectTooLarge:
            raise
        except (
            GoogleAPICallError,
            GoogleAuthError,
            OSError,
            TimeoutError,
            TypeError,
            ValueError,
        ) as exc:
            if _looks_like_not_found(exc):
                raise ObjectNotFound from None
            raise ObjectStorageUnavailable from None
        if len(data) > self.max_size_bytes:
            raise ObjectTooLarge
        try:
            content_type = _validated_content_type(blob.content_type or "application/octet-stream")
        except ValueError:
            raise ObjectStorageUnavailable from None
        return StoredObject(StoredObjectRef(object_id, content_type, len(data)), data)

    def delete(self, owner_id: UUID, object_id: UUID) -> bool:
        blob = self._bucket.blob(_namespace(owner_id, object_id))
        try:
            blob.reload(timeout=self.timeout_seconds, retry=None)
            blob.delete(
                if_generation_match=int(blob.generation),
                timeout=self.timeout_seconds,
                retry=None,
            )
            return True
        except (
            GoogleAPICallError,
            GoogleAuthError,
            OSError,
            TimeoutError,
            TypeError,
            ValueError,
        ) as exc:
            if _looks_like_not_found(exc):
                return False
            raise ObjectStorageUnavailable from None

    def delete_owner(self, owner_id: UUID) -> None:
        """Delete a time-bounded prefix batch with generation preconditions."""
        prefix = f"owners/{owner_id.hex}/objects/"
        batch_size = max(
            1,
            min(
                1000,
                self._OWNER_CLEANUP_REQUEST_BUDGET_SECONDS // self.timeout_seconds - 1,
            ),
        )
        try:
            blobs = list(
                self._bucket.list_blobs(
                    prefix=prefix,
                    max_results=batch_size + 1,
                    versions=True,
                    timeout=self.timeout_seconds,
                    retry=None,
                )
            )
            batch = blobs[:batch_size]
            for blob in batch:
                name = getattr(blob, "name", "")
                if not name.startswith(prefix) or not re.fullmatch(
                    r"owners/[0-9a-f]{32}/objects/[0-9a-f]{32}\.blob", name
                ):
                    raise ObjectStorageUnavailable
                generation = int(blob.generation)
                try:
                    blob.delete(
                        if_generation_match=generation,
                        timeout=self.timeout_seconds,
                        retry=None,
                    )
                except (
                    GoogleAPICallError,
                    GoogleAuthError,
                    OSError,
                    TimeoutError,
                    TypeError,
                    ValueError,
                ) as exc:
                    if not _looks_like_not_found(exc):
                        raise ObjectStorageUnavailable from None
        except ObjectStorageUnavailable:
            raise
        except (
            GoogleAPICallError,
            GoogleAuthError,
            OSError,
            TimeoutError,
            TypeError,
            ValueError,
        ):
            raise ObjectStorageUnavailable from None
        if len(blobs) > len(batch):
            raise ObjectCleanupPending


def create_object_storage(settings: Settings) -> ObjectStorage:
    if settings.object_storage_backend == "gcs":
        if not settings.gcs_bucket:
            raise ObjectStorageUnavailable
        return GCSObjectStorage(
            settings.gcs_bucket,
            project_id=settings.gcp_project_id,
            max_size_bytes=settings.max_object_size_bytes,
            timeout_seconds=settings.object_storage_timeout_seconds,
        )
    return LocalObjectStorage(
        settings.local_object_storage_root,
        max_size_bytes=settings.max_object_size_bytes,
    )


def _looks_like_not_found(exc: Exception) -> bool:
    return type(exc).__name__ == "NotFound" or getattr(exc, "code", None) == 404
