import hashlib
import io
import json
import traceback
import builtins
from datetime import datetime, timedelta, UTC
from pathlib import Path
from uuid import uuid4

import h5py
import httpx2
import pytest

import emmet.cli.upload as upload_module
from emmet.archival.vasp.metadata import ArchiveMetadata
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
    def __init__(
        self,
        fail_object=None,
        fail_finalize=False,
        malformed_upload=False,
        omit_completed_objects=False,
        finalize_state="complete",
    ):
        self.fail_object = fail_object
        self.fail_finalize = fail_finalize
        self.malformed_upload = malformed_upload
        self.omit_completed_objects = omit_completed_objects
        self.finalize_state = finalize_state
        self.prepare_requests = []
        self.prepare_headers = []
        self.put_attempts = []
        self.puts = {}
        self.finalize_requests = []
        self.finalize_headers = []

    def __call__(self, request):
        content = request.read()
        if request.url.host == "uploads.test":
            object_id = request.headers["x-object-id"]
            self.put_attempts.append(object_id)
            if object_id == self.fail_object or (
                self.fail_object == "manifest" and object_id.endswith(".json")
            ):
                return httpx2.Response(500)
            self.puts[object_id] = content
            return httpx2.Response(200)

        payload = json.loads(content)
        if request.url.path.endswith("/complete"):
            self.finalize_requests.append(payload)
            self.finalize_headers.append(request.headers)
            if self.fail_finalize:
                self.fail_finalize = False
                return httpx2.Response(500)
            for item in payload["objects"]:
                uploaded_sha256 = hashlib.sha256(
                    self.puts[item["object_id"]]
                ).hexdigest()
                if item["sha256"] != uploaded_sha256:
                    return httpx2.Response(422)
            response_submission_id = request.url.path.split("/")[2]
            return httpx2.Response(
                200,
                json={
                    "submission_id": response_submission_id,
                    "session_state": self.finalize_state,
                },
            )

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
        if self.malformed_upload:
            uploads[0].pop("object_id")
        response_payload = {
            "session_id": "session-1",
            "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
            "uploads": uploads,
            "completed_object_ids": list(self.puts),
        }
        if not self.omit_completed_objects:
            response_payload["completed_objects"] = [
                {
                    "object_id": object_id,
                    "sha256": hashlib.sha256(uploaded).hexdigest(),
                }
                for object_id, uploaded in self.puts.items()
            ]
        return httpx2.Response(200, json=response_payload)


def _uploader(state_manager, service):
    client = httpx2.Client(transport=httpx2.MockTransport(service))
    return HttpSubmissionUploader(
        state_manager=state_manager,
        api_key="secret-token",
        api_url="https://api.test",
        client=client,
    )


def test_environment_configuration_requires_token(tmp_path, monkeypatch):
    monkeypatch.delenv("MP_API_KEY", raising=False)
    monkeypatch.delenv("EMMET_API_TOKEN", raising=False)

    with pytest.raises(EmmetCliError, match="MP_API_KEY"):
        HttpSubmissionUploader.from_environment(StateManager(tmp_path / "state"))


def test_environment_prefers_mp_api_key(tmp_path, monkeypatch):
    monkeypatch.setenv("MP_API_KEY", "current-key")
    monkeypatch.setenv("EMMET_API_TOKEN", "legacy-key")

    with HttpSubmissionUploader.from_environment(
        StateManager(tmp_path / "state")
    ) as uploader:
        assert uploader.api_key == "current-key"


def test_environment_supports_deprecated_token(tmp_path, monkeypatch, caplog):
    monkeypatch.delenv("MP_API_KEY", raising=False)
    monkeypatch.setenv("EMMET_API_TOKEN", "legacy-key")

    with HttpSubmissionUploader.from_environment(
        StateManager(tmp_path / "state")
    ) as uploader:
        assert uploader.api_key == "legacy-key"
    assert "deprecated" in caplog.text


def test_context_manager_closes_owned_client(tmp_path):
    uploader = HttpSubmissionUploader(
        state_manager=StateManager(tmp_path / "state"),
        api_key="secret-token",
    )
    client = uploader.client

    with uploader:
        assert not client.is_closed

    assert client.is_closed


def test_contributor_status_matches_server_route(tmp_path):
    def service(request):
        assert request.method == "GET"
        assert request.url.path == "/submissions/contributor-status"
        assert request.headers["x-api-key"] == "secret-token"
        assert request.content == b""
        return httpx2.Response(200, json={"status": "active"})

    client = httpx2.Client(transport=httpx2.MockTransport(service))
    uploader = HttpSubmissionUploader(
        state_manager=StateManager(tmp_path / "state"),
        api_key="secret-token",
        api_url="https://api.test",
        client=client,
    )

    assert uploader.contributor_status() == "active"


def test_submission_status_matches_server_route(tmp_path):
    submission_id = uuid4()

    def service(request):
        assert request.method == "POST"
        assert request.url.path == f"/submissions/{submission_id}/status"
        assert request.content == b""
        return httpx2.Response(
            200,
            json={
                "submission_id": str(submission_id),
                "status": "incomplete",
                "completed_object_ids": ["completed-object"],
                "in_progress_object_ids": ["pending-object"],
            },
        )

    client = httpx2.Client(transport=httpx2.MockTransport(service))
    uploader = HttpSubmissionUploader(
        state_manager=StateManager(tmp_path / "state"),
        api_key="secret-token",
        api_url="https://api.test",
        client=client,
    )

    assert uploader.submission_status(submission_id) == {
        "submission_id": str(submission_id),
        "status": "incomplete",
        "completed_object_ids": ["completed-object"],
        "in_progress_object_ids": ["pending-object"],
    }


def test_uploads_raw_archive_and_snapshot_manifest(tmp_path):
    submission = _submission_with_raw_files(tmp_path)
    changes = submission.stage_for_push()
    state_manager = StateManager(tmp_path / "state")
    service = UploadService()

    uploader = _uploader(state_manager, service)
    submission.push(uploader)

    assert len(service.prepare_requests) == 1
    assert service.prepare_headers[0]["x-api-key"] == "secret-token"
    assert "authorization" not in service.prepare_headers[0]
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
    assert service.finalize_headers[0]["idempotency-key"] == manifest["snapshot_id"]
    assert all("sha256" not in item for item in service.prepare_requests[0]["objects"])
    assert all(
        isinstance(item.get("size"), int) and item["size"] > 0
        for item in service.prepare_requests[0]["objects"]
    )
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
    submission.stage_for_push()
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


def test_malformed_prepare_upload_is_wrapped(tmp_path):
    submission = _submission_with_raw_files(tmp_path)
    submission.stage_for_push()
    service = UploadService(malformed_upload=True)

    with pytest.raises(EmmetCliError, match="invalid prepare response"):
        submission.push(_uploader(StateManager(tmp_path / "state"), service))


def test_prepare_requires_completed_objects_field(tmp_path):
    submission = _submission_with_raw_files(tmp_path)
    submission.stage_for_push()
    service = UploadService(omit_completed_objects=True)

    with pytest.raises(EmmetCliError, match="invalid prepare response"):
        submission.push(_uploader(StateManager(tmp_path / "state"), service))


def test_finalize_requires_complete_session_state(tmp_path):
    submission = _submission_with_raw_files(tmp_path)
    submission.stage_for_push()
    service = UploadService(finalize_state="in_progress")

    with pytest.raises(EmmetCliError, match="invalid finalization response"):
        submission.push(_uploader(StateManager(tmp_path / "state"), service))

    assert len(submission.calc_history) == 0


def test_streaming_file_read_error_is_retryable(tmp_path, monkeypatch):
    submission = _submission_with_raw_files(tmp_path)
    submission.stage_for_push()
    service = UploadService()

    def broken_file_chunks(path, digest):
        raise OSError("file disappeared")
        yield b""  # pragma: no cover

    monkeypatch.setattr(upload_module, "_file_chunks", broken_file_chunks)

    with pytest.raises(EmmetCliError, match="accessible and retry"):
        submission.push(_uploader(StateManager(tmp_path / "state"), service))


def test_prepare_state_failure_is_retryable(tmp_path, monkeypatch):
    submission = _submission_with_raw_files(tmp_path)
    submission.stage_for_push()
    state_manager = StateManager(tmp_path / "state")
    service = UploadService()

    def fail_update(*args):
        raise TypeError("not serializable")

    monkeypatch.setattr(state_manager, "update", fail_update)

    with pytest.raises(EmmetCliError, match="prepared remotely"):
        submission.push(_uploader(state_manager, service))

    assert len(service.prepare_requests) == 1
    assert service.puts == {}


def test_checkpoint_wraps_non_os_state_error(tmp_path, monkeypatch):
    state_manager = StateManager(tmp_path / "state")
    uploader = _uploader(state_manager, UploadService())

    def fail_update(*args):
        raise TypeError("not serializable")

    monkeypatch.setattr(state_manager, "update", fail_update)

    with pytest.raises(EmmetCliError, match="progress could not be saved"):
        uploader._checkpoint_session(
            submission_id=uuid4(),
            session={},
            completed=set(),
            session_objects={},
        )


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
    assert sort_calls == 0


def test_expired_session_refreshes_urls_without_reuploading_completed_objects(
    tmp_path, monkeypatch
):
    submission = _submission_with_raw_files(tmp_path)
    submission.stage_for_push()
    state_manager = StateManager(tmp_path / "state")
    service = UploadService(fail_object="manifest")
    original_to_archive = upload_module.RawArchive.to_archive
    archive_writes = 0

    def count_archive_writes(*args, **kwargs):
        nonlocal archive_writes
        archive_writes += 1
        return original_to_archive(*args, **kwargs)

    monkeypatch.setattr(upload_module.RawArchive, "to_archive", count_archive_writes)

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
    assert archive_writes == 1


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
    original_to_archive = upload_module.RawArchive.to_archive
    archive_writes = 0

    def count_archive_writes(*args, **kwargs):
        nonlocal archive_writes
        archive_writes += 1
        return original_to_archive(*args, **kwargs)

    monkeypatch.setattr(upload_module.RawArchive, "to_archive", count_archive_writes)

    with pytest.raises(EmmetCliError, match="Finalizing upload session"):
        submission.push(_uploader(state_manager, service))
    first_put_attempts = list(service.put_attempts)
    uploaded_archive_id = next(
        object_id for object_id in service.puts if object_id.endswith(".h5")
    )
    uploaded_archive_sha256 = hashlib.sha256(
        service.puts[uploaded_archive_id]
    ).hexdigest()
    assert archive_writes == 1
    assert len(submission.calc_history) == 0

    submission.push(_uploader(state_manager, service))

    assert archive_writes == 1
    assert service.put_attempts == first_put_attempts
    assert len(service.finalize_requests) == 2
    finalized_archive = next(
        item
        for item in service.finalize_requests[-1]["objects"]
        if item["object_id"] == uploaded_archive_id
    )
    assert finalized_archive["sha256"] == uploaded_archive_sha256
    assert len(submission.calc_history) == 1


def test_clear_failure_does_not_hide_successful_push(tmp_path, monkeypatch, caplog):
    submission = _submission_with_raw_files(tmp_path)
    changes = submission.stage_for_push()
    state_manager = StateManager(tmp_path / "state")
    service = UploadService()
    original_update = state_manager.update
    update_calls = 0

    def fail_clear(key, updater):
        nonlocal update_calls
        update_calls += 1
        if update_calls == 3:
            raise OSError("disk full")
        return original_update(key, updater)

    monkeypatch.setattr(state_manager, "update", fail_clear)

    submission.push(_uploader(state_manager, service))

    assert len(submission.calc_history) == 1
    assert str(submission.id) in state_manager.get(UPLOAD_STATE_KEY)
    assert "local retry state could not be cleared" in caplog.text

    monkeypatch.setattr(state_manager, "update", original_update)
    _uploader(state_manager, service).upload(submission.id, changes)

    assert len(service.put_attempts) == 2
    assert len(service.finalize_requests) == 2
    assert (
        service.finalize_headers[0]["idempotency-key"]
        == service.finalize_headers[1]["idempotency-key"]
    )
    assert state_manager.get(UPLOAD_STATE_KEY) == {}


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


def _stage_directory(directory, calc_suffixes=None):
    """Make a submission of the calculations in a directory, which pass validation."""
    kwargs = {"calc_suffixes": calc_suffixes} if calc_suffixes else {}
    submission = Submission.from_paths([directory], **kwargs)
    for _, calculation in submission.calculations:
        for file in calculation.files:
            file.compute_hash()
        calculation.calc_valid = True
    return submission


def _archives_by_calculation(service, submission):
    archives = {}
    for locator, calculation in submission.calculations:
        object_id = next(
            object_id
            for object_id in service.puts
            if object_id.startswith(f"calculations/{calculation.id}/")
        )
        archives[locator.modifier] = (
            calculation,
            h5py.File(io.BytesIO(service.puts[object_id]), "r"),
        )
    return archives


def test_each_calculation_of_a_directory_is_archived_on_its_own(tmp_path):
    calc_dir = tmp_path / "launcher_1"
    calc_dir.mkdir()
    for name in (
        "INCAR.relax1",
        "INCAR.relax2",
        "vasprun.xml.relax1",
        "vasprun.xml.relax2",
        "INCAR.orig",
        "POTCAR.spec",
        "CHGCAR",
    ):
        content = "[]" if name == "POTCAR.spec" else f"contents of {name}"
        (calc_dir / name).write_text(content)
    submission = _stage_directory(calc_dir)
    assert len(submission.calculations) == 2

    submission.stage_for_push()
    service = UploadService()
    submission.push(_uploader(StateManager(tmp_path / "state"), service))

    archives = _archives_by_calculation(service, submission)
    assert set(archives) == {"relax1", "relax2"}
    for suffix, (calculation, archive) in archives.items():
        metadata = ArchiveMetadata.from_attrs(archive.attrs)
        assert metadata.calculation_id == calculation.id
        assert metadata.submission_id == submission.id
        assert metadata.calc_suffix == suffix
        assert metadata.snapshot_id == service.finalize_requests[0]["snapshot_id"]
        # the directory of the user is not given away
        assert metadata.source_dir_name == (
            f"submission://{submission.id}/{calculation.id}"
        )
        assert str(tmp_path) not in str(dict(archive.attrs))

        # every calculation has its own output, and the shared POTCAR
        vasprun = archive["output/vasprun.xml"]
        assert vasprun.attrs["original_name"] == f"vasprun.xml.{suffix}"
        assert "input/POTCAR.spec" in archive
        for key in ("input/INCAR", "output/vasprun.xml"):
            assert not Path(archive[key].attrs["original_name"]).is_absolute()
            assert "file_path" not in archive[key].attrs

    assert "input/INCAR.orig" in archives["relax1"][1]
    assert "input/INCAR.orig" not in archives["relax2"][1]
    assert "volumetric/CHGCAR" in archives["relax2"][1]
    assert "volumetric/CHGCAR" not in archives["relax1"][1]


def test_custom_suffixes_are_used_to_archive(tmp_path):
    calc_dir = tmp_path / "launcher_1"
    calc_dir.mkdir()
    for name in ("INCAR.nscf", "vasprun.xml.nscf"):
        (calc_dir / name).write_text(f"contents of {name}")
    submission = _stage_directory(calc_dir, calc_suffixes=("nscf",))
    submission.stage_for_push()
    service = UploadService()
    submission.push(_uploader(StateManager(tmp_path / "state"), service))

    ((calculation, archive),) = _archives_by_calculation(service, submission).values()
    assert ArchiveMetadata.from_attrs(archive.attrs).calc_suffix == "nscf"
    assert "output/vasprun.xml" in archive


def test_a_file_which_cannot_be_archived_fails_the_push_before_uploading(tmp_path):
    submission = _submission_with_raw_files(tmp_path)
    ((locator, calculation),) = submission.calculations
    # a file which was not checked when it was added, e.g., from an old submission
    path = tmp_path / "OUTCAR.old"
    path.write_text("x")
    calculation.files.append(FileMetadata(name=path.name, path=path))
    calculation.files[-1].compute_hash()

    submission.stage_for_push()
    service = UploadService()
    with pytest.raises(ValueError, match="'old'"):
        submission.push(_uploader(StateManager(tmp_path / "state"), service))
    assert service.puts == {}
    assert submission.calc_history == []


def test_original_names_are_relative_to_the_directory_of_the_calculation(tmp_path):
    launcher = tmp_path / "launcher_1"
    for suffix in ("relax1", "relax2"):
        (launcher / suffix).mkdir(parents=True)
        for name in ("INCAR", "vasprun.xml"):
            (launcher / suffix / name).write_text(f"{suffix} {name}")
    (launcher / "POTCAR.spec").write_text("[]")
    submission = _stage_directory(launcher)
    assert {loc.modifier for loc, _ in submission.calculations} == {"relax1", "relax2"}

    submission.stage_for_push()
    service = UploadService()
    submission.push(_uploader(StateManager(tmp_path / "state"), service))

    for suffix, (_, archive) in _archives_by_calculation(service, submission).items():
        assert archive["output/vasprun.xml"].attrs["original_name"] == (
            f"{suffix}/vasprun.xml"
        )
        assert archive["input/POTCAR.spec"].attrs["original_name"] == "POTCAR.spec"
