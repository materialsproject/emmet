"""Remote upload support for calculation submission archives.

The control-plane service exposes an idempotent three-step protocol:

1. ``POST /submissions/{id}/upload-sessions`` with a snapshot manifest and the
   objects that require presigned upload URLs.
2. ``PUT`` each object to the returned URL using the returned headers.
3. ``POST /submissions/{id}/upload-sessions/{session_id}/complete`` with the
   uploaded object identifiers and checksums.

Calling the prepare endpoint again with the same ``Idempotency-Key`` refreshes
expired URLs and returns the same logical upload session.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Iterator
from uuid import UUID

import httpx

from emmet.archival.vasp.raw import RawArchive, raw_archive_hierarchy_from_files
from emmet.cli.state_manager import StateManager
from emmet.cli.submission import CalculationMetadata, SubmissionChangeSet
from emmet.cli.utils import EmmetCliError

DEFAULT_API_URL = "https://api.materialsproject.org"
UPLOAD_STATE_KEY = "submission_uploads"
ARCHIVE_CONTENT_TYPE = "application/x-hdf5"
MANIFEST_CONTENT_TYPE = "application/json"
PROGRESS_CHECKPOINT_INTERVAL = 10

logger = logging.getLogger("emmet")


@dataclass(frozen=True)
class _SessionParts:
    uploads: dict[str, dict[str, Any]]
    objects: dict[str, dict[str, Any]]
    completed_ids: set[str]
    completed_objects: dict[str, dict[str, Any]]


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _calculation_digest(calculation: CalculationMetadata) -> str:
    files = sorted(
        ({"name": file.name, "hash": file.hash} for file in calculation.files),
        key=lambda file: file["name"],
    )
    return hashlib.sha256(_canonical_json(files)).hexdigest()


def _file_chunks(path: Path, digest: Any) -> Iterator[bytes]:
    with path.open("rb") as file:
        while chunk := file.read(1024 * 1024):
            digest.update(chunk)
            yield chunk


def _is_unexpired(expires_at: str | None) -> bool:
    if not expires_at:
        return False
    try:
        expiry = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
    except ValueError:
        return False
    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)
    return expiry > datetime.now(timezone.utc)


class HttpSubmissionUploader:
    """Reusable uploader for service-provided presigned URLs.

    Call :meth:`close` when finished, or use the uploader as a context manager.
    Clients supplied by the caller remain owned by the caller and are not closed.
    """

    def __init__(
        self,
        state_manager: StateManager,
        token: str,
        api_url: str = DEFAULT_API_URL,
        client: httpx.Client | None = None,
    ) -> None:
        if not token:
            raise EmmetCliError(
                "EMMET_API_TOKEN must be set before pushing a submission."
            )
        self.state_manager = state_manager
        self.token = token
        self.api_url = api_url.rstrip("/")
        self.client = client or httpx.Client(timeout=60.0)
        self._owns_client = client is None

    @classmethod
    def from_environment(
        cls, state_manager: StateManager, client: httpx.Client | None = None
    ) -> HttpSubmissionUploader:
        """Create an uploader using the CLI's supported environment settings."""
        return cls(
            state_manager=state_manager,
            token=os.environ.get("EMMET_API_TOKEN", ""),
            api_url=os.environ.get("EMMET_API_URL", DEFAULT_API_URL),
            client=client,
        )

    def close(self) -> None:
        """Close the internally-created HTTP client, if any."""
        if self._owns_client and not self.client.is_closed:
            self.client.close()

    def __enter__(self) -> HttpSubmissionUploader:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def upload(self, submission_id: UUID, changes: SubmissionChangeSet) -> None:
        """Archive and upload a staged snapshot, then finalize it remotely."""
        with TemporaryDirectory(prefix="emmet-upload-") as directory:
            objects, manifest = self._build_objects(
                submission_id, changes, Path(directory)
            )
            snapshot_id = manifest["snapshot_id"]
            session = self._get_or_prepare_session(
                submission_id, snapshot_id, manifest, objects
            )
            session_parts = self._parse_session(
                session, "Upload session contains invalid details."
            )
            uploads = session_parts.uploads
            completed = session_parts.completed_ids
            session_objects = session_parts.objects
            pending_checkpoint = 0

            try:
                for object_info in objects:
                    object_id = object_info["object_id"]
                    if object_id in completed:
                        continue
                    upload = uploads.get(object_id)
                    if upload is None:
                        raise EmmetCliError(
                            f"Upload service did not return a URL for object {object_id}."
                        )
                    self._put_object(object_info, upload)
                    completed.add(object_id)
                    session_objects[object_id] = self._object_metadata(object_info)
                    pending_checkpoint += 1
                    if pending_checkpoint >= PROGRESS_CHECKPOINT_INTERVAL:
                        self._checkpoint_session(
                            submission_id, session, completed, session_objects
                        )
                        pending_checkpoint = 0
            except Exception:
                if pending_checkpoint:
                    with suppress(Exception):
                        self._checkpoint_session(
                            submission_id, session, completed, session_objects
                        )
                raise

            if pending_checkpoint:
                self._checkpoint_session(
                    submission_id, session, completed, session_objects
                )
            self._finalize_session(submission_id, session)
            self._clear_session(submission_id)

    def _build_objects(
        self,
        submission_id: UUID,
        changes: SubmissionChangeSet,
        directory: Path,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        change_by_id = {change.calculation_id: change for change in changes.changes}
        calculation_entries = []
        archive_specs = []

        for _, calculation in sorted(
            changes.current_calculations, key=lambda item: str(item[1].id)
        ):
            digest = _calculation_digest(calculation)
            object_id = f"calculations/{calculation.id}/{digest}.h5"
            change = change_by_id.get(calculation.id)
            calculation_entries.append(
                {
                    "calculation_id": str(calculation.id),
                    "archive_object_id": object_id,
                    "content_digest": digest,
                    "change": change.status if change else "unchanged",
                    "added_files": change.added_files if change else [],
                    "changed_files": change.changed_files if change else [],
                    "removed_files": change.removed_files if change else [],
                }
            )
            if change is not None:
                archive_specs.append((calculation, object_id))

        manifest_body = {
            "schema_version": 1,
            "submission_id": str(submission_id),
            "calculations": calculation_entries,
            "removed_calculations": [
                {
                    "calculation_id": str(change.calculation_id),
                    "removed_files": change.removed_files,
                }
                for change in changes.changes
                if change.status == "removed"
            ],
        }
        snapshot_id = hashlib.sha256(_canonical_json(manifest_body)).hexdigest()
        manifest = {**manifest_body, "snapshot_id": snapshot_id}

        objects = []
        for calculation, object_id in archive_specs:
            archive_path = directory / f"{calculation.id}.h5"
            objects.append(
                self._object_info(
                    object_id,
                    archive_path,
                    ARCHIVE_CONTENT_TYPE,
                    calculation=calculation,
                    archive_metadata={
                        "submission_id": str(submission_id),
                        "calculation_id": str(calculation.id),
                        "snapshot_id": snapshot_id,
                    },
                )
            )

        manifest_path = directory / "manifest.json"
        objects.append(
            self._object_info(
                f"manifests/{snapshot_id}.json",
                manifest_path,
                MANIFEST_CONTENT_TYPE,
                content=_canonical_json(manifest),
            )
        )
        return objects, manifest

    @staticmethod
    def _object_info(
        object_id: str,
        path: Path,
        content_type: str,
        **build_args: Any,
    ) -> dict[str, Any]:
        object_info = {
            "object_id": object_id,
            "path": path,
            "content_type": content_type,
            **{f"_{key}": value for key, value in build_args.items()},
        }
        if path.exists():
            object_info["size"] = path.stat().st_size
        return object_info

    @staticmethod
    def _object_metadata(object_info: dict[str, Any]) -> dict[str, Any]:
        """Return persistable metadata describing the bytes prepared for upload."""
        return {
            key: value
            for key, value in object_info.items()
            if key != "path" and not key.startswith("_")
        }

    @classmethod
    def _parse_session(cls, session: dict[str, Any], error: str) -> _SessionParts:
        def items_by_id(key: str, require_checksum: bool = False):
            items = session.get(key, [])
            if not isinstance(items, list):
                raise EmmetCliError(error)
            parsed = {}
            for item in items:
                if (
                    not isinstance(item, dict)
                    or not isinstance(item.get("object_id"), str)
                    or (require_checksum and not cls._has_checksum(item))
                ):
                    raise EmmetCliError(error)
                parsed[item["object_id"]] = item
            return parsed

        completed_ids = session.get("completed_object_ids", [])
        if not isinstance(completed_ids, list) or not all(
            isinstance(object_id, str) for object_id in completed_ids
        ):
            raise EmmetCliError(error)
        return _SessionParts(
            uploads=items_by_id("uploads"),
            objects=items_by_id("objects"),
            completed_ids=set(completed_ids),
            completed_objects=items_by_id("completed_objects", require_checksum=True),
        )

    @staticmethod
    def _has_checksum(item: dict[str, Any]) -> bool:
        return isinstance(item.get("sha256"), str)

    @staticmethod
    def _objects_have_checksums(
        completed: set[str], objects: dict[str, dict[str, Any]]
    ) -> bool:
        return all(
            object_id in objects
            and HttpSubmissionUploader._has_checksum(objects[object_id])
            for object_id in completed
        )

    @classmethod
    def _resolve_object_metadata(
        cls,
        base: dict[str, Any],
        service_completed: set[str],
        service_objects: dict[str, dict[str, Any]],
        previous_objects: dict[str, dict[str, Any]],
    ) -> tuple[dict[str, Any], bool]:
        object_id = base["object_id"]
        service_metadata = service_objects.get(object_id)
        if service_metadata is not None:
            return {**base, **service_metadata}, True
        previous_metadata = previous_objects.get(object_id)
        if (
            object_id in service_completed
            and previous_metadata is not None
            and cls._has_checksum(previous_metadata)
        ):
            return {**base, **previous_metadata}, True
        return base, False

    def _get_or_prepare_session(
        self,
        submission_id: UUID,
        snapshot_id: str,
        manifest: dict[str, Any],
        objects: list[dict[str, Any]],
    ) -> dict[str, Any]:
        previous_session = self._load_session(submission_id)
        required_ids = {item["object_id"] for item in objects}
        try:
            previous_parts = self._parse_session(
                previous_session, "Cached upload session is invalid."
            )
        except EmmetCliError:
            previous_session = {}
            previous_parts = _SessionParts({}, {}, set(), {})
        if (
            previous_session.get("snapshot_id") == snapshot_id
            and _is_unexpired(previous_session.get("expires_at"))
            and required_ids
            <= previous_parts.uploads.keys() | previous_parts.completed_ids
            and required_ids <= previous_parts.objects.keys()
            and self._objects_have_checksums(
                previous_parts.completed_ids, previous_parts.objects
            )
        ):
            return previous_session

        payload = {
            "snapshot_id": snapshot_id,
            "manifest": manifest,
            "objects": [self._object_metadata(item) for item in objects],
        }
        response = self._control_request(
            "POST",
            f"/submissions/{submission_id}/upload-sessions",
            json=payload,
            headers={"Idempotency-Key": snapshot_id},
            action="Preparing upload session",
        )
        try:
            session = response.json()
            if not isinstance(session, dict) or not isinstance(
                session["session_id"], str
            ):
                raise TypeError
            service_parts = self._parse_session(
                session, "Upload service returned an invalid prepare response."
            )
        except (KeyError, TypeError, ValueError, EmmetCliError):
            raise EmmetCliError(
                "Upload service returned an invalid prepare response."
            ) from None
        session["snapshot_id"] = snapshot_id
        if previous_session.get("snapshot_id") != snapshot_id:
            previous_parts = _SessionParts({}, {}, set(), {})
        service_completed = (
            service_parts.completed_ids | service_parts.completed_objects.keys()
        )
        completed = set()
        resolved_objects = []
        for item in objects:
            metadata, is_completed = self._resolve_object_metadata(
                self._object_metadata(item),
                service_completed,
                service_parts.completed_objects,
                previous_parts.objects,
            )
            resolved_objects.append(metadata)
            if is_completed:
                completed.add(item["object_id"])
        session["completed_object_ids"] = list(completed)
        session["objects"] = resolved_objects
        try:
            self._save_session(submission_id, session)
        except Exception:
            raise EmmetCliError(
                "Upload session was prepared remotely but could not be saved locally. "
                "Retry the push to resume or refresh the session."
            ) from None
        return session

    @staticmethod
    def _materialize_object(object_info: dict[str, Any]) -> None:
        path = object_info["path"]
        if not path.exists():
            calculation = object_info.get("_calculation")
            if calculation is not None:
                RawArchive(
                    file_paths=raw_archive_hierarchy_from_files(calculation.files)
                ).to_archive(path, metadata=object_info["_archive_metadata"])
            elif "_content" in object_info:
                path.write_bytes(object_info["_content"])
        object_info["size"] = path.stat().st_size

    def _put_object(self, object_info: dict[str, Any], upload: dict[str, Any]) -> None:
        digest = hashlib.sha256()
        try:
            self._materialize_object(object_info)
            response = self.client.put(
                upload["url"],
                headers=upload.get("headers", {}),
                content=_file_chunks(object_info["path"], digest),
            )
            response.raise_for_status()
            object_info["sha256"] = digest.hexdigest()
        except (KeyError, TypeError) as exc:
            raise EmmetCliError(
                f"Upload service returned invalid details for object {object_info['object_id']}."
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise EmmetCliError(
                f"Uploading object {object_info['object_id']} failed with HTTP "
                f"{exc.response.status_code}."
            ) from None
        except httpx.RequestError:
            raise EmmetCliError(
                f"Uploading object {object_info['object_id']} failed due to a network error."
            ) from None
        except OSError:
            raise EmmetCliError(
                f"Reading object {object_info['object_id']} failed during upload. "
                "Verify the local files are accessible and retry the push."
            ) from None

    def _finalize_session(
        self,
        submission_id: UUID,
        session: dict[str, Any],
    ) -> None:
        try:
            payload = {
                "snapshot_id": session["snapshot_id"],
                "objects": [
                    {"object_id": item["object_id"], "sha256": item["sha256"]}
                    for item in session["objects"]
                ],
            }
            session_id = session["session_id"]
        except (KeyError, TypeError):
            raise EmmetCliError(
                "Upload session is missing object checksums required for finalization. "
                "Retry the push to reconcile remote upload progress."
            ) from None
        self._control_request(
            "POST",
            f"/submissions/{submission_id}/upload-sessions/{session_id}/complete",
            json=payload,
            headers={"Idempotency-Key": session["snapshot_id"]},
            action="Finalizing upload session",
        )

    def _control_request(
        self,
        method: str,
        path: str,
        *,
        action: str,
        json: dict[str, Any],
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        request_headers = {"Authorization": f"Bearer {self.token}"}
        request_headers.update(headers or {})
        try:
            response = self.client.request(
                method,
                f"{self.api_url}{path}",
                headers=request_headers,
                json=json,
            )
            response.raise_for_status()
            return response
        except httpx.HTTPStatusError as exc:
            raise EmmetCliError(
                f"{action} failed with HTTP {exc.response.status_code}."
            ) from None
        except httpx.RequestError:
            raise EmmetCliError(f"{action} failed due to a network error.") from None

    def _load_session(self, submission_id: UUID) -> dict[str, Any]:
        sessions = self.state_manager.get(UPLOAD_STATE_KEY, {})
        session = sessions.get(str(submission_id), {})
        return session if isinstance(session, dict) else {}

    def _save_session(self, submission_id: UUID, session: dict[str, Any]) -> None:
        def save(sessions: Any) -> dict[str, Any]:
            updated = dict(sessions or {})
            updated[str(submission_id)] = session
            return updated

        self.state_manager.update(UPLOAD_STATE_KEY, save)

    def _checkpoint_session(
        self,
        submission_id: UUID,
        session: dict[str, Any],
        completed: set[str],
        session_objects: dict[str, dict[str, Any]],
    ) -> None:
        session["completed_object_ids"] = list(completed)
        session["objects"] = list(session_objects.values())
        try:
            self._save_session(submission_id, session)
        except Exception:
            raise EmmetCliError(
                "Remote upload progress could not be saved locally. Retry the push; "
                "expired URLs will be refreshed and completed objects reconciled."
            ) from None

    def _clear_session(self, submission_id: UUID) -> None:
        def clear(sessions: Any) -> dict[str, Any]:
            updated = dict(sessions or {})
            updated.pop(str(submission_id), None)
            return updated

        try:
            self.state_manager.update(UPLOAD_STATE_KEY, clear)
        except Exception:
            logger.warning(
                "Remote upload completed, but its local retry state could not be "
                "cleared. A later retry may safely finalize the same snapshot again."
            )
