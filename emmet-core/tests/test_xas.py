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
