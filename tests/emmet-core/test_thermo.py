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
                "energy": -6.824046313,
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
                "energy": -6.759691351,
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
                "energy": -3.844778857,
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
                "energy": -6.502098305,
                "composition": {"Fe": 2.0},
                "name": "Fe",
                "attribute": None,
                "@version": "2020.4.29",
            },
            {
                "@module": "pymatgen.entries.computed_entries",
                "@class": "ComputedEntry",
                "correction": 0.0,
                "entry_id": "test-5",
                "energy": -6.755167412,
                "composition": {"Fe": 64.0, "O": 96.0},
                "name": "Fe2O3",
                "attribute": None,
                "@version": "2020.4.29",
            },
        ]
    )


def test_from_entries(entries):
    docs = ThermoDoc.from_entries(entries)
    assert len(docs) == len(entries)

    assert all([d.energy_type == "Unknown" for d in docs])
