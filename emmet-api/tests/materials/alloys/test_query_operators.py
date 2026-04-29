# Test alloy query operators

from emmet.api.utils import process_identifiers

from emmet.api.routes.materials.alloys.query_operators import (
    MaterialIDsSearchQuery,
    FormulaSearchQuery,
)


def test_material_id_query():

    op = MaterialIDsSearchQuery()
    # test single ID
    idxs = "mp-70"
    assert op.query(material_ids=idxs) == {
        "criteria": {
            "$or": [
                {k: {"$in": process_identifiers(idxs)}}
                for k in (
                    "alloy_pair.id_a",
                    "alloy_pair.id_b",
                )
            ]
        }
    }

    idxs = "mp-70,mp-80, mp-1000,    mp-4500"
    assert op.query(material_ids=idxs) == {
        "criteria": {
            "$or": [
                {k: {"$in": process_identifiers(idxs)}}
                for k in (
                    "alloy_pair.id_a",
                    "alloy_pair.id_b",
                )
            ]
        }
    }


def test_formula_query():

    op = FormulaSearchQuery()

    # Single formula
    formula = "LiFeO3"
    assert op.query(formulae=formula) == {
        "criteria": {
            "$or": [{f"alloy_pair.formula_{k}": {"$in": [formula]}} for k in ("a", "b")]
        }
    }

    # multiple formulas
    formulae = "LiFeO3, NaCl,  KF"
    assert op.query(formulae=formulae) == {
        "criteria": {
            "$or": [
                {
                    f"alloy_pair.formula_{k}": {
                        "$in": [f.strip() for f in formulae.split(",")]
                    }
                }
                for k in ("a", "b")
            ]
        }
    }
