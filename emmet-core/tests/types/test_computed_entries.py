import pytest
from pydantic import TypeAdapter

from emmet.core.io.pymatgen import Element
from emmet.core.types.pymatgen_types.computed_entries_adapter import (
    ComputedEntryType,
)


@pytest.mark.parametrize("fe, o", [("Fe", "O"), (Element.Fe, Element.O)])
def test_validated_entry_as_dict_with_oxidation_states(fe, o):
    entry = TypeAdapter(ComputedEntryType).validate_python(
        {
            "@module": "pymatgen.entries.computed_entries",
            "@class": "ComputedEntry",
            "composition": {"Fe": 2.0, "O": 3.0},
            "energy": -38.0,
            "correction": 0.0,
            "data": {"oxidation_states": {fe: 3.0, o: -2.0}},
        }
    )
    assert entry.as_dict()["data"]["oxidation_states"] == {"Fe": 3.0, "O": -2.0}
