import pytest
from pymatgen.analysis.dimensionality import get_structure_components
from pymatgen.analysis.local_env import CrystalNN

from emmet.core.featurization.robocrys.condense.component import (
    filter_molecular_components,
)
from emmet.core.featurization.robocrys.condense.molecule import MoleculeNamer

try:
    from openbabel import openbabel
except Exception:
    openbabel = None


@pytest.fixture
def methylammonium(test_structures):
    mapi = CrystalNN().get_bonded_structure(test_structures["mapi"].copy())
    mapi_components = get_structure_components(mapi, inc_molecule_graph=True)
    mol_components, _ = filter_molecular_components(mapi_components)
    return mol_components[0]["molecule_graph"]


def test_init():
    """Test initialising MoleculeNamer."""
    mn = MoleculeNamer()
    assert mn

    mn = MoleculeNamer(use_online_pubchem=False)
    assert mn


@pytest.mark.skipif(not openbabel, reason="Openbabel not installed.")
def test_molecule_graph_to_smiles(methylammonium):
    """Test converting a molecule graph to SMILES string."""
    smiles = MoleculeNamer.molecule_graph_to_smiles(methylammonium)
    assert smiles == "C[NH3]"


@pytest.mark.skipif(not openbabel, reason="Openbabel not installed.")
def test_get_name_from_pubchem():
    """Test downloading the molecule name from Pubchem."""
    mn = MoleculeNamer()
    name = mn.get_name_from_pubchem("C[NH3]")
    assert name == "methylammonium"


@pytest.mark.skipif(not openbabel, reason="Openbabel not installed.")
def test_get_name_from_molecule_graph(methylammonium):
    """Test getting a molecule name from the molecule graph."""
    mn = MoleculeNamer()
    name = mn.get_name_from_molecule_graph(methylammonium)
    assert name == "methylammonium"

    # test iupac naming source
    mn = MoleculeNamer(name_preference=("iupac",))
    name = mn.get_name_from_molecule_graph(methylammonium)
    assert name == "methylazanium"
