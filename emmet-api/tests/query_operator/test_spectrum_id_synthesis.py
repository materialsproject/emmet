"""Tests for ``SpectrumIdSynthesisQuery``.

``SpectrumIdSynthesisQuery`` injects the computed ``spectrum_id`` field into
each XAS response doc by composing it from ``task_id``, ``spectrum_type``,
``absorbing_element``, and ``edge``. It exists because
``XASDoc.spectrum_id`` is a ``@cached_property`` (not a pydantic field), so
pydantic does not include it in the serialized API response.
"""

import pytest

from emmet.api.query_operator import IdFormatQuery
from emmet.api.routes.materials.xas.query_operators import SpectrumIdSynthesisQuery
from emmet.core.types.typing import format_task_id
from emmet.core.xas import format_spectrum_id


@pytest.fixture
def synth() -> SpectrumIdSynthesisQuery:
    return SpectrumIdSynthesisQuery()


@pytest.fixture
def xas_id_format() -> IdFormatQuery:
    """An ``IdFormatQuery`` wired the same way as the XAS resource."""
    return IdFormatQuery(
        id_fields=[
            ("task_id", format_task_id),
            ("spectrum_id", format_spectrum_id),
        ]
    )


@pytest.fixture
def full_doc() -> dict:
    """A representative XAS response doc as it arrives from the DB layer.

    Task ids are stored in alpha shape (e.g. ``aaabsjpj`` -> 779827); other
    fields are pulled directly from typed enum values.
    """
    return {
        "task_id": "aaabsjpj",
        "spectrum_type": "XANES",
        "absorbing_element": "O",
        "edge": "K",
        "formula_pretty": "Fe2O3",
    }


# ---------------------------------------------------------------------------
# query() is a no-op DB-criteria emitter.
# ---------------------------------------------------------------------------


def test_query_emits_empty_criteria(synth):
    assert synth.query() == {"criteria": {}}


# ---------------------------------------------------------------------------
# post_process() injects spectrum_id by composing the four component fields.
# ---------------------------------------------------------------------------


def test_post_process_synthesizes_spectrum_id(synth, full_doc):
    docs = [full_doc]
    out = synth.post_process(docs, {})
    # In-place mutation: same list returned.
    assert out is docs
    assert out[0]["spectrum_id"] == "aaabsjpj-XANES-O-K"
    # Other fields untouched.
    assert out[0]["task_id"] == "aaabsjpj"
    assert out[0]["formula_pretty"] == "Fe2O3"


def test_post_process_handles_empty_list(synth):
    assert synth.post_process([], {}) == []


def test_post_process_ignores_non_dict_entries(synth, full_doc):
    docs = [full_doc, None, "garbage"]
    synth.post_process(docs, {})
    assert docs[0]["spectrum_id"] == "aaabsjpj-XANES-O-K"
    assert docs[1] is None
    assert docs[2] == "garbage"


def test_post_process_skips_doc_missing_component_field(synth):
    # Sparse-fields projection may exclude one of the synthesis inputs; the
    # operator must skip rather than half-populate or raise.
    docs = [
        {"task_id": "aaaaaaac", "spectrum_type": "XANES", "edge": "L3"},
        # Missing absorbing_element above.
    ]
    synth.post_process(docs, {})
    assert "spectrum_id" not in docs[0]


def test_post_process_does_not_clobber_existing_spectrum_id(synth):
    # If a downstream caller has already populated spectrum_id (or if the
    # DB ever starts persisting it), don't overwrite.
    docs = [
        {
            "task_id": "aaaaaaad",
            "spectrum_type": "XANES",
            "absorbing_element": "Cs",
            "edge": "L3",
            "spectrum_id": "already-set",
        }
    ]
    synth.post_process(docs, {})
    assert docs[0]["spectrum_id"] == "already-set"


def test_post_process_treats_falsy_existing_spectrum_id_as_missing(synth, full_doc):
    # A `None`/empty pre-existing value should be replaced rather than
    # preserved (otherwise we'd leak a stale empty value to the client).
    full_doc["spectrum_id"] = None
    synth.post_process([full_doc], {})
    assert full_doc["spectrum_id"] == "aaabsjpj-XANES-O-K"


# ---------------------------------------------------------------------------
# Interaction with IdFormatQuery: the synthesizer must run BEFORE IdFormatQuery
# so the resulting spectrum_id inherits the user-requested shape rather than
# stamping a fresh alpha-shape value over reformatted task_ids.
# ---------------------------------------------------------------------------


def test_synthesis_then_legacy_reformat_yields_legacy_spectrum_id(
    synth, xas_id_format, full_doc
):
    docs = [full_doc]
    synth.post_process(docs, {})
    xas_id_format.post_process(docs, {"id_format": "legacy"})
    assert docs[0]["task_id"] == "mp-779827"
    assert docs[0]["spectrum_id"] == "mp-779827-XANES-O-K"


def test_synthesis_then_alpha_reformat_preserves_alpha_spectrum_id(
    synth, xas_id_format, full_doc
):
    docs = [full_doc]
    synth.post_process(docs, {})
    xas_id_format.post_process(docs, {"id_format": "alpha"})
    # Already alpha-shape; reformat is effectively a no-op.
    assert docs[0]["task_id"] == "aaabsjpj"
    assert docs[0]["spectrum_id"] == "aaabsjpj-XANES-O-K"


def test_synthesis_then_no_reformat_keeps_db_shape(synth, xas_id_format, full_doc):
    # When id_format is absent, IdFormatQuery is a no-op; the synthesized
    # spectrum_id remains in whatever shape the source task_id had (alpha,
    # in this case, matching the DB).
    docs = [full_doc]
    synth.post_process(docs, {})
    xas_id_format.post_process(docs, {})
    assert docs[0]["task_id"] == "aaabsjpj"
    assert docs[0]["spectrum_id"] == "aaabsjpj-XANES-O-K"
