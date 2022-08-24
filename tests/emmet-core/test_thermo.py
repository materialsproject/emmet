import pytest
from monty.serialization import MontyDecoder
from monty.serialization import loadfn
from emmet.core.thermo import ThermoDoc


@pytest.fixture(scope="session")
def Fe3O4_structure(test_dir):
    structure = loadfn(test_dir / "thermo/Fe3O4_structure.json")
    return structure


@pytest.fixture(scope="session")
def Fe2O3a_structure(test_dir):
    structure = loadfn(test_dir / "thermo/Fe2O3a_structure.json")
    return structure


@pytest.fixture(scope="session")
def Fe2O3b_structure(test_dir):
    structure = loadfn(test_dir / "thermo/Fe2O3b_structure.json")
    return structure


@pytest.fixture(scope="session")
def Fe_structure(test_dir):
    structure = loadfn(test_dir / "thermo/Fe_structure.json")
    return structure


@pytest.fixture(scope="session")
def O_structure(test_dir):
    structure = loadfn(test_dir / "thermo/O_structure.json")
    return structure


@pytest.fixture
def entries(
    Fe3O4_structure, Fe2O3a_structure, Fe2O3b_structure, Fe_structure, O_structure
):
    return MontyDecoder().process_decoded(
        [
            {
                "@module": "pymatgen.entries.computed_entries",
                "@class": "ComputedStructureEntry",
                "correction": 0.0,
                "structure": Fe3O4_structure.as_dict(),
                "entry_id": "mp-1",
                "energy": -382.146593528,
                "composition": {"Fe": 24.0, "O": 32.0},
                "name": "Fe3O4",
                "data": {
                    "material_id": "mp-1",
                    "run_type": "Unknown",
                    "task_id": "mp-10",
                },
                "attribute": None,
                "@version": "2020.4.29",
            },
            {
                "@module": "pymatgen.entries.computed_entries",
                "@class": "ComputedStructureEntry",
                "correction": 0.0,
                "structure": Fe2O3a_structure.as_dict(),
                "entry_id": "mp-2",
                "energy": -270.38765404,
                "composition": {"Fe": 16.0, "O": 24.0},
                "name": "Fe2O3",
                "data": {
                    "material_id": "mp-2",
                    "run_type": "Unknown",
                    "task_id": "mp-20",
                },
                "attribute": None,
                "@version": "2020.4.29",
            },
            {
                "@module": "pymatgen.entries.computed_entries",
                "@class": "ComputedStructureEntry",
                "correction": 0.0,
                "structure": O_structure.as_dict(),
                "entry_id": "mp-3",
                "energy": -92.274692568,
                "composition": {"O": 24.0},
                "name": "O",
                "data": {
                    "material_id": "mp-3",
                    "run_type": "Unknown",
                    "task_id": "mp-30",
                },
                "attribute": None,
                "@version": "2020.4.29",
            },
            {
                "@module": "pymatgen.entries.computed_entries",
                "@class": "ComputedStructureEntry",
                "correction": 0.0,
                "structure": Fe_structure.as_dict(),
                "entry_id": "mp-4",
                "energy": -13.00419661,
                "composition": {"Fe": 2.0},
                "name": "Fe",
                "data": {
                    "material_id": "mp-4",
                    "run_type": "Unknown",
                    "task_id": "mp-40",
                },
                "attribute": None,
                "@version": "2020.4.29",
            },
            {
                "@module": "pymatgen.entries.computed_entries",
                "@class": "ComputedStructureEntry",
                "correction": 0.0,
                "structure": Fe2O3b_structure.as_dict(),
                "entry_id": "mp-5",
                "energy": -1080.82678592,
                "composition": {"Fe": 64.0, "O": 96.0},
                "name": "Fe2O3",
                "attribute": None,
                "data": {
                    "material_id": "mp-5",
                    "run_type": "Unknown",
                    "task_id": "mp-50",
                },
                "@version": "2020.4.29",
            },
        ]
    )


def test_from_entries(entries):
    docs, pd = ThermoDoc.from_entries(entries, thermo_type="UNKNOWN", deprecated=False)

    assert len(docs) == len(entries)

    assert all([d.energy_type == "Unknown" for d in docs])
    unstable_doc = next(d for d in docs if d.material_id == "mp-5")
    assert unstable_doc.is_stable is False
    assert all([d.is_stable for d in docs if d != unstable_doc])
