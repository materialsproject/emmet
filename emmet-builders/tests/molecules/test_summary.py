import pytest

from maggma.stores import JSONStore, MemoryStore

from emmet.builders.qchem.molecules import MoleculesAssociationBuilder, MoleculesBuilder
from emmet.builders.molecules.atomic import PartialChargesBuilder, PartialSpinsBuilder
from emmet.builders.molecules.bonds import BondingBuilder
from emmet.builders.molecules.electric import ElectricMultipoleBuilder
from emmet.builders.molecules.metal_binding import MetalBindingBuilder
from emmet.builders.molecules.orbitals import OrbitalBuilder
from emmet.builders.molecules.redox import RedoxBuilder
from emmet.builders.molecules.thermo import ThermoBuilder
from emmet.builders.molecules.vibration import VibrationBuilder
from emmet.builders.molecules.summary import SummaryBuilder


@pytest.fixture(scope="session")
def tasks_one(test_dir):
    return JSONStore(test_dir / "lithium_carbonate_tasks.json.gz")


@pytest.fixture(scope="session")
def mols_one(tasks_one):
    assoc_store = MemoryStore(key="molecule_id")
    stage_one = MoleculesAssociationBuilder(tasks=tasks_one, assoc=assoc_store)
    stage_one.run()

    mol_store = MemoryStore(key="molecule_id")
    stage_two = MoleculesBuilder(assoc=assoc_store, molecules=mol_store)
    stage_two.run()

    return mol_store


@pytest.fixture(scope="session")
def tasks_two(test_dir):
    return JSONStore(test_dir / "force_trajectory" / "force_traj_tasks.json.gz")


@pytest.fixture(scope="session")
def mols_two(tasks_two):
    assoc_store = MemoryStore(key="molecule_id")
    stage_one = MoleculesAssociationBuilder(tasks=tasks_two, assoc=assoc_store)
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
def multipoles(test_dir):
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


def test_summary_one(
    tasks_one,
    mols_one,
    charges,
    spins,
    bonds,
    multipoles,
    metal_binding,
    orbitals,
    redox,
    thermo,
    vibes,
    summary,
):
    charge_build = PartialChargesBuilder(tasks_one, mols_one, charges)
    charge_build.run()

    spins_build = PartialSpinsBuilder(tasks_one, mols_one, spins)
    spins_build.run()

    bonds_build = BondingBuilder(tasks_one, mols_one, bonds)
    bonds_build.run()

    orb_build = OrbitalBuilder(tasks_one, mols_one, orbitals)
    orb_build.run()

    multipole_build = ElectricMultipoleBuilder(tasks_one, mols_one, multipoles)
    multipole_build.run()

    thermo_build = ThermoBuilder(tasks_one, mols_one, thermo)
    thermo_build.run()

    redox_build = RedoxBuilder(tasks_one, mols_one, thermo, redox)
    redox_build.run()

    metal_binding_build = MetalBindingBuilder(
        mols_one, charges, spins, bonds, thermo, metal_binding
    )
    metal_binding_build.run()

    vibe_build = VibrationBuilder(tasks_one, mols_one, vibes)
    vibe_build.run()

    builder = SummaryBuilder(
        molecules=mols_one,
        charges=charges,
        spins=spins,
        bonds=bonds,
        multipoles=multipoles,
        metal_binding=metal_binding,
        orbitals=orbitals,
        redox=redox,
        thermo=thermo,
        vibes=vibes,
        summary=summary,
    )
    builder.run()

    assert summary.count() == 25


def test_summary_two(
    tasks_two,
    mols_two,
    charges,
    spins,
    bonds,
    multipoles,
    metal_binding,
    orbitals,
    redox,
    thermo,
    vibes,
    summary,
):
    charge_build = PartialChargesBuilder(tasks_two, mols_two, charges)
    charge_build.run()

    spins_build = PartialSpinsBuilder(tasks_two, mols_two, spins)
    spins_build.run()

    bonds_build = BondingBuilder(tasks_two, mols_two, bonds)
    bonds_build.run()

    orb_build = OrbitalBuilder(tasks_two, mols_two, orbitals)
    orb_build.run()

    multipole_build = ElectricMultipoleBuilder(tasks_two, mols_two, multipoles)
    multipole_build.run()

    thermo_build = ThermoBuilder(tasks_two, mols_two, thermo)
    thermo_build.run()

    redox_build = RedoxBuilder(tasks_two, mols_two, thermo, redox)
    redox_build.run()

    metal_binding_build = MetalBindingBuilder(
        mols_two, charges, spins, bonds, thermo, metal_binding
    )
    metal_binding_build.run()

    vibe_build = VibrationBuilder(tasks_two, mols_two, vibes)
    vibe_build.run()

    builder = SummaryBuilder(
        molecules=mols_two,
        charges=charges,
        spins=spins,
        bonds=bonds,
        multipoles=multipoles,
        metal_binding=metal_binding,
        orbitals=orbitals,
        redox=redox,
        thermo=thermo,
        vibes=vibes,
        summary=summary,
    )
    builder.run()

    assert summary.count() == 33
