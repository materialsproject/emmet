"""Tests for ``IdFormatQuery``.

``IdFormatQuery`` adds an optional ``id_format`` query parameter to a route
and rewrites MP-identifier-shaped fields on the response in ``post_process``.
The operator never adds DB criteria — it is purely a serialization-time
transform.
"""

import pytest

from emmet.api.query_operator import IdFormatQuery
from emmet.core.types.typing import format_identifier, format_task_id
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
