from emmet.core.io.pymatgen import Ordering

from emmet.api.routes.materials.summary.query_operators import (
    HasPropsQuery,
    MaterialIDsSearchQuery,
    SearchESQuery,
    SearchIsStableQuery,
    SearchIsTheoreticalQuery,
    SearchMagneticQuery,
)


def test_has_props_query():
    op = HasPropsQuery()

    assert op.query(has_props="electronic_structure, thermo") == {
        "criteria": {"has_props.electronic_structure": True, "has_props.thermo": True}
    }


def test_material_ids_query():
    op = MaterialIDsSearchQuery()

    query = {"criteria": {"material_id": {"$in": ["mp-aaaaaaft", "mp-aaaaaaan"]}}}

    assert op.query(material_ids="mp-149, mp-13") == query

    docs = [{"material_id": "mp-aaaaaaan"}, {"material_id": "mp-aaaaaaft"}]

    assert op.post_process(docs, {**query, "properties": ["material_id"]})[0] == docs[1]


def test_is_stable_query():
    op = SearchIsStableQuery()

    assert op.query(is_stable=True) == {"criteria": {"is_stable": True}}


def test_magnetic_query():
    op = SearchMagneticQuery()

    assert op.query(ordering=Ordering.FiM) == {"criteria": {"ordering": "FiM"}}


def test_is_theoretical_query():
    op = SearchIsTheoreticalQuery()

    assert op.query(theoretical=False) == {"criteria": {"theoretical": False}}


def test_search_es_query():
    op = SearchESQuery()

    assert op.query(is_gap_direct=False, is_metal=False) == {
        "criteria": {"is_gap_direct": False, "is_metal": False}
    }
