import json
import datetime
import copy

import pytest

from monty.io import zopen
from monty.serialization import loadfn

from emmet.core.qchem.molecule import MoleculeDoc
from emmet.core.molecules.atomic import PartialChargesDoc, PartialSpinsDoc
from emmet.core.molecules.bonds import BondingDoc
from emmet.core.molecules.orbitals import OrbitalDoc
from emmet.core.molecules.redox import RedoxDoc
from emmet.core.molecules.thermo import ThermoDoc
from emmet.core.molecules.vibration import VibrationDoc
from emmet.core.molecules.summary import SummaryDoc


@pytest.fixture(scope="session")
def mols(test_dir):

    mols = [MoleculeDoc(**x) for x in loadfn(test_dir / "builder_mols_set.json")]

    return mols


@pytest.fixture(scope="session")
def charges(test_dir):

    charges = [PartialChargesDoc(**x) for x in loadfn(test_dir / "builder_charges_set.json")]

    return charges


@pytest.fixture(scope="session")
def spins(test_dir):

    spins = [PartialSpinsDoc(**x) for x in loadfn(test_dir / "builder_spins_set.json")]

    return spins


@pytest.fixture(scope="session")
def bonds(test_dir):

    bonds = [BondingDoc(**x) for x in loadfn(test_dir / "builder_bonding_set.json")]

    return bonds


@pytest.fixture(scope="session")
def orbitals(test_dir):

    orbitals = [OrbitalDoc(**x) for x in loadfn(test_dir / "builder_orbitals_set.json")]

    return orbitals


@pytest.fixture(scope="session")
def redox(test_dir):

    redox = [RedoxDoc(**x) for x in loadfn(test_dir / "builder_redox_set.json")]

    return redox


@pytest.fixture(scope="session")
def thermo(test_dir):

    thermo = [ThermoDoc(**x) for x in loadfn(test_dir / "builder_thermo_set.json")]

    return thermo


@pytest.fixture(scope="session")
def vibes(test_dir):

    vibes = [VibrationDoc(**x) for x in loadfn(test_dir / "builder_vibes_set.json")]

    return vibes


def test_summary_doc():
    pass
