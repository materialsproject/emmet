"""Test basic features of XASDoc."""

import pytest
from monty.serialization import loadfn
from emmet.core.io.pymatgen import XAS, Element

from emmet.core import ARROW_COMPATIBLE
from emmet.core.types.enums import XasEdge, XasType
from emmet.core.types.typing import validate_compound_identifier
from emmet.core.utils import jsanitize
from emmet.core.xas import XASDoc

if ARROW_COMPATIBLE:
    import pyarrow as pa

    from emmet.core.arrow import arrowize


@pytest.fixture(scope="module")
def xas_dict(test_dir):
    return loadfn(test_dir / "xasdoc_nonpos_mp_626735.json.gz", cls=None)


def test_xas_doc(xas_dict):
    # First show that there are non-positive intensities
    non_pos_idx = [idx for idx, v in enumerate(xas_dict["spectrum"]["y"]) if v <= 0.0]
    assert len(non_pos_idx) > 0

    # Now show that XASDoc removes non-positive intensities and correctly serializes
    xas = XASDoc(**xas_dict)
    assert xas.spectrum_id == validate_compound_identifier(
        f"{xas.task_id}-"
        + "-".join(
            getattr(xas, k).value
            for k in ("spectrum_type", "absorbing_element", "edge")
        ),
        suffixes=(XasType, Element, XasEdge),
        separator="-",
        use_prefix=False,
    )

    assert isinstance(xas.spectrum, XAS)
    assert len(xas.spectrum.y[xas.spectrum.y <= 0.0]) == 0
    assert all(
        xas.spectrum.y[idx] > 0.0 and xas.spectrum.y[idx] == pytest.approx(0.0)
        for idx in non_pos_idx
    )

    assert isinstance(xas.absorbing_element, Element)

    xas_no_task_id = XASDoc(**{k: v for k, v in xas_dict.items() if k != "task_id"})
    with pytest.raises(
        ValueError, match="Cannot determine `spectrum_id` without a `task_id`"
    ):
        xas_no_task_id.spectrum_id


@pytest.mark.skipif(
    not ARROW_COMPATIBLE, reason="pyarrow must be installed to run this test."
)
def test_arrow(xas_dict):
    doc = XASDoc(**xas_dict)
    arrow_struct = pa.scalar(
        doc.model_dump(context={"format": "arrow"}), type=arrowize(XASDoc)
    )
    test_arrow_doc = XASDoc(**arrow_struct.as_py(maps_as_pydicts="strict"))

    assert jsanitize(doc.model_dump(), allow_bson=True) == jsanitize(
        test_arrow_doc.model_dump(), allow_bson=True
    )


# ---------------------------------------------------------------------------
# format_spectrum_id — XAS-spectrum-id-specific renderer
#
# Spectrum ids are composite identifiers: task id + (XasType, Element, XasEdge)
# joined with "-". They follow the same prefix-dropping rule as task ids:
#   - Legacy: `mp-779827-XANES-O-K`
#   - Alpha:  `aaabsjpj-XANES-O-K` (no `mp-` prefix on the leading id portion)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "spectrum_id",
    ["mp-779827-XANES-O-K", "aaabsjpj-XANES-O-K"],
    ids=["legacy", "alpha"],
)
def test_format_spectrum_id_legacy_view_always_returns_mp_prefix(spectrum_id):
    from emmet.core.xas import format_spectrum_id

    # Regardless of incoming shape, the legacy view is `mp-<int>-<suffix>`.
    assert format_spectrum_id(spectrum_id, legacy=True) == "mp-779827-XANES-O-K"


@pytest.mark.parametrize(
    "spectrum_id",
    ["mp-779827-XANES-O-K", "aaabsjpj-XANES-O-K"],
    ids=["legacy", "alpha"],
)
def test_format_spectrum_id_alpha_view_drops_prefix(spectrum_id):
    from emmet.core.xas import format_spectrum_id

    # Regardless of incoming shape, the alpha view is bare padded alpha +
    # suffix, with no `mp-` prefix on the leading id portion.
    assert format_spectrum_id(spectrum_id, legacy=False) == "aaabsjpj-XANES-O-K"


def test_format_spectrum_id_round_trip_alpha_to_legacy_to_alpha():
    from emmet.core.xas import format_spectrum_id

    original = "aaabsjpj-XANES-O-K"
    legacy = format_spectrum_id(original, legacy=True)
    assert format_spectrum_id(legacy, legacy=False) == original


def test_format_spectrum_id_round_trip_legacy_to_alpha_to_legacy():
    from emmet.core.xas import format_spectrum_id

    original = "mp-779827-XANES-O-K"
    alpha = format_spectrum_id(original, legacy=False)
    assert format_spectrum_id(alpha, legacy=True) == original


def test_format_spectrum_id_preserves_suffix_components():
    from emmet.core.xas import format_spectrum_id

    # EXAFS spectrum type, L2 edge, different absorbing element.
    sid = "mp-149-EXAFS-Fe-L2"
    assert format_spectrum_id(sid, legacy=True) == sid
    alpha = format_spectrum_id(sid, legacy=False)
    assert alpha.endswith("-EXAFS-Fe-L2")
    assert not alpha.startswith("mp-")


@pytest.mark.parametrize("value", ["", None])
def test_format_spectrum_id_empty_input_passes_through(value):
    from emmet.core.xas import format_spectrum_id

    assert format_spectrum_id(value, legacy=True) is value
    assert format_spectrum_id(value, legacy=False) is value


def test_format_spectrum_id_unparseable_input_passes_through():
    from emmet.core.xas import format_spectrum_id

    # Defensive: display helpers never raise. validate_xas_spectrum_id raises
    # ValueError on malformed input; we swallow and return the input as-is.
    assert format_spectrum_id("BAD-ID!!", legacy=True) == "BAD-ID!!"
    assert format_spectrum_id("not-a-spectrum", legacy=False) == "not-a-spectrum"


def test_format_spectrum_id_accepts_mpid_typed_input():
    """Regression: MPID instances passed through must not trip the empty-
    string guard.

    The original guard ``spectrum_id is None or spectrum_id == ""`` triggered
    ``MPID.__eq__("")`` which raises ValueError because ``MPID("")`` is
    invalid. Passing an MPID-typed value used to crash the helper.

    Note: AlphaID does not accept the uppercase-letter portions of a
    spectrum_id (e.g. "XANES", "O", "K"), so composite spectrum ids that
    flow through pydantic-typed fields arrive as ``MPID`` instances.
    """
    from emmet.core.mpid import MPID
    from emmet.core.xas import format_spectrum_id

    sid = MPID("mp-779827-XANES-O-K")
    assert format_spectrum_id(sid, legacy=True) == "mp-779827-XANES-O-K"
    assert format_spectrum_id(sid, legacy=False) == "aaabsjpj-XANES-O-K"
