import pytest
from maggma.stores import JSONStore, MemoryStore

from emmet.builders.qchem.molecules import MoleculesAssociationBuilder, MoleculesBuilder
from emmet.builders.molecules.thermo import ThermoBuilder


__author__ = "Evan Spotte-Smith <ewcspottesmith@lbl.gov>"


@pytest.fixture(scope="session")
def tasks_store(test_dir):
    return JSONStore(test_dir / "C3H4Li1O3.json.gz")


@pytest.fixture(scope="session")
def mol_store(tasks_store):
    assoc_store = MemoryStore(key="molecule_id")
    stage_one = MoleculesAssociationBuilder(tasks=tasks_store, assoc=assoc_store)
    stage_one.run()

    mol_store = MemoryStore(key="molecule_id")
    stage_two = MoleculesBuilder(assoc=assoc_store, molecules=mol_store, prefix="libe")
    stage_two.run()

    return mol_store


@pytest.fixture(scope="session")
def thermo_store():
    return MemoryStore()


@pytest.mark.skip(reason="Waiting on molecule update.")
def test_thermo_builder(tasks_store, mol_store, thermo_store):
    builder = ThermoBuilder(tasks_store, mol_store, thermo_store)
    builder.run()

    assert thermo_store.count() == 48
    assert thermo_store.count({"vibrational_enthalpy": None}) == 0
