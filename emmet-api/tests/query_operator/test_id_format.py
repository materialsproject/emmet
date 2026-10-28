"""Tests for ``IdFormatQuery``.

``IdFormatQuery`` adds an optional ``id_format`` query parameter to a route
and rewrites MP-identifier-shaped fields on the response in ``post_process``.
The operator never adds DB criteria — it is purely a serialization-time
transform.
"""

import pytest
from pydantic import BaseModel

from emmet.api.query_operator import IdFormatQuery
from emmet.core.types.typing import (
    IdentifierType,
    MaterialIdentifierType,
    TaskIdentifierType,
    format_identifier,
    format_task_id,
)
from emmet.core.xas import format_spectrum_id


@pytest.fixture
def material_op() -> IdFormatQuery:
    """An operator wired for a ``/materials/summary/`` shaped response."""
    return IdFormatQuery(id_fields=[("material_id", format_identifier)])


@pytest.fixture
def xas_op() -> IdFormatQuery:
    """An operator wired for a ``/materials/xas/`` shaped response."""
    return IdFormatQuery(
        id_fields=[
            ("task_id", format_task_id),
            ("spectrum_id", format_spectrum_id),
        ]
    )


# ---------------------------------------------------------------------------
# query() returns an empty criteria dict so this operator never affects
# which documents the DB returns. It only echoes the id_format value into
# STORE_PARAMS so post_process can read it back.
# ---------------------------------------------------------------------------


def test_query_returns_empty_criteria_when_param_absent(material_op):
    assert material_op.query(id_format=None) == {
        "criteria": {},
        "id_format": None,
    }


def test_query_propagates_legacy_value(material_op):
    assert material_op.query(id_format="legacy") == {
        "criteria": {},
        "id_format": "legacy",
    }


def test_query_propagates_alpha_value(material_op):
    assert material_op.query(id_format="alpha") == {
        "criteria": {},
        "id_format": "alpha",
    }


def test_query_propagates_invalid_value_unchanged(material_op):
    # ``query`` doesn't validate; it forwards whatever arrived. ``post_process``
    # is responsible for handling unknown values defensively.
    assert material_op.query(id_format="banana") == {
        "criteria": {},
        "id_format": "banana",
    }


# ---------------------------------------------------------------------------
# post_process() rewrites the registered id fields based on id_format.
# ---------------------------------------------------------------------------


def test_post_process_no_op_when_id_format_absent(material_op):
    docs = [{"material_id": "mp-149", "other": "value"}]
    out = material_op.post_process(docs, {})
    assert out is docs  # in-place
    assert out == [{"material_id": "mp-149", "other": "value"}]


def test_post_process_no_op_when_id_format_invalid(material_op):
    docs = [{"material_id": "mp-149"}]
    material_op.post_process(docs, {"id_format": "banana"})
    # Invalid value -> behave as if absent. No reformatting attempted.
    assert docs == [{"material_id": "mp-149"}]


def test_post_process_no_op_on_empty_docs(material_op):
    assert material_op.post_process([], {"id_format": "alpha"}) == []


def test_post_process_rewrites_material_id_to_alpha(material_op):
    docs = [
        {"material_id": "mp-149", "formula": "FeO"},
        {"material_id": "mp-13", "formula": "Fe"},
    ]
    out = material_op.post_process(docs, {"id_format": "alpha"})
    assert out[0]["material_id"] == "mp-aaaaaaft"
    assert out[1]["material_id"] == "mp-aaaaaaan"
    # Non-id fields are untouched.
    assert out[0]["formula"] == "FeO"


def test_post_process_rewrites_material_id_to_legacy(material_op):
    docs = [{"material_id": "mp-aaaaaaft"}]
    material_op.post_process(docs, {"id_format": "legacy"})
    assert docs[0]["material_id"] == "mp-149"


def test_post_process_handles_xas_composite_fields(xas_op):
    docs = [
        {
            "task_id": "mp-779827",
            "spectrum_id": "mp-779827-XANES-O-K",
            "edge": "K",
        }
    ]
    xas_op.post_process(docs, {"id_format": "alpha"})
    # task_id: prefix dropped in alpha form.
    assert docs[0]["task_id"] == "aaabsjpj"
    # spectrum_id: prefix dropped on the leading id portion; suffix preserved.
    assert docs[0]["spectrum_id"] == "aaabsjpj-XANES-O-K"
    # Non-id fields are untouched.
    assert docs[0]["edge"] == "K"


def test_post_process_handles_xas_legacy_view(xas_op):
    docs = [
        {
            "task_id": "aaabsjpj",
            "spectrum_id": "aaabsjpj-XANES-O-K",
        }
    ]
    xas_op.post_process(docs, {"id_format": "legacy"})
    assert docs[0]["task_id"] == "mp-779827"
    assert docs[0]["spectrum_id"] == "mp-779827-XANES-O-K"


def test_post_process_skips_missing_fields(material_op):
    # Sparse-fields projection may strip the id field entirely; nothing to
    # rewrite in that case.
    docs = [{"formula_pretty": "FeO"}]
    material_op.post_process(docs, {"id_format": "alpha"})
    assert docs == [{"formula_pretty": "FeO"}]


def test_post_process_skips_none_and_empty_values(material_op):
    docs = [
        {"material_id": None},
        {"material_id": ""},
    ]
    material_op.post_process(docs, {"id_format": "alpha"})
    # Falsy values are left untouched (truthy-guard in IdFormatQuery).
    assert docs[0]["material_id"] is None
    assert docs[1]["material_id"] == ""


def test_post_process_handles_unparseable_value_defensively(material_op):
    # If somehow a corrupted id makes it into a document, the format
    # helpers return the input unchanged. The operator must not raise.
    docs = [{"material_id": "BAD-VALUE!!"}]
    material_op.post_process(docs, {"id_format": "alpha"})
    assert docs[0]["material_id"] == "BAD-VALUE!!"


def test_post_process_ignores_non_dict_entries(material_op):
    # Defensive: response post-processing should tolerate unexpected entries
    # rather than crash the request.
    docs = [{"material_id": "mp-149"}, None, "junk"]
    out = material_op.post_process(docs, {"id_format": "alpha"})
    assert out[0]["material_id"] == "mp-aaaaaaft"
    assert out[1] is None
    assert out[2] == "junk"


def test_default_id_fields_is_empty():
    # Operator with no id_fields registered is a no-op even with a valid
    # id_format value — useful for endpoints where the parameter should be
    # accepted but no rewriting is wired yet.
    op = IdFormatQuery()
    docs = [{"material_id": "mp-149"}]
    op.post_process(docs, {"id_format": "alpha"})
    assert docs == [{"material_id": "mp-149"}]


# ---------------------------------------------------------------------------
# Nested identifiers: explicit dotted paths
# ---------------------------------------------------------------------------


def test_nested_path_through_list_of_dicts():
    op = IdFormatQuery(id_fields=[("decomposes_to.material_id", format_identifier)])
    docs = [
        {
            "material_id": "mp-aaaaaaft",
            "decomposes_to": [
                {"material_id": "mp-aaaaaaft", "amount": 0.5},
                {"material_id": "mp-aaaaaaan", "amount": 0.5},
            ],
        }
    ]
    op.post_process(docs, {"id_format": "legacy"})
    # Not registered, so untouched
    assert docs[0]["material_id"] == "mp-aaaaaaft"
    assert [d["material_id"] for d in docs[0]["decomposes_to"]] == ["mp-149", "mp-13"]
    assert [d["amount"] for d in docs[0]["decomposes_to"]] == [0.5, 0.5]


def test_nested_path_through_dict_and_list_of_ids():
    op = IdFormatQuery(id_fields=[("origins.task_id", format_task_id)])
    docs = [{"origins": [{"name": "a", "task_id": "mp-aaaaaaft"}]}]
    op.post_process(docs, {"id_format": "legacy"})
    assert docs[0]["origins"][0]["task_id"] == "mp-149"
    op.post_process(docs, {"id_format": "alpha"})
    assert docs[0]["origins"][0]["task_id"] == "aaaaaaft"


def test_dict_values_wildcard():
    op = IdFormatQuery(id_fields=[("phonon_IDs.*", format_task_id)])
    docs = [{"phonon_IDs": {"dfpt": ["mp-aaaaaaft", "mp-aaaaaaan"], "pheasy": []}}]
    op.post_process(docs, {"id_format": "legacy"})
    assert docs[0]["phonon_IDs"] == {"dfpt": ["mp-149", "mp-13"], "pheasy": []}


def test_dict_keys_path():
    op = IdFormatQuery(id_fields=[("calc_types.*key", format_task_id)])
    docs = [
        {"calc_types": {"mp-aaaaaaft": "GGA Structure Optimization", "not an id": "y"}}
    ]
    op.post_process(docs, {"id_format": "legacy"})
    assert docs[0]["calc_types"] == {
        "mp-149": "GGA Structure Optimization",
        "not an id": "y",
    }
    op.post_process(docs, {"id_format": "alpha"})
    assert list(docs[0]["calc_types"]) == ["aaaaaaft", "not an id"]


def test_fixed_position_path():
    op = IdFormatQuery(id_fields=[("dos.0", format_task_id)])
    docs = [{"dos": ["mp-aaaaaaft", {"not": "an id"}, 1]}]
    op.post_process(docs, {"id_format": "legacy"})
    assert docs[0]["dos"] == ["mp-149", {"not": "an id"}, 1]


@pytest.mark.parametrize(
    "doc",
    [
        {},
        {"decomposes_to": None},
        {"decomposes_to": []},
        {"decomposes_to": "mp-aaaaaaft"},
        {"decomposes_to": [None, "junk", {"amount": 1}]},
        {"decomposes_to": [{"material_id": None}]},
        {"decomposes_to": {"material_id": None}},
    ],
)
def test_nested_path_tolerates_missing_or_unexpected_shapes(doc):
    op = IdFormatQuery(id_fields=[("decomposes_to.material_id", format_identifier)])
    before = repr(doc)
    op.post_process([doc], {"id_format": "legacy"})
    assert repr(doc) == before


def test_nested_path_is_noop_without_id_format():
    op = IdFormatQuery(id_fields=[("decomposes_to.material_id", format_identifier)])
    docs = [{"decomposes_to": [{"material_id": "mp-aaaaaaft"}]}]
    op.post_process(docs, {"id_format": None})
    assert docs[0]["decomposes_to"][0]["material_id"] == "mp-aaaaaaft"


def test_explicit_id_fields_override_discovered():
    class Doc(BaseModel):
        material_id: IdentifierType | None = None

    def shout(value, *, legacy):
        return "overridden"

    op = IdFormatQuery(model=Doc, id_fields=[("material_id", shout)])
    docs = [{"material_id": "mp-aaaaaaft"}]
    op.post_process(docs, {"id_format": "legacy"})
    assert docs[0]["material_id"] == "overridden"


# ---------------------------------------------------------------------------
# Discovery of identifier fields from a model
# ---------------------------------------------------------------------------


class _Leaf(BaseModel):
    material_id: IdentifierType | None = None
    amount: float = 0.0


class _Node(BaseModel):
    task_id: TaskIdentifierType
    mid: MaterialIdentifierType
    plain: str = "mp-149"
    children: list["_Node"] | None = None


class _Doc(BaseModel):
    material_id: MaterialIdentifierType
    task_ids: list[TaskIdentifierType] = []
    maybe: IdentifierType | int | None = None
    leaves: list[_Leaf] | None = None
    by_method: dict[str, list[TaskIdentifierType]] | None = None
    by_name: dict[str, _Leaf] = {}
    task_types: dict[TaskIdentifierType, str] = {}
    pair: tuple[IdentifierType, float, int] | None = None
    node: _Node | None = None
    not_an_id: str = "mp-149"
    number: int = 0


def test_model_driven_operator_rewrites_everything_it_found():
    op = IdFormatQuery(model=_Doc)
    docs = [
        {
            "material_id": "mp-aaaaaaft",
            "task_ids": ["mp-aaaaaaft", "mp-aaaaaaan"],
            "maybe": "mp-aaaaaaft",
            "leaves": [{"material_id": "mp-aaaaaaan", "amount": 1.0}],
            "by_method": {"a": ["mp-aaaaaaft"]},
            "by_name": {"x": {"material_id": "mp-aaaaaaft"}},
            "task_types": {"mp-aaaaaaft": "Structure Optimization", "mp-aaaaaaan": "x"},
            "pair": ["mp-aaaaaaft", 1.0, 2],
            "node": {
                "task_id": "mp-aaaaaaft",
                "mid": "mp-aaaaaaft",
                "plain": "mp-aaaaaaft",
                "children": [{"task_id": "mp-aaaaaaan", "mid": "mp-aaaaaaan"}],
            },
            "not_an_id": "mp-aaaaaaft",
            "number": 3,
        }
    ]
    op.post_process(docs, {"id_format": "legacy"})
    doc = docs[0]
    assert doc["material_id"] == "mp-149"
    assert doc["task_ids"] == ["mp-149", "mp-13"]
    assert doc["maybe"] == "mp-149"
    assert doc["leaves"] == [{"material_id": "mp-13", "amount": 1.0}]
    assert doc["by_method"] == {"a": ["mp-149"]}
    assert doc["by_name"] == {"x": {"material_id": "mp-149"}}
    assert doc["task_types"] == {"mp-149": "Structure Optimization", "mp-13": "x"}
    assert list(doc["task_types"]) == ["mp-149", "mp-13"]  # order is preserved
    assert doc["pair"] == ["mp-149", 1.0, 2]
    assert doc["node"]["task_id"] == "mp-149"
    assert doc["node"]["mid"] == "mp-149"
    assert doc["node"]["children"] == [{"task_id": "mp-aaaaaaan", "mid": "mp-aaaaaaan"}]
    # Fields that are not typed as identifiers are never touched
    assert doc["node"]["plain"] == "mp-aaaaaaft"
    assert doc["not_an_id"] == "mp-aaaaaaft"
    assert doc["number"] == 3


def test_discovery_happens_at_construction_not_per_request():
    op = IdFormatQuery(model=_Doc)
    assert ("material_id",) in op.id_paths
    # discovered once; post_process reads the cached mapping
    assert op.id_paths is op.id_paths
