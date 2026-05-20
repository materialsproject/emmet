import pytest
from pydantic import BaseModel

from emmet.core.mpid import MPID, AlphaID
from emmet.core.types.typing import (
    ID_PADLEN,
    ID_PREFIX,
    MaterialIdentifierType,
    format_compound_identifier,
    format_identifier,
    format_task_id,
)


def test_identifier_type():

    class TestClass(BaseModel):
        ID: MaterialIdentifierType

    tc = TestClass(ID="dogs")

    # ensure that extant MPIDs are deserialized to MPID,
    # and return AlphaID strings on model dump
    assert isinstance(tc.ID, MPID)
    assert tc.model_dump()["ID"].split("-")[-1].isalpha()
    assert not tc.model_dump()["ID"].isnumeric()

    tc = TestClass(ID=AlphaID._cut_point + 1)
    # ensure that new MPIDs are deserialized to MPID,
    # and return AlphaID strings on model dump
    assert isinstance(tc.ID, AlphaID)
    assert tc.model_dump()["ID"].split("-")[-1].isalpha()
    assert not tc.model_dump()["ID"].isnumeric()


# ---------------------------------------------------------------------------
# format_identifier — display-format helper for plain MP identifiers
# ---------------------------------------------------------------------------


def test_format_identifier_legacy_form_below_cutoff():
    assert format_identifier("mp-149", legacy=True) == "mp-149"


def test_format_identifier_alpha_form_below_cutoff_is_padded():
    # AlphaID display form is padded to ID_PADLEN (8 by default).
    assert format_identifier("mp-149", legacy=False) == "mp-aaaaaaft"


def test_format_identifier_round_trip_legacy_to_alpha_to_legacy():
    alpha = format_identifier("mp-149", legacy=False)
    assert format_identifier(alpha, legacy=True) == "mp-149"


def test_format_identifier_round_trip_alpha_to_legacy_to_alpha():
    legacy = format_identifier("mp-aaaaaaft", legacy=True)
    assert format_identifier(legacy, legacy=False) == "mp-aaaaaaft"


def test_format_identifier_unpadded_alpha_input_produces_padded_output():
    # `mp-ft` is the unpadded AlphaID for 149; should normalize to the padded form.
    assert format_identifier("mp-ft", legacy=False) == "mp-aaaaaaft"


def test_format_identifier_above_cutoff_returns_alpha_for_both_modes():
    # Values above the legacy cutoff have no meaningful legacy form;
    # AlphaID.string returns the alpha form in that case.
    big = "mp-zzzzzz"
    assert format_identifier(big, legacy=True) == big

    # The alpha form is the padded version of the same value.
    padded = format_identifier(big, legacy=False)
    assert padded.startswith(f"{ID_PREFIX}-")
    # Prefix "mp-" plus a padded identifier of length ID_PADLEN.
    assert len(padded) == len(ID_PREFIX) + 1 + ID_PADLEN


@pytest.mark.parametrize("value", ["", None])
def test_format_identifier_empty_input_passes_through(value):
    # Empty / None inputs are returned unchanged so display code is safe to
    # call on absent values.
    assert format_identifier(value, legacy=True) is value
    assert format_identifier(value, legacy=False) is value


def test_format_identifier_unparseable_input_returns_str():
    # Invalid identifiers should be coerced to str and returned unchanged
    # (defensive: never raise from a display helper).
    assert format_identifier("not-an-mpid!!", legacy=True) == "not-an-mpid!!"


def test_format_identifier_respects_custom_padlen():
    # Padding is configurable; verify a non-default padlen propagates.
    assert format_identifier("mp-149", legacy=False, padlen=4) == f"{ID_PREFIX}-aaft"


def test_format_identifier_respects_custom_prefix():
    assert format_identifier(149, legacy=False, prefix="task", padlen=4) == "task-aaft"


# ---------------------------------------------------------------------------
# format_compound_identifier — composite-id display formatter
# ---------------------------------------------------------------------------


def test_format_compound_identifier_plain_mpid_passes_through_to_format_identifier():
    assert format_compound_identifier("mp-149", legacy=True) == "mp-149"
    assert format_compound_identifier("mp-149", legacy=False) == "mp-aaaaaaft"


def test_format_compound_identifier_battery_id_legacy():
    # battery_id = "mp-2658_Al" (composite: mpid + working-ion suffix on "_")
    assert format_compound_identifier("mp-2658_Al", legacy=True) == "mp-2658_Al"


def test_format_compound_identifier_battery_id_alpha_preserves_suffix():
    out = format_compound_identifier("mp-2658_Al", legacy=False)
    assert out.endswith("_Al")
    assert out.startswith(f"{ID_PREFIX}-")

    # The mp-prefix portion should be the alpha form of mp-2658.
    alpha_mpid = format_identifier("mp-2658", legacy=False)
    assert out == f"{alpha_mpid}_Al"


def test_format_compound_identifier_battery_id_round_trip():
    original = "mp-2658_Al"
    alpha = format_compound_identifier(original, legacy=False)
    assert format_compound_identifier(alpha, legacy=True) == original


@pytest.mark.parametrize("value", ["", None])
def test_format_compound_identifier_empty_input_passes_through(value):
    assert format_compound_identifier(value, legacy=True) is value
    assert format_compound_identifier(value, legacy=False) is value


def test_format_compound_identifier_unparseable_input_passes_through():
    # If the leading segment can't be parsed as an MP id, return unchanged.
    # Note: AlphaID accepts arbitrary lowercase strings with valid separators
    # (e.g. "junk_suffix" is parsed as prefix="junk", id="suffix"). We use a
    # value with characters disallowed by AlphaID's alphabet to force the
    # unparseable fallback path.
    assert format_compound_identifier("BAD-ID!!_xx", legacy=False) == "BAD-ID!!_xx"


# ---------------------------------------------------------------------------
# format_task_id — task-id-specific renderer
#
# Task ids have a different shape convention than other MP identifiers:
#   - Legacy: `mp-149` (prefixed)
#   - Alpha:  `aaaaaaft` (bare padded alpha, no prefix, no suffix)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "task_id",
    ["mp-149", "aaaaaaft", "mp-aaaaaaft", "mp-ft", 149],
    ids=["legacy", "alpha-bare", "alpha-prefixed", "alpha-unpadded", "bare-int"],
)
def test_format_task_id_legacy_view_always_returns_mp_prefix(task_id):
    # Regardless of incoming shape, the legacy view is `mp-<int>`.
    assert format_task_id(task_id, legacy=True) == "mp-149"


@pytest.mark.parametrize(
    "task_id",
    ["mp-149", "aaaaaaft", "mp-aaaaaaft", "mp-ft", 149],
    ids=["legacy", "alpha-bare", "alpha-prefixed", "alpha-unpadded", "bare-int"],
)
def test_format_task_id_alpha_view_drops_prefix(task_id):
    # Regardless of incoming shape, the alpha view is the bare padded form
    # with no `mp-` prefix.
    assert format_task_id(task_id, legacy=False) == "aaaaaaft"


def test_format_task_id_round_trip_alpha_to_legacy_to_alpha():
    legacy = format_task_id("aaaaaaft", legacy=True)
    assert format_task_id(legacy, legacy=False) == "aaaaaaft"


def test_format_task_id_round_trip_legacy_to_alpha_to_legacy():
    alpha = format_task_id("mp-149", legacy=False)
    assert format_task_id(alpha, legacy=True) == "mp-149"


@pytest.mark.parametrize("value", ["", None])
def test_format_task_id_empty_input_passes_through(value):
    assert format_task_id(value, legacy=True) is value
    assert format_task_id(value, legacy=False) is value


def test_format_task_id_unparseable_input_passes_through():
    # Defensive: display helpers never raise.
    assert format_task_id("BAD-ID!!", legacy=True) == "BAD-ID!!"
    assert format_task_id("BAD-ID!!", legacy=False) == "BAD-ID!!"


def test_format_task_id_respects_custom_prefix():
    # The legacy prefix is configurable for callers that need a non-default
    # prefix (e.g. a hypothetical "task-149" rendering).
    assert format_task_id("aaaaaaft", legacy=True, prefix="task") == "task-149"


def test_format_task_id_respects_custom_padlen():
    assert format_task_id("mp-149", legacy=False, padlen=4) == "aaft"
