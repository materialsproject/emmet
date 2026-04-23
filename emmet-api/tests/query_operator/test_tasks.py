import pytest

from emmet.api.query_operator.tasks import MultiTaskIDQuery


@pytest.mark.parametrize("use_plural", [True, False])
def test_multi_task_id(use_plural: bool):

    key = "task_id" + ("s" if use_plural else "")

    multi_idxs = "mp-149, mol-129, aaft"
    # check space removal
    for idxs in [multi_idxs, multi_idxs.replace(" ", "")]:
        q = MultiTaskIDQuery(use_plural=use_plural).query(task_ids=idxs)
        assert q == {"criteria": {key: {"$in": ["mp-149", "mol-129", "aaft"]}}}

    assert MultiTaskIDQuery(use_plural=use_plural).query(task_ids="mp-abcdefg") == {
        "criteria": {key: "mp-abcdefg"}
    }
