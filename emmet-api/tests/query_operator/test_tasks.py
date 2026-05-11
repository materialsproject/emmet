from functools import partial
from itertools import product

import pytest

from emmet.api.query_operator import MultiTaskIDQuery
from emmet.api.utils import process_identifiers, split_csv


@pytest.mark.parametrize("use_plural,use_prefix", product(*[[True, False]] * 2))
def test_multi_task_id(use_plural: bool, use_prefix: bool):

    field = "task_id" + ("s" if use_plural else "")

    multi_idxs = "mp-149, mol-129, aaft"
    # check space removal
    for idxs in [multi_idxs, multi_idxs.replace(" ", "")]:
        q = MultiTaskIDQuery(field_name=field, pre_processor=split_csv).query(
            task_ids=idxs
        )
        assert q == {"criteria": {field: {"$in": ["mp-149", "mol-129", "aaft"]}}}

    assert MultiTaskIDQuery(field_name=field).query(task_ids="mp-abcdefg") == {
        # default padlen for process_identifiers is 8 (emmet.core.types.typing.ID_PADLEN)
        # abcdefg -> aabcdefg (extra padded 'a')
        "criteria": {field: {"$in": ["aabcdefg"]}}
    }

    # Note coercion to mp- prefix
    op = MultiTaskIDQuery(
        field_name=field,
        pre_processor=partial(process_identifiers, use_prefix=use_prefix),
    )
    assert op.query(task_ids="mp-149, mvc-13") == {
        "criteria": {
            field: {
                "$in": (
                    ["mp-aaaaaaft", "mp-aaaaaaan"]
                    if use_prefix
                    else ["aaaaaaft", "aaaaaaan"]
                )
            }
        }
    }
