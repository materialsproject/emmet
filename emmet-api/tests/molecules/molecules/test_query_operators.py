import os
import pytest

from emmet.api.core.settings import MAPISettings
from emmet.api.routes.molecules.molecules.query_operators import (
    FormulaQuery,
    ChemsysQuery,
    CompositionElementsQuery,
    ChargeSpinQuery,
    DeprecationQuery,
    MultiTaskIDQuery,
    MultiMPculeIDQuery,
    FindMoleculeQuery,
    CalcMethodQuery,
    HashQuery,
    StringRepQuery,
)
from pymatgen.core.structure import Molecule

try:
    from openbabel import openbabel
except ImportError:
    openbabel = None


def test_formula_query():
    op = FormulaQuery()
    assert op.query("C1 Li2 O3") == {"criteria": {"formula_alphabetical": "C1 Li2 O3"}}


def test_chemsys_query():
    op = ChemsysQuery()
    assert op.query("O-C") == {"criteria": {"chemsys": "C-O"}}

    assert op.query("C-*") == {
        "criteria": {"nelements": 2, "composition_reduced.C": {"$exists": True}}
    }


def test_composition_query():
    eles = ["C", "O"]
    neles = ["N", "P"]

    op = CompositionElementsQuery()
    assert op.query(elements=",".join(eles), exclude_elements=",".join(neles)) == {
        "criteria": {
            "composition.C": {"$exists": True},
            "composition.O": {"$exists": True},
            "composition.N": {"$exists": False},
            "composition.P": {"$exists": False},
        }
    }


def test_charge_spin_query():
    op = ChargeSpinQuery()
    assert op.query(charge=1, spin_multiplicity=2) == {
        "criteria": {"charge": 1, "spin_multiplicity": 2}
    }


def test_deprecation_query():
    op = DeprecationQuery()
    assert op.query(True) == {"criteria": {"deprecated": True}}


def test_multi_task_id_query():
    op = MultiTaskIDQuery()
    assert op.query(task_ids="mpcule-149, mpcule-13") == {
        "criteria": {"task_ids": {"$in": ["mpcule-149", "mpcule-13"]}}
    }


def test_multi_mpculeid_query():
    op = MultiMPculeIDQuery()
    assert op.query(
        molecule_ids="21d752f3018fd3c4eba7a9ce7a37b8c8-C1F1Mg1N1O1S2-1-2, 542d9adc3163002fe8dfe6d226875dde-C3H5Li2O3-0-2"
    ) == {
        "criteria": {
            "molecule_id": {
                "$in": [
                    "21d752f3018fd3c4eba7a9ce7a37b8c8-C1F1Mg1N1O1S2-1-2",
                    "542d9adc3163002fe8dfe6d226875dde-C3H5Li2O3-0-2",
                ]
            }
        }
    }

    assert op.query(
        molecule_ids="21d752f3018fd3c4eba7a9ce7a37b8c8-C1F1Mg1N1O1S2-1-2"
    ) == {
        "criteria": {
            "molecule_id": "21d752f3018fd3c4eba7a9ce7a37b8c8-C1F1Mg1N1O1S2-1-2"
        }
    }


@pytest.mark.skipif(
    openbabel is None, reason="openbabel must be installed to use FindMoleculeQuery."
)
def test_find_molecule_query():
    op = FindMoleculeQuery()

    mol = Molecule.from_file(
        os.path.join(MAPISettings().TEST_FILES, "test_molecule.xyz")
    )
    query = {
        "criteria": {
            "composition": dict(mol.composition),
            "charge": int(mol.charge),
            "spin_multiplicity": int(mol.spin_multiplicity),
        }
    }
    assert (
        op.query(
            molecule=mol.as_dict(),
            tolerance=0.01,
            charge=0,
            spin_multiplicity=1,
            _limit=1,
        )
        == query
    )

    docs = [
        {
            "molecule": mol.as_dict(),
            "molecule_id": "f9eff23899e37989eb800214ea1d54d4-C1F4Li1O3P1-0-1",
        }
    ]

    pp = op.post_process(docs, query)[0]
    assert pp["molecule_id"] == "f9eff23899e37989eb800214ea1d54d4-C1F4Li1O3P1-0-1"
    assert pp["rmsd"] < 1e-15


def test_calc_method_query():
    op = CalcMethodQuery()

    assert op.query(
        level_of_theory="wB97X-V/def2-TZVPPD/SMD",
        solvent="SOLVENT=THF",
        lot_solvent="wB97X-V/def2-TZVPPD/SMD(SOLVENT=THF)",
    ) == {
        "criteria": {
            "unique_levels_of_theory": "wB97X-V/def2-TZVPPD/SMD",
            "unique_lot_solvents": "wB97X-V/def2-TZVPPD/SMD(SOLVENT=THF)",
            "unique_solvents": "SOLVENT=THF",
        }
    }


def test_hash_query():
    op = HashQuery()

    assert op.query(
        species_hash="ea83c62377feef8c8c3190562e13ffd6",
        coord_hash="5a0282381090c5c9646d03891133d8c9",
    ) == {
        "criteria": {
            "species_hash": "ea83c62377feef8c8c3190562e13ffd6",
            "coord_hash": "5a0282381090c5c9646d03891133d8c9",
        }
    }


def test_string_rep_query():
    op = StringRepQuery()

    assert op.query(inchi="InChI=1S/C2H3NO3/c3-1(4)2(5)6/h(H2,3,4)(H,5,6)") == {
        "criteria": {"inchi": "InChI=1S/C2H3NO3/c3-1(4)2(5)6/h(H2,3,4)(H,5,6)"}
    }
