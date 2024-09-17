from emmet.core.qchem.calc_types.calc_types import (
    FUNCTIONALS,
    BASIS_SETS,
    SOLVENT_MODELS,
    TASK_TYPES,
)

_REFERENCE_MEMBER_COUNT = {
    "LevelOfTheory": len(FUNCTIONALS) * len(BASIS_SETS) * len(SOLVENT_MODELS),
    "TaskType": len(TASK_TYPES),
}
_REFERENCE_MEMBER_COUNT["CalcType"] = (
    _REFERENCE_MEMBER_COUNT["LevelOfTheory"] * _REFERENCE_MEMBER_COUNT["TaskType"]
)


def test_enums():
    from emmet.core.qchem.calc_types import enums as qchem_enums

    for k, count in _REFERENCE_MEMBER_COUNT.items():
        # Test that we have expected number of enum members
        curr_enum = getattr(qchem_enums, k, None)
        assert len(curr_enum) == count
