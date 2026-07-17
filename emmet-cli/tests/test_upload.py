import hashlib
import json
import traceback
import builtins
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest

import emmet.cli.upload as upload_module
from emmet.cli.state_manager import StateManager
from emmet.cli.submission import CalculationMetadata, Submission
from emmet.cli.upload import HttpSubmissionUploader, UPLOAD_STATE_KEY
from emmet.cli.utils import EmmetCliError
from emmet.core.vasp.utils import CalculationLocator, FileMetadata


def _submission_with_raw_files(tmp_path):
    files = []
    for name in ("INCAR", "POSCAR"):
        path = tmp_path / name
        path.write_text(f"contents of {name}")
        metadata = FileMetadata(name=name, path=path)
        metadata.compute_hash()
        files.append(metadata)
    calculation = CalculationMetadata(files=files, calc_valid=True)
    locator = CalculationLocator(path=tmp_path, modifier="standard")
    return Submission(calculations=[(locator, calculation)])


class UploadService:
    def __init__(self, fail_object=None, fail_finalize=False):
        self.fail_object = fail_object
        self.fail_finalize = fail_finalize
        self.prepare_requests = []
        self.prepare_headers = []
        self.put_attempts = []
        self.puts = {}
        self.finalize_requests = []

    def __call__(self, request):
        content = request.read()
        if request.url.host == "uploads.test":
            object_id = request.headers["x-object-id"]
            self.put_attempts.append(object_id)
            if object_id == self.fail_object or (
                self.fail_object == "manifest" and object_id.endswith(".json")
            ):
                return httpx.Response(500)
            self.puts[object_id] = content
            return httpx.Response(200)

        payload = json.loads(content)
        if request.url.path.endswith("/complete"):
            self.finalize_requests.append(payload)
            if self.fail_finalize:
                self.fail_finalize = False
                return httpx.Response(500)
            for item in payload["objects"]:
                uploaded_sha256 = hashlib.sha256(
                    self.puts[item["object_id"]]
                ).hexdigest()
                if item["sha256"] != uploaded_sha256:
                    return httpx.Response(422)
            return httpx.Response(200, json={"status": "complete"})

        self.prepare_requests.append(payload)
        self.prepare_headers.append(request.headers)
        uploads = [
            {
                "object_id": item["object_id"],
                "url": f"https://uploads.test/{index}",
                "headers": {"x-object-id": item["object_id"]},
            }
            for index, item in enumerate(payload["objects"])
        ]
        return httpx.Response(
            200,
            json={
                "session_id": "session-1",
                "expires_at": (
                    datetime.now(timezone.utc) + timedelta(hours=1)
                ).isoformat(),
                "uploads": uploads,
                "completed_object_ids": list(self.puts),
            },
        )


def _uploader(state_manager, service):
    client = httpx.Client(transport=httpx.MockTransport(service))
    return HttpSubmissionUploader(
        state_manager=state_manager,
        token="secret-token",
        api_url="https://api.test",
        client=client,
    )


def test_environment_configuration_requires_token(tmp_path, monkeypatch):
    monkeypatch.delenv("EMMET_API_TOKEN", raising=False)

    with pytest.raises(EmmetCliError, match="EMMET_API_TOKEN"):
        HttpSubmissionUploader.from_environment(StateManager(tmp_path / "state"))


def test_context_manager_closes_owned_client(tmp_path):
    uploader = HttpSubmissionUploader(
        state_manager=StateManager(tmp_path / "state"),
        token="secret-token",
    )
    client = uploader.client

    with uploader:
        assert not client.is_closed

    assert client.is_closed


def test_uploads_raw_archive_and_snapshot_manifest(tmp_path):
    submission = _submission_with_raw_files(tmp_path)
    changes = submission.stage_for_push()
    state_manager = StateManager(tmp_path / "state")
    service = UploadService()

    uploader = _uploader(state_manager, service)
    submission.push(uploader)

    assert len(service.prepare_requests) == 1
    assert service.prepare_headers[0]["authorization"] == "Bearer secret-token"
    assert len(service.puts) == 2
    archive = next(
        content
        for object_id, content in service.puts.items()
        if object_id.endswith(".h5")
    )
    assert archive.startswith(b"\x89HDF")
    manifest = json.loads(
        next(
            content
            for object_id, content in service.puts.items()
            if object_id.endswith(".json")
        )
    )
    assert service.prepare_headers[0]["idempotency-key"] == manifest["snapshot_id"]
    assert manifest["submission_id"] == str(submission.id)
    assert manifest["calculations"][0]["change"] == "added"
    assert manifest["calculations"][0]["added_files"] == ["INCAR", "POSCAR"]
    assert len(service.finalize_requests) == 1
    assert state_manager.get(UPLOAD_STATE_KEY) == {}
    assert len(submission.calc_history) == 1
    assert changes.has_changes
    assert not uploader.client.is_closed

    second_directory = tmp_path / "second"
    second_directory.mkdir()
    second_submission = _submission_with_raw_files(second_directory)
    uploader.upload(second_submission.id, second_submission.stage_for_push())
    assert len(service.finalize_requests) == 2
    assert not uploader.client.is_closed


def test_partial_upload_resumes_saved_session(tmp_path):
    submission = _submission_with_raw_files(tmp_path)
    changes = submission.stage_for_push()
    state_manager = StateManager(tmp_path / "state")
    service = UploadService(fail_object="manifest")

    with pytest.raises(EmmetCliError, match="Uploading object") as exc_info:
        submission.push(_uploader(state_manager, service))
    rendered_error = "".join(traceback.format_exception(exc_info.value))
    assert "secret-token" not in rendered_error
    assert "uploads.test" not in rendered_error

    saved = state_manager.get(UPLOAD_STATE_KEY)[str(submission.id)]
    assert len(saved["completed_object_ids"]) == 1
    assert saved["completed_object_ids"][0].endswith(".h5")
    assert "secret-token" not in json.dumps(saved)
    assert len(submission.calc_history) == 0

    service.fail_object = None
    submission.push(_uploader(state_manager, service))

    assert len(service.prepare_requests) == 1
    assert len(submission.calc_history) == 1
    assert state_manager.get(UPLOAD_STATE_KEY) == {}


def test_upload_progress_uses_batched_atomic_checkpoints(tmp_path, monkeypatch):
    submission = _submission_with_raw_files(tmp_path)
    changes = submission.stage_for_push()
    state_manager = StateManager(tmp_path / "state")
    service = UploadService()
    uploader = _uploader(state_manager, service)
    objects = []
    for index in range(25):
        path = tmp_path / f"object-{index}"
        path.write_bytes(f"object {index}".encode())
        objects.append(
            uploader._object_info(f"objects/{index}", path, "application/octet-stream")
        )
    monkeypatch.setattr(
        uploader,
        "_build_objects",
        lambda *args: (objects, {"snapshot_id": "snapshot-1"}),
    )
    original_update = state_manager.update
    update_calls = 0
    sort_calls = 0

    def count_update(key, updater):
        nonlocal update_calls
        update_calls += 1
        return original_update(key, updater)

    def count_sorted(*args, **kwargs):
        nonlocal sort_calls
        sort_calls += 1
        return builtins.sorted(*args, **kwargs)

    monkeypatch.setattr(state_manager, "update", count_update)
    monkeypatch.setattr(upload_module, "sorted", count_sorted, raising=False)

    uploader.upload(submission.id, changes)

    assert len(service.puts) == 25
    assert update_calls == 5  # prepare, 2 batches, final partial batch, and clear
    assert sort_calls == 3


def test_expired_session_refreshes_urls_without_reuploading_completed_objects(
    tmp_path,
):
    submission = _submission_with_raw_files(tmp_path)
    submission.stage_for_push()
    state_manager = StateManager(tmp_path / "state")
    service = UploadService(fail_object="manifest")

    with pytest.raises(EmmetCliError):
        submission.push(_uploader(state_manager, service))

    sessions = state_manager.get(UPLOAD_STATE_KEY)
    sessions[str(submission.id)]["expires_at"] = "2000-01-01T00:00:00+00:00"
    state_manager.set(UPLOAD_STATE_KEY, sessions)
    archive_id = sessions[str(submission.id)]["completed_object_ids"][0]
    service.fail_object = None

    submission.push(_uploader(state_manager, service))

    assert len(service.prepare_requests) == 2
    assert service.put_attempts.count(archive_id) == 1


def test_checkpoint_failure_preserves_upload_error_and_remote_progress(
    tmp_path, monkeypatch
):
    submission = _submission_with_raw_files(tmp_path)
    submission.stage_for_push()
    state_manager = StateManager(tmp_path / "state")
    service = UploadService(fail_object="manifest")
    original_update = state_manager.update
    update_calls = 0

    def fail_progress_checkpoint(key, updater):
        nonlocal update_calls
        update_calls += 1
        if update_calls == 2:
            raise OSError("disk full")
        return original_update(key, updater)

    monkeypatch.setattr(state_manager, "update", fail_progress_checkpoint)

    with pytest.raises(EmmetCliError, match="Uploading object"):
        submission.push(_uploader(state_manager, service))

    sessions = state_manager.get(UPLOAD_STATE_KEY)
    archive_id = next(
        object_id for object_id in service.puts if object_id.endswith(".h5")
    )
    assert sessions[str(submission.id)]["completed_object_ids"] == []

    monkeypatch.setattr(state_manager, "update", original_update)
    sessions[str(submission.id)]["expires_at"] = "2000-01-01T00:00:00+00:00"
    state_manager.set(UPLOAD_STATE_KEY, sessions)
    service.fail_object = None

    submission.push(_uploader(state_manager, service))

    assert len(service.prepare_requests) == 2
    assert service.put_attempts.count(archive_id) == 1


def test_retry_after_lost_finalize_uses_uploaded_checksums(tmp_path, monkeypatch):
    submission = _submission_with_raw_files(tmp_path)
    submission.stage_for_push()
    state_manager = StateManager(tmp_path / "state")
    service = UploadService(fail_finalize=True)

    with pytest.raises(EmmetCliError, match="Finalizing upload session"):
        submission.push(_uploader(state_manager, service))
    first_put_attempts = list(service.put_attempts)
    uploaded_archive_id = next(
        object_id for object_id in service.puts if object_id.endswith(".h5")
    )
    uploaded_archive_sha256 = hashlib.sha256(
        service.puts[uploaded_archive_id]
    ).hexdigest()
    assert len(submission.calc_history) == 0

    original_file_digest = upload_module._file_digest

    def rebuilt_file_digest(path):
        if path.suffix == ".h5":
            return "0" * 64
        return original_file_digest(path)

    monkeypatch.setattr(upload_module, "_file_digest", rebuilt_file_digest)

    submission.push(_uploader(state_manager, service))

    assert service.put_attempts == first_put_attempts
    assert len(service.finalize_requests) == 2
    finalized_archive = next(
        item
        for item in service.finalize_requests[-1]["objects"]
        if item["object_id"] == uploaded_archive_id
    )
    assert finalized_archive["sha256"] == uploaded_archive_sha256
    assert len(submission.calc_history) == 1


def test_removal_only_push_uploads_manifest(tmp_path):
    submission = _submission_with_raw_files(tmp_path)
    previous = submission._create_calculations_copy()
    removed_id = previous[0][1].id
    submission.calc_history.append(previous)
    submission.calculations = []
    changes = submission.stage_for_push()
    state_manager = StateManager(tmp_path / "state")
    service = UploadService()

    submission.push(_uploader(state_manager, service))

    assert [change.status for change in changes.changes] == ["removed"]
    assert list(service.puts) == [
        f"manifests/{service.prepare_requests[0]['snapshot_id']}.json"
    ]
    manifest = json.loads(next(iter(service.puts.values())))
    assert manifest["removed_calculations"][0]["calculation_id"] == str(removed_id)
