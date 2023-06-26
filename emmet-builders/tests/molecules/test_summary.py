import pytest

from maggma.stores import JSONStore, MemoryStore

from emmet.builders.qchem.molecules import MoleculesAssociationBuilder, MoleculesBuilder
from emmet.builders.molecules.atomic import PartialChargesBuilder, PartialSpinsBuilder
from emmet.builders.molecules.bonds import BondingBuilder
from emmet.builders.molecules.metal_binding import MetalBindingBuilder
from emmet.builders.molecules.orbitals import OrbitalBuilder
from emmet.builders.molecules.redox import RedoxBuilder
from emmet.builders.molecules.thermo import ThermoBuilder
from emmet.builders.molecules.vibration import VibrationBuilder
from emmet.builders.molecules.summary import SummaryBuilder


@pytest.fixture(scope="session")
def tasks(test_dir):
    return JSONStore(test_dir / "lithium_carbonate_tasks.json.gz")


@pytest.fixture(scope="session")
def mols(tasks):
    assoc_store = MemoryStore(key="molecule_id")
    stage_one = MoleculesAssociationBuilder(tasks=tasks, assoc=assoc_store)
    stage_one.run()

    mol_store = MemoryStore(key="molecule_id")
    stage_two = MoleculesBuilder(assoc=assoc_store, molecules=mol_store)
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
def metal_binding(test_dir):
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


def test_summary_doc(
    tasks,
    mols,
    charges,
    spins,
    bonds,
    metal_binding,
    orbitals,
    redox,
    thermo,
    vibes,
    summary,
):
    charge_build = PartialChargesBuilder(tasks, mols, charges)
    charge_build.run()

    spins_build = PartialSpinsBuilder(tasks, mols, spins)
    spins_build.run()

    bonds_build = BondingBuilder(tasks, mols, bonds)
    bonds_build.run()

    orb_build = OrbitalBuilder(tasks, mols, orbitals)
    orb_build.run()

    thermo_build = ThermoBuilder(tasks, mols, thermo)
    thermo_build.run()

    redox_build = RedoxBuilder(tasks, mols, thermo, redox)
    redox_build.run()

    metal_binding_build = MetalBindingBuilder(
        mols, charges, spins, bonds, thermo, metal_binding
    )
    metal_binding_build.run()

    vibe_build = VibrationBuilder(tasks, mols, vibes)
    vibe_build.run()

    builder = SummaryBuilder(
        molecules=mols,
        charges=charges,
        spins=spins,
        bonds=bonds,
        metal_binding=metal_binding,
        orbitals=orbitals,
        redox=redox,
        thermo=thermo,
        vibes=vibes,
        summary=summary,
    )
    builder.run()

    assert summary.count() == 25
