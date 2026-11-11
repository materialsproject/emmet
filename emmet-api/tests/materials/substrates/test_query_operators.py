from emmet.api.query_operator import StringQueryOperator
from emmet.api.routes.materials.substrates.query_operators import (
    SubstrateStructureQuery,
    EnergyAreaQuery,
)
from emmet.core.substrates import SubstratesDoc


def test_substrate_structure_operator():
    op = SubstrateStructureQuery()

    assert op.query(film_orientation="0,1, 1", substrate_orientation="1, 0,1") == {
        "criteria": {"film_orient": "0 1 1", "orient": "1 0 1"}
    }


def test_energy_area_operator():
    op = EnergyAreaQuery()

    q = op.query(area_min=0, area_max=5, energy_min=0, energy_max=5)

    fields = ["area", "energy"]

    assert q == {"criteria": {field: {"$gte": 0, "$lte": 5} for field in fields}}


def test_substrates_id_query_params_exposed():
    op = StringQueryOperator(
        model=SubstratesDoc, excluded_fields=["film_orient", "orient"]
    )
    params = set(op.mapping)

    for name in ("film_id", "sub_id"):
        assert {name, f"{name}_not_eq", f"{name}_eq_any", f"{name}_neq_any"} <= params
    assert "sub_form" in params
    assert "film_orient" not in params and "orient" not in params


def test_substrates_id_query_matches_legacy_and_alpha():
    op = StringQueryOperator(
        model=SubstratesDoc, excluded_fields=["film_orient", "orient"]
    )
    both = ["mp-149", "mp-aaaaaaft"]

    for given in ("mp-149", "mp-aaaaaaft"):
        crit = op.query(film_id=given)["criteria"]["film_id"]["$in"]
        assert sorted(crit) == sorted(both)

    assert sorted(op.query(sub_id_not_eq="mp-149")["criteria"]["sub_id"]["$nin"]) == (
        sorted(both)
    )

    any_crit = op.query(film_id_eq_any="mp-149, mp-aaaaaaan")["criteria"]["film_id"]
    assert set(any_crit["$in"]) == {"mp-149", "mp-aaaaaaft", "mp-13", "mp-aaaaaaan"}

    neq_crit = op.query(sub_id_neq_any="mp-149,mp-13")["criteria"]["sub_id"]
    assert set(neq_crit["$nin"]) == {"mp-149", "mp-aaaaaaft", "mp-13", "mp-aaaaaaan"}


def test_substrates_id_query_unparsable_value_is_exact():
    op = StringQueryOperator(
        model=SubstratesDoc, excluded_fields=["film_orient", "orient"]
    )
    assert op.query(film_id="not-an-id")["criteria"]["film_id"]["$in"] == ["not-an-id"]


def test_string_operator_plain_str_fields_unchanged():
    op = StringQueryOperator(
        model=SubstratesDoc, excluded_fields=["film_orient", "orient"]
    )
    assert op.query(sub_form="SiO2")["criteria"] == {"sub_form": "SiO2"}
    assert op.query(sub_form_eq_any="SiO2, Si")["criteria"] == {
        "sub_form": {"$in": ["SiO2", "Si"]}
    }
