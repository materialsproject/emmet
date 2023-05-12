from emmet.api.routes.materials.materials.utils import (
    formula_to_criteria,
    chemsys_to_criteria,
)
import pytest


def test_formula_to_criteria():
    # Regular formula
    assert formula_to_criteria("Cr2O3") == {
        "composition_reduced.Cr": 2.0,
        "composition_reduced.O": 3.0,
        "nelements": 2,
    }
    assert formula_to_criteria("Cr2O3, O2Si") == {
        "formula_pretty": {"$in": ["Cr2O3", "SiO2"]}
    }

    # Add wildcard
    assert formula_to_criteria("Cr2*3") == {
        "composition_reduced.Cr": 2.0,
        "formula_anonymous": "A2B3",
    }
    # Anonymous element
    assert formula_to_criteria("A2B3") == {"formula_anonymous": "A2B3"}
    assert formula_to_criteria("A2B3, ABC3") == {
        "formula_anonymous": {"$in": ["A2B3", "ABC3"]}
    }


def test_chemsys_to_criteria():
    # Chemsys
    assert chemsys_to_criteria("Si-O") == {"chemsys": "O-Si"}
    assert chemsys_to_criteria("Si-*") == {"elements": {"$all": ["Si"]}, "nelements": 2}
    assert chemsys_to_criteria("*-*-*") == {"nelements": 3}

    assert chemsys_to_criteria("Si-O, P-Li-Fe") == {
        "chemsys": {"$in": ["O-Si", "Fe-Li-P"]}
    }


@pytest.mark.xfail()
def test_chemsys_to_criteria_multiple_wildcard():
    chemsys_to_criteria("Si-O, Li-Fe-*")


@pytest.mark.xfail()
def test_formula_to_criteria_multiple_wildcard():
    formula_to_criteria("SiO, LiFe*")
