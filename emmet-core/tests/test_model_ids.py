"""Identifier typing of models served by the API."""

import pytest

from emmet.core.substrates import SubstratesDoc
from emmet.core.tasks import EntryDoc


@pytest.mark.parametrize("value", ["mp-149", "mp-aaaaaaft"])
def test_entry_doc_task_id_is_a_validated_identifier(value):
    assert EntryDoc(task_id=value).model_dump()["task_id"] == "mp-aaaaaaft"
    assert EntryDoc().task_id is None


def test_substrates_doc_ids_are_validated_identifiers():
    doc = SubstratesDoc(sub_id="mp-149", film_id="mp-13")
    assert doc.model_dump() == {
        "sub_form": None,
        "sub_id": "mp-aaaaaaft",
        "film_orient": None,
        "area": None,
        "energy": None,
        "film_id": "mp-aaaaaaan",
        "norients": None,
        "orient": None,
    }
