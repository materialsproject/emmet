from emmet.api.routes.electrodes.utils import (
    electrodes_chemsys_to_criteria,
    electrodes_formula_to_criteria,
)
import pytest


def test_electrodes_formula_to_criteria():
    # Regular formula
    assert electrodes_formula_to_criteria("Cr2O3") == {
        "entries_composition_summary.all_composition_reduced.Cr": 2.0,
        "entries_composition_summary.all_composition_reduced.O": 3.0,
        "nelements": {"$in": [2, 1]},
    }

    assert electrodes_formula_to_criteria("Cr2O3, FeLiO4P") == {
        "entries_composition_summary.all_formulas": {"$in": ["Cr2O3", "LiFePO4"]}
    }
    # Add wildcard
    assert electrodes_formula_to_criteria("Cr2*3") == {
        "entries_composition_summary.all_composition_reduced.Cr": 2.0,
        "entries_composition_summary.all_formula_anonymous": "A2B3",
    }
    # Anonymous element
    assert electrodes_formula_to_criteria("A2B3") == {
        "entries_composition_summary.all_formula_anonymous": "A2B3"
    }

    assert electrodes_formula_to_criteria("A2B3, ABC3") == {
        "entries_composition_summary.all_formula_anonymous": {"$in": ["A2B3", "ABC3"]}
    }


def test_electrodes_chemsys_to_criteria():
    # Chemsys
    assert electrodes_chemsys_to_criteria("Si-O") == {
        "entries_composition_summary.all_chemsys": "O-Si"
    }
    assert electrodes_chemsys_to_criteria("Si-*") == {
        "entries_composition_summary.all_elements": {"$all": ["Si"]},
        "nelements": {"$in": [2, 1]},
    }
    assert electrodes_chemsys_to_criteria("*-*-*") == {"nelements": {"$in": [3, 2]}}

    assert electrodes_chemsys_to_criteria("Si-O, P-Li-Fe") == {
        "entries_composition_summary.all_chemsys": {"$in": ["O-Si", "Fe-Li-P"]}
    }


@pytest.mark.xfail()
def test_electrodes_chemsys_to_criteria_multiple_wildcard():
    electrodes_chemsys_to_criteria("Si-O, Li-Fe-*")


@pytest.mark.xfail()
def test_electrodes_formula_to_criteria_multiple_wildcard():
    electrodes_formula_to_criteria("SiO, LiFe*")
