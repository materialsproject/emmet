import pytest
from maggma.stores import JSONStore, MemoryStore

from emmet.builders.qchem.molecules import MoleculesAssociationBuilder, MoleculesBuilder
from emmet.builders.molecules.bonds import BondingBuilder


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
def bonds_store():
    return MemoryStore()


@pytest.mark.skip(reason="Waiting on molecule update.")
def test_bonding_builder(tasks_store, mol_store, bonds_store):
    builder = BondingBuilder(
        tasks_store, mol_store, bonds_store, methods=["critic2", "OpenBabelNN + metal_edge_extender"],
    )
    builder.run()

    assert bonds_store.count() == 90
    assert bonds_store.count({"deprecated": True}) == 0
