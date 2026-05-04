from itertools import product
import pytest

from emmet.api.query_operator.tasks import MultiTaskIDQuery


@pytest.mark.parametrize("use_plural,use_prefix", product(*[[True, False]] * 2))
def test_multi_task_id(use_plural: bool, use_prefix: bool):

    key = "task_id" + ("s" if use_plural else "")

    multi_idxs = "mp-149, mol-129, aaft"
    # check space removal
    for idxs in [multi_idxs, multi_idxs.replace(" ", "")]:
        q = MultiTaskIDQuery(key=key).query(task_ids=idxs)
        assert q == {"criteria": {key: {"$in": ["mp-149", "mol-129", "aaft"]}}}

    assert MultiTaskIDQuery(key=key).query(task_ids="mp-abcdefg") == {
        "criteria": {key: "mp-abcdefg"}
    }

    # Note coercion to mp- prefix
    op = MultiTaskIDQuery(key=key, validate=True, use_prefix=use_prefix)
    assert op.query(task_ids="mp-149, mvc-13") == {
        "criteria": {
            key: {
                "$in": (
                    ["mp-aaaaaaft", "mp-aaaaaaan"]
                    if use_prefix
                    else ["aaaaaaft", "aaaaaaan"]
                )
            }
        }
    }
