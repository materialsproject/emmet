import yaml
from importlib.resources import files

with files("emmet.core.vasp.calc_types").joinpath("calc_types.yaml").open() as f:
    config = yaml.safe_load(f)

_REFERENCE_MEMBER_COUNT = {
    "RunType": 2 * sum(len(rtypes) for rtypes in config["RUN_TYPES"].values()),
    "TaskType": len(config["TASK_TYPES"]),
}
_REFERENCE_MEMBER_COUNT["CalcType"] = (
    _REFERENCE_MEMBER_COUNT["RunType"] * _REFERENCE_MEMBER_COUNT["TaskType"]
)


def test_enums():
    from emmet.core.vasp.calc_types import enums as vasp_enums

    for k, count in _REFERENCE_MEMBER_COUNT.items():
        # Test that we have expected number of enum members
        curr_enum = getattr(vasp_enums, k, None)
        assert len(curr_enum) == count

        if k == "RunType":
            # Test that RunType enum is not case sensitive
            assert all(
                curr_enum(member.value.upper()) == curr_enum(member.value.lower())
                for member in curr_enum
            )
