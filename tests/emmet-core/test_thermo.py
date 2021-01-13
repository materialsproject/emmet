import pytest
from monty.serialization import MontyDecoder
from pymatgen.entries.entry_tools import EntrySet

from emmet.core.thermo import ThermoDoc


@pytest.fixture
def entries():
    return MontyDecoder().process_decoded(
        [
            {
                "@module": "pymatgen.entries.computed_entries",
                "@class": "ComputedEntry",
                "correction": 0.0,
                "entry_id": "test-1",
                "energy": -382.146593528,
                "composition": {"Fe": 24.0, "O": 32.0},
                "name": "Fe3O4",
                "attribute": None,
                "@version": "2020.4.29",
            },
            {
                "@module": "pymatgen.entries.computed_entries",
                "@class": "ComputedEntry",
                "correction": 0.0,
                "entry_id": "test-2",
                "energy": -270.38765404,
                "composition": {"Fe": 16.0, "O": 24.0},
                "name": "Fe2O3",
                "attribute": None,
                "@version": "2020.4.29",
            },
            {
                "@module": "pymatgen.entries.computed_entries",
                "@class": "ComputedEntry",
                "correction": 0.0,
                "entry_id": "test-3",
                "energy": -92.274692568,
                "composition": {"O": 24.0},
                "name": "O",
                "attribute": None,
                "@version": "2020.4.29",
            },
            {
                "@module": "pymatgen.entries.computed_entries",
                "@class": "ComputedEntry",
                "correction": 0.0,
                "entry_id": "test-4",
                "energy": -13.00419661,
                "composition": {"Fe": 2.0},
                "name": "Fe",
                "attribute": None,
                "@version": "2020.4.29",
            },
            {
                "@module": "pymatgen.entries.computed_entries",
                "@class": "ComputedEntry",
                "correction": 0.0,
                "entry_id": "unstable",
                "energy": -1080.82678592,
                "composition": {"Fe": 64.0, "O": 96.0},
                "name": "Fe2O3",
                "attribute": None,
                "@version": "2020.4.29",
            },
        ]
    )


@pytest.mark.xfail
def test_from_entries(entries):
    docs = ThermoDoc.from_entries(entries)

    assert len(docs) == len(entries)

    assert all([d.energy_type == "Unknown" for d in docs])
    unstable_doc = next(d for d in docs if d.material_id == "unstable")
    assert unstable_doc.is_stable is False
    assert all([d.is_stable for d in docs if d != unstable_doc])
