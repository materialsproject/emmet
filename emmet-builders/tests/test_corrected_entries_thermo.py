from pathlib import Path

import pytest
from maggma.stores import JSONStore, MemoryStore
from monty.serialization import dumpfn, loadfn

from emmet.builders.materials.corrected_entries import CorrectedEntriesBuilder
from emmet.builders.materials.thermo import ThermoBuilder
from emmet.builders.vasp.materials import MaterialsBuilder


@pytest.fixture(scope="session")
def tasks_store(test_dir):
    return JSONStore(test_dir / "test_si_tasks.json.gz")


@pytest.fixture(scope="session")
def materials_store(tasks_store):
    materials_store = MemoryStore(key="material_id")
    builder = MaterialsBuilder(tasks=tasks_store, materials=materials_store)
    builder.run()
    return materials_store


@pytest.fixture(scope="session")
def corrected_entries_store():
    return MemoryStore(key="chemsys")


@pytest.fixture
def thermo_store():
    return MemoryStore(key="thermo_id")


@pytest.fixture
def phase_diagram_store():
    return MemoryStore(key="chemsys")


def test_corrected_entries_builder(corrected_entries_store, materials_store):

    builder = CorrectedEntriesBuilder(materials=materials_store, corrected_entries=corrected_entries_store)
    builder.run()

    assert corrected_entries_store.count() == 1
    assert corrected_entries_store.count({"chemsys": "Si"}) == 1


def test_corrected_entries_serialization(tmpdir):
    builder = CorrectedEntriesBuilder(MemoryStore(), MemoryStore(), MemoryStore())

    dumpfn(builder.as_dict(), Path(tmpdir) / "test.json")
    loadfn(Path(tmpdir) / "test.json")


def test_thermo_builder(corrected_entries_store, thermo_store, phase_diagram_store):

    builder = ThermoBuilder(
        thermo=thermo_store, corrected_entries=corrected_entries_store, phase_diagram=phase_diagram_store
    )
    builder.run()

    assert thermo_store.count() == 1
    assert thermo_store.count({"material_id": "mp-149"}) == 1

    assert phase_diagram_store.count() == 1


def test_thermo_serialization(tmpdir):
    builder = ThermoBuilder(MemoryStore(), MemoryStore(), MemoryStore())

    dumpfn(builder.as_dict(), Path(tmpdir) / "test.json")
    loadfn(Path(tmpdir) / "test.json")
