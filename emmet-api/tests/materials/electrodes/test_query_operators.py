from emmet.api.routes.materials.insertion_electrodes.query_operators import (
    ElectrodeFormulaQuery,
    ElectrodesChemsysQuery,
    ElectrodeElementsQuery,
    WorkingIonQuery,
    MultiBatteryIDQuery,
)


def test_electrode_formula_query():
    op = ElectrodeFormulaQuery()

    assert op.query(formula="BiFeO3") == {
        "criteria": {
            "entries_composition_summary.all_composition_reduced.Bi": 1.0,
            "entries_composition_summary.all_composition_reduced.Fe": 1.0,
            "entries_composition_summary.all_composition_reduced.O": 3.0,
            "nelements": {"$in": [3, 2]},
        }
    }


def test_electrodes_chemsys_query():
    op = ElectrodesChemsysQuery()
    assert op.query("Si-O") == {
        "criteria": {"entries_composition_summary.all_chemsys": "O-Si"}
    }

    assert op.query("Si-*") == {
        "criteria": {
            "nelements": {"$in": [2, 1]},
            "entries_composition_summary.all_elements": {"$all": ["Si"]},
        }
    }


def test_electrodes_elements_query():
    eles = ["Si", "O"]
    neles = ["N", "P"]

    op = ElectrodeElementsQuery()
    assert op.query(elements=",".join(eles), exclude_elements=",".join(neles)) == {
        "criteria": {
            "entries_composition_summary.all_elements": {
                "$all": ["Si", "O"],
                "$nin": ["N", "P"],
            }
        }
    }


def test_insertion_electrode_query():
    op = WorkingIonQuery()

    q = op.query(
        working_ion="Li",
    )

    assert q == {"criteria": {"working_ion": "Li"}}


def test_multi_battery_id_query():
    op = MultiBatteryIDQuery()
    assert op.query(battery_ids="mp-149_Ca, mp-13_Li") == {
        "criteria": {"battery_id": {"$in": ["mp-149_Ca", "mp-13_Li"]}}
    }

    assert op.query(battery_ids="mp-149_Ca") == {
        "criteria": {"battery_id": "mp-149_Ca"}
    }
