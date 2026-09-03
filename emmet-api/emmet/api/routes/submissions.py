from typing import Literal
from emmet.core.types.typing import DateTimeType
from uuid import UUID
from enum import Enum
from typing import Annotated
from pydantic import BaseModel, ConfigDict, BeforeValidator
from fastapi import APIRouter, Header, HTTPException, status, Depends

router = APIRouter()

GROUP_HEADER_NAME = "x-authenticated-groups"


class ContributerState(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    EXPIRED = "expired"


class ContributerStatus(BaseModel):
    status: ContributerState
    model_config = ConfigDict({"use_enum_values": True})


class SubmissionState(str, Enum):
    COMPLETE = "complete"
    INCOMPLETE = "incomplete"


class SubmissionStatus(BaseModel):
    submission_id: UUID
    status: SubmissionState
    completed_object_ids: list[str]
    in_progress_object_ids: list[str]
    model_config = ConfigDict({"use_enum_values": True})


class CalculationChange(str, Enum):
    ADDED = "added"
    CHANGED = "changed"
    UNCHANGED = "unchanged"


class Calculation(BaseModel):
    calculation_id: UUID
    archive_object_id: str
    content_digest: str
    change: CalculationChange
    added_files: list[str]
    changed_files: list[str]
    removed_files: list[str]
    model_config = ConfigDict({"use_enum_values": True})


class RemovedCalculation(BaseModel):
    calculation_id: UUID
    removed_files: list[str]


class UploadManifest(BaseModel):
    submission_id: UUID
    schema_version: int
    snapshot_id: str
    calculations: list[Calculation]
    removed_calculations: list[RemovedCalculation]


class ObjectDigest(BaseModel):
    object_id: str
    content_type: Literal["application/x-hdf5", "application/json"]
    size: int


class UploadRequest(BaseModel):
    snapshot_id: str
    manifest: UploadManifest
    objects: list[ObjectDigest]


class UploadURLs(BaseModel):
    object_id: str
    url: str


class Object(BaseModel):
    object_id: str
    sha256: str


class UploadResponse(BaseModel):
    session_id: UUID
    expires_at: DateTimeType
    uploads: list[UploadURLs]
    completed_object_ids: list[str]
    completed_objects: list[Object]


class FinalizeSessionRequest(BaseModel):
    snapshot_id: str
    objects: list[Object]


class SessionState(str, Enum):
    COMPLETE = "complete"
    IN_PROGRESS = "in_progress"
    # ABANDONED = "abandoned"  # ? likely need some mechanism to mark submissions abandoned after x period of time and lock them


class FinalizeSessionResponse(BaseModel):
    submission_id: UUID
    session_state: SessionState


def validate_contributer(x_authenticated_groups: Annotated[str, Header()]):
    if not "core:contributions=writer" in x_authenticated_groups.split(","):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)


@router.get("/submissions/contributer-status")
def check_contributer_status(
    x_consumer_id: Annotated[str, Header()],
    _authenticated_groups: Annotated[str, Depends(validate_contributer)],
) -> ContributerStatus:
    # TODO: query w/ consumer_id

    return ContributerStatus(status=ContributerState.ACTIVE)


@router.post("/submissions/{submission_id}/status")
def submission_status(
    x_consumer_id: Annotated[str, Header()],
    submission_id: UUID,
    _authenticated_groups: Annotated[str, Depends(validate_contributer)],
):
    # TODO: verify submission_id belongs to consumer_id
    # TODO: query w/ consumer_id + submission_id

    return SubmissionStatus(
        submission_id=submission_id,
        status=SubmissionState.INCOMPLETE,
        completed_object_ids=[],
        in_progress_object_ids=[],
    )


@router.post("/submissions/{submission_id}/upload-sessions")
def create_submission(
    x_consumer_id: Annotated[str, Header()],
    submission_id: UUID,
    upload_request: UploadRequest,
    _authenticated_groups: Annotated[str, Depends(validate_contributer)],
) -> UploadResponse:
    # TODO: verify submission_id belongs to consumer_id
    # TODO: query w/ consumer_id + submission_id

    from uuid import uuid4

    return UploadResponse(
        session_id=uuid4(),
        expires_at="2027-01-01",
        uploads=[],
        completed_object_ids=[],
        completed_objects=[],
    )


@router.post("/submissions/{submission_id}/upload-sessions/{session_id}/complete")
def complete_submission(
    submission_id: UUID,
    session_id: UUID,
    finalize_session_request: FinalizeSessionRequest,
    x_consumer_id: Annotated[str, Header()],
    _authenticated_groups: Annotated[str, Depends(validate_contributer)],
) -> FinalizeSessionResponse:
    # TODO: verify submission_id belongs to consumer_id
    # TODO: query w/ consumer_id + submission_id + session_id

    return FinalizeSessionResponse(
        submission_id=submission_id, session_state=SessionState.COMPLETE
    )
