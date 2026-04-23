import os

from pymatgen.core.structure import Structure
import pytest

from emmet.api.core.settings import MAPISettings
from emmet.api.query_operator import MultiTaskIDQuery
from emmet.api.routes.materials.materials.query_operators import (
    BlessedCalcsQuery,
    ChemsysQuery,
    DeprecationQuery,
    ElementsQuery,
    FindStructureQuery,
    FormulaAutoCompleteQuery,
    FormulaQuery,
    MultiMaterialIDQuery,
    SymmetryQuery,
)
from emmet.core.symmetry import CrystalSystem, _get_space_group_symbol_to_number_mapping
from emmet.core.vasp.calc_types import RunType


def test_blessed_calcs_query():

    op = BlessedCalcsQuery()
    for mapped, possible_user_input in {
        "GGA": ["GGA", RunType.GGA, RunType.PBE],
        "GGA_U": ["GGA_U", RunType.PBE_U],
        "R2SCAN": ["R2SCAN", RunType.r2SCAN],
        "SCAN": ["SCAN", RunType.SCAN],
        "HSE": ["HSE", RunType.HSE06],
    }.items():

        assert all(
            op.query(run_type=user_inp, energy_min=None, energy_max=None)
            == {"criteria": {f"entries.{mapped}": {"$ne": None}}}
            for user_inp in possible_user_input
        )

        assert all(
            op.query(
                run_type=user_inp,
                energy_min=0.0,
                energy_max=None,
            )
            == {"criteria": {f"entries.{mapped}.energy": {"$gte": 0.0}}}
            for user_inp in possible_user_input
        )

        assert all(
            op.query(
                run_type=user_inp,
                energy_min=None,
                energy_max=5.0,
            )
            == {"criteria": {f"entries.{mapped}.energy": {"$lte": 5.0}}}
            for user_inp in possible_user_input
        )

        assert all(
            op.query(
                run_type=user_inp,
                energy_min=0.0,
                energy_max=5.0,
            )
            == {"criteria": {f"entries.{mapped}.energy": {"$gte": 0.0, "$lte": 5.0}}}
            for user_inp in possible_user_input
        )


def test_formula_query():
    op = FormulaQuery()
    assert op.query("Si2O4") == {
        "criteria": {
            "composition_reduced.O": 2.0,
            "composition_reduced.Si": 1.0,
            "nelements": 2,
        }
    }


def test_chemsys_query():
    op = ChemsysQuery()
    assert op.query("Si-O") == {"criteria": {"chemsys": "O-Si"}}

    assert op.query("Si-*") == {
        "criteria": {"nelements": 2, "composition_reduced.Si": {"$exists": True}}
    }


def test_elements_query():
    eles = ["Si", "O"]
    neles = ["N", "P"]

    op = ElementsQuery()
    assert op.query(elements=",".join(eles), exclude_elements=",".join(neles)) == {
        "criteria": {
            "composition_reduced.Si": {"$exists": True},
            "composition_reduced.O": {"$exists": True},
            "composition_reduced.N": {"$exists": False},
            "composition_reduced.P": {"$exists": False},
        }
    }


def test_deprecation_query():
    op = DeprecationQuery()
    assert op.query(True) == {"criteria": {"deprecated": True}}


def test_symmetry_query():
    op = SymmetryQuery()

    for aux_query in [
        {"spacegroup_number": 221},
        {"spacegroup_symbol": "Pm-3m"},
        {"spacegroup_number": 221, "spacegroup_symbol": "Pm-3m"},
    ]:
        # Assert correct reduction of space group symbol to number
        assert op.query(crystal_system=CrystalSystem.cubic, **aux_query) == {
            "criteria": {
                "symmetry.crystal_system": "Cubic",
                "symmetry.number": 221,
            }
        }

    with pytest.raises(
        ValueError, match=r"inequivalent space group number.*and symbol"
    ):
        op.query(spacegroup_number=221, spacegroup_symbol="Im-3m")

    with pytest.raises(ValueError, match="inequivalent space group number.*and symbol"):
        op.query(spacegroup_number="229,221", spacegroup_symbol="Im-3m")

    assert op.query(spacegroup_number="229,221") == {
        "criteria": {"symmetry.number": {"$in": [221, 229]}}
    }

    with pytest.raises(ValueError, match="Unknown space group symbol.*apple, pear"):
        op.query(spacegroup_symbol="pear,apple,Pnma")

    with pytest.raises(
        ValueError, match="inequivalent space group number.*and crystal system"
    ):
        op.query(spacegroup_number=221, crystal_system="Trigonal")

    with pytest.raises(
        ValueError, match="inequivalent space group number.*and crystal system"
    ):
        assert op.query(spacegroup_number="229,221", crystal_system="Trigonal")

    with pytest.raises(
        ValueError, match="inequivalent space group number.*and crystal system"
    ):
        assert op.query(crystal_system="Trigonal", spacegroup_symbol="Im-3m")

    crystal_systems = ["ortho", "mono"]
    cs = [CrystalSystem[x].value for x in crystal_systems]
    assert op.query(crystal_system=",".join(cs)) == {
        "criteria": {"symmetry.crystal_system": {"$in": cs}}
    }

    with pytest.raises(ValueError, match="You have queried for 7 crystal systems"):
        op.query(crystal_system=",".join(cs.value for cs in CrystalSystem))

    with pytest.raises(ValueError, match="You have queried for 230 space groups"):
        op.query(spacegroup_number=",".join(str(1 + x) for x in range(230)))

    sgn_to_sgs = {v: k for k, v in _get_space_group_symbol_to_number_mapping().items()}
    with pytest.raises(ValueError, match="You have queried for 230 space groups"):
        op.query(
            spacegroup_number=",".join(str(1 + x) for x in range(115)),
            spacegroup_symbol=",".join(sgn_to_sgs[1 + x] for x in range(115, 230)),
        )


def test_multi_task_id_query():
    op = MultiTaskIDQuery()
    assert op.query(task_ids="mp-149, mp-13") == {
        "criteria": {"task_ids": {"$in": ["mp-149", "mp-13"]}}
    }


def test_multi_material_id_query():
    op = MultiMaterialIDQuery()
    assert op.query(material_ids="mp-149, mp-13") == {
        "criteria": {"material_id": {"$in": ["mp-149", "mp-13"]}}
    }

    assert op.query(material_ids="mp-149") == {"criteria": {"material_id": "mp-149"}}


def test_find_structure_query():
    op = FindStructureQuery()

    structure = Structure.from_file(
        os.path.join(MAPISettings().TEST_FILES, "Si_mp_149.cif"), primitive=True
    )
    query = {
        "criteria": {"composition_reduced": dict(structure.composition.to_reduced_dict)}
    }
    assert (
        op.query(
            structure=structure.as_dict(), ltol=0.2, stol=0.3, angle_tol=5, _limit=1
        )
        == query
    )

    docs = [{"structure": structure.as_dict(), "material_id": "mp-149"}]

    assert op.post_process(docs, query) == [
        {
            "material_id": "mp-149",
            "normalized_rms_displacement": 0,
            "max_distance_paired_sites": 0,
        }
    ]


def test_formula_auto_complete_query():
    op = FormulaAutoCompleteQuery()

    eles = ["Si", "O"]

    pipeline = [
        {
            "$search": {
                "index": "formula_autocomplete",
                "text": {"path": "formula_pretty", "query": ["SiO", "OSi"]},
            }
        },
        {
            "$project": {
                "_id": 0,
                "formula_pretty": 1,
                "elements": 1,
                "length": {"$strLenCP": "$formula_pretty"},
            }
        },
        {"$match": {"elements": {"$all": eles}, "length": {"$gte": 3}}},
        {"$limit": 10},
        {"$sort": {"length": 1}},
        {"$project": {"elements": 0, "length": 0}},
    ]

    assert op.query(formula="".join(eles), limit=10) == {"pipeline": pipeline}

    eles = ["Si"]

    pipeline = [
        {
            "$search": {
                "index": "formula_autocomplete",
                "text": {"path": "formula_pretty", "query": ["Si"]},
            }
        },
        {
            "$project": {
                "_id": 0,
                "formula_pretty": 1,
                "elements": 1,
                "length": {"$strLenCP": "$formula_pretty"},
            }
        },
        {"$match": {"elements": {"$all": eles}, "length": {"$gte": 2}}},
        {"$limit": 10},
        {"$sort": {"length": 1}},
        {"$project": {"elements": 0, "length": 0}},
    ]

    assert op.query(formula="".join(eles), limit=10) == {"pipeline": pipeline}
