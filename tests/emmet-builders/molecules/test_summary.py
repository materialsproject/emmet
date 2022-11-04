import json
import datetime
import copy

import pytest

from monty.io import zopen
from monty.serialization import loadfn

from maggma.stores import JSONStore, MemoryStore

from emmet.builders.qchem.molecules import MoleculesAssociationBuilder, MoleculesBuilder
from emmet.builders.molecules.atomic import PartialChargesBuilder, PartialSpinsBuilder
from emmet.builders.molecules.bonds import BondingBuilder
from emmet.builders.molecules.orbitals import OrbitalBuilder
from emmet.builders.molecules.redox import RedoxBuilder
from emmet.builders.molecules.thermo import ThermoBuilder
from emmet.builders.molecules.vibration import VibrationBuilder
from emmet.builders.molecules.summary import SummaryBuilder


@pytest.fixture(scope="session")
def tasks(test_dir):
    return JSONStore(test_dir / "builder_task_set.json.gz")


@pytest.fixture(scope="session")
def mols(tasks):
    assoc_store = MemoryStore(key="molecule_id")
    stage_one = MoleculesAssociationBuilder(tasks=tasks, assoc=assoc_store)
    stage_one.run()

    mol_store = MemoryStore(key="molecule_id")
    stage_two = MoleculesBuilder(assoc=assoc_store, molecules=mol_store, prefix="libe")
    stage_two.run()

    return mol_store


@pytest.fixture(scope="session")
def charges(test_dir):
    return MemoryStore(key="molecule_id")


@pytest.fixture(scope="session")
def spins(test_dir):
    return MemoryStore(key="molecule_id")


@pytest.fixture(scope="session")
def bonds(test_dir):
    return MemoryStore(key="molecule_id")


@pytest.fixture(scope="session")
def orbitals(test_dir):
    return MemoryStore(key="molecule_id")


@pytest.fixture(scope="session")
def redox(test_dir):
    return MemoryStore(key="molecule_id")


@pytest.fixture(scope="session")
def thermo(test_dir):
    return MemoryStore(key="molecule_id")


@pytest.fixture(scope="session")
def vibes(test_dir):
    return MemoryStore(key="molecule_id")


@pytest.fixture(scope="session")
def summary():
    return MemoryStore(key="molecule_id")


@pytest.mark.skip(reason="Waiting on molecule update.")
def test_summary_doc(tasks, mols, charges, spins, bonds, orbitals, redox, thermo, vibes, summary):
    charge_build = PartialChargesBuilder(tasks, mols, charges)
    charge_build.run()

    spins_build = PartialSpinsBuilder(tasks, mols, spins)
    spins_build.run()

    bonds_build = BondingBuilder(tasks, mols, bonds)
    bonds_build.run()

    orb_build = OrbitalBuilder(tasks, mols, orbitals)
    orb_build.run()

    redox_build = RedoxBuilder(mols, redox)
    redox_build.run()

    thermo_build = ThermoBuilder(tasks, mols, thermo)
    thermo_build.run()

    vibe_build = VibrationBuilder(tasks, mols, vibes)
    vibe_build.run()

    builder = SummaryBuilder(
        molecules=mols,
        charges=charges,
        spins=spins,
        bonds=bonds,
        orbitals=orbitals,
        redox=redox,
        thermo=thermo,
        vibes=vibes,
        summary=summary,
    )
    builder.run()

    docs = list(summary.query())

    assert len(docs) == 46
