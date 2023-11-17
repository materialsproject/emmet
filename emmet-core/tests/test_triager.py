from emmet.core.tasks import TaskDoc
from emmet.core.triage.MP_triager import FailedTriageMessage, MPTriager, TriageDoc
from emmet.core.vasp.task_valid import TaskDocument
import json
from monty.io import zopen
import pytest


@pytest.mark.parametrize(
    "triager",
    [
        MPTriager,
        TriageDoc,
    ],
)
def test_triage_methods(triager, test_dir):
    with zopen(test_dir / "CoF_TaskDoc.json", "r") as f:
        taskdoc_d = json.load(f)

    expected_errors = {FailedTriageMessage(f"TR{itr}") for itr in range(2, 6)}

    taskdoc = TaskDoc(
        **{key: taskdoc_d[key] for key in taskdoc_d if key != "orig_inputs"}
    )

    taskdocument = TaskDocument(
        **{key: taskdoc_d[key] for key in taskdoc_d if key != "last_updated"}
    )

    for doc in [taskdoc, taskdocument]:
        doc.task_id = "mp-123456789"
        triage_doc = triager.from_task_doc(task_doc=doc)

        assert not triage_doc.valid
        assert set(triage_doc.reasons) == expected_errors
