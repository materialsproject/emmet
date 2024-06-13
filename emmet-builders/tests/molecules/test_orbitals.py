import pytest
from maggma.stores import JSONStore, MemoryStore

from emmet.builders.qchem.molecules import MoleculesAssociationBuilder, MoleculesBuilder
from emmet.builders.molecules.orbitals import OrbitalBuilder


__author__ = "Evan Spotte-Smith <ewcspottesmith@lbl.gov>"


@pytest.fixture(scope="session")
def tasks_store(test_dir):
    return JSONStore(test_dir / "C2H4.json.gz")


@pytest.fixture(scope="session")
def mol_store(tasks_store):
    assoc_store = MemoryStore(key="molecule_id")
    stage_one = MoleculesAssociationBuilder(tasks=tasks_store, assoc=assoc_store)
    stage_one.run()

    mol_store = MemoryStore(key="molecule_id")
    stage_two = MoleculesBuilder(assoc=assoc_store, molecules=mol_store)
    stage_two.run()

    return mol_store


@pytest.fixture(scope="session")
def orbital_store():
    return MemoryStore()


@pytest.fixture(scope="session")
def new_tasks_store(test_dir):
    return JSONStore(test_dir / "new_orbital_buildtasks.json.gz")


@pytest.fixture(scope="session")
def new_mol_store(new_tasks_store):
    assoc_store = MemoryStore(key="molecule_id")
    stage_one = MoleculesAssociationBuilder(tasks=new_tasks_store, assoc=assoc_store)
    stage_one.run()

    mol_store = MemoryStore(key="molecule_id")
    stage_two = MoleculesBuilder(assoc=assoc_store, molecules=mol_store)
    stage_two.run()

    return mol_store


@pytest.fixture(scope="session")
def new_orbital_store():
    return MemoryStore()


def test_orbital_builder(tasks_store, mol_store, orbital_store):
    builder = OrbitalBuilder(tasks_store, mol_store, orbital_store)
    builder.run()

    assert orbital_store.count() == 20
    assert orbital_store.count({"open_shell": True}) == 9


def test_new_orbitals(new_tasks_store, new_mol_store, new_orbital_store):
    builder = OrbitalBuilder(new_tasks_store, new_mol_store, new_orbital_store)
    builder.run()

    assert new_orbital_store.count() == 19
    assert new_orbital_store.count({"open_shell": True}) == 11
