
from monty.serialization import loadfn

_REFERENCE_MEMBER_COUNT = {
    "LevelOfTheory": 264,
    "TaskType": 8,
}
_REFERENCE_MEMBER_COUNT["CalcType"] = (
    _REFERENCE_MEMBER_COUNT["LevelOfTheory"]
    * _REFERENCE_MEMBER_COUNT["TaskType"]
)

def test_generate(tmp_dir):

    from emmet.core.qchem.calc_types.generate import generate_enum_file

    new_enum_file = "new_qchem_enums.json"
    generate_enum_file(enum_file_name=new_enum_file)
    new_enums = loadfn(new_enum_file)

    for enum_name in {"LevelOfTheory","TaskType","CalcType"}:
        new_enum_dict = {
            k: v for k, v in new_enums.get(enum_name,{}).items()
            if not k.startswith("__")
        }
        len(new_enum_dict) == _REFERENCE_MEMBER_COUNT[enum_name]
        
def test_enums():

    from emmet.core.qchem.calc_types import enums as qchem_enums

    for k, count in _REFERENCE_MEMBER_COUNT.items():
        # Test that we have expected number of enum members
        curr_enum = getattr(qchem_enums, k, None)
        assert len(curr_enum) == count
    
        # Test that enums are not case sensitive
        assert all(
            curr_enum(member.value.upper()) == curr_enum(member.value.lower())
            for member in curr_enum
        )