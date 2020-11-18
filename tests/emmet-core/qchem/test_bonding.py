import pytest

from pymatgen.core.periodic_table import Element
from pymatgen.analysis.graphs import MoleculeGraph
from pymatgen.analysis.local_env import OpenBabelNN

from emmet.stubs import Molecule
from emmet.core.qchem.bonding import Bonding


@pytest.fixture
def g2(test_dir):
    g2_mol = Molecule.from_file(test_dir / "molecules" / "diglyme.xyz")
    return g2_mol


def test_from_molecule(g2):
    g2_bonding = Bonding.from_molecule("test", g2)

    assert g2_bonding.atom_types == {
        0: Element("C"),
        1: Element("O"),
        2: Element("C"),
        3: Element("C"),
        4: Element("O"),
        5: Element("C"),
        6: Element("C"),
        7: Element("O"),
        8: Element("C"),
        9: Element("H"),
        10: Element("H"),
        11: Element("H"),
        12: Element("H"),
        13: Element("H"),
        14: Element("H"),
        15: Element("H"),
        16: Element("H"),
        17: Element("H"),
        18: Element("H"),
        19: Element("H"),
        20: Element("H"),
        21: Element("H"),
        22: Element("H"),
    }

    assert g2_bonding.bonding == g2_bonding.covalent_bonding == g2_bonding.babel_bonding

    assert g2_bonding.bonding == {
        (0, 1),
        (0, 9),
        (0, 10),
        (0, 11),
        (1, 2),
        (2, 3),
        (2, 12),
        (2, 13),
        (3, 4),
        (3, 14),
        (3, 15),
        (4, 5),
        (5, 6),
        (5, 16),
        (5, 17),
        (6, 7),
        (6, 18),
        (6, 19),
        (7, 8),
        (8, 20),
        (8, 21),
        (8, 22),
    }

    assert g2_bonding.bond_types == {
        (Element("H"), Element("C")),
        (Element("C"), Element("C")),
        (Element("C"), Element("O")),
    }

    crit = {(0, 1), (0, 9)}
    g2_bond_critic = Bonding.from_molecule("test", g2, critic_bonds=crit)
    assert g2_bond_critic.covalent_bonding == g2_bonding.covalent_bonding
    assert g2_bond_critic.bonding == crit


def test_from_molecule_graph(g2):
    g2_from_mol = Bonding.from_molecule("test", g2)
    g2_mg = MoleculeGraph.with_local_env_strategy(g2, OpenBabelNN())
    g2_from_mg = Bonding.from_molecule_graph("test", g2_mg)

    assert g2_from_mol.bonding == g2_from_mg.bonding

    edges = {(0, 1): None, (0, 9): None}
    custom_mg = MoleculeGraph.with_edges(g2, edges)
    custom_bond = Bonding.from_molecule_graph("test", custom_mg)
    assert custom_bond.covalent_bonding == g2_from_mg.covalent_bonding
    assert custom_bond.bonding == set(edges.keys())

