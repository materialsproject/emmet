"""Test basic features of XASDoc."""

import pytest

from monty.serialization import loadfn
from pymatgen.analysis.xas.spectrum import XAS
from pymatgen.core import Element

from emmet.core.xas import XASDoc

def test_xas_doc(test_dir):

    xas_dict = loadfn(test_dir / "xasdoc_nonpos_mp_626735.json.gz", cls=None)

    # First show that there are non-positive intensities
    non_pos_idx = [idx for idx, v in enumerate(xas_dict["spectrum"]["y"]) if v <= 0.]
    assert len(non_pos_idx) > 0

    # Now show that XASDoc removes non-positive intensities and correctly serializes
    xas = XASDoc(**xas_dict)
    assert isinstance(xas.spectrum, XAS)
    assert len(xas.spectrum.y[xas.spectrum.y <= 0.]) == 0
    assert all(
        xas.spectrum.y[idx] > 0. and xas.spectrum.y[idx] == pytest.approx(0.)
        for idx in non_pos_idx
    )

    assert isinstance(xas.absorbing_element,Element)