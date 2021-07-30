import pytest
from pymatgen.analysis.diffraction.xrd import WAVELENGTHS
from pymatgen.core import Element, Lattice, Structure

from emmet.core.xrd import Edge, XRDDoc


@pytest.fixture
def structure():
    test_latt = Lattice.cubic(3.0)
    test_struc = Structure(lattice=test_latt, species=["Fe"], coords=[[0, 0, 0]])
    return test_struc


@pytest.mark.parametrize("target", list(WAVELENGTHS.keys()))
def test_target_detection(structure, target):
    doc = XRDDoc.from_structure(
        structure=structure,
        spectrum_id="test-1",
        material_id="test-1",
        wavelength=WAVELENGTHS[target],
    )

    target_element = Element(target[:2])
    target_edge = Edge(target[2:])
    assert doc.target == target_element
    assert doc.edge == target_edge


@pytest.mark.parametrize("target", list(WAVELENGTHS.keys()))
def test_from_target(structure, target):
    target_element = Element(target[:2])
    target_edge = Edge(target[2:])
    doc = XRDDoc.from_target(
        structure=structure,
        material_id="test-1",
        target=target_element,
        edge=target_edge,
    )
    assert doc.target == target_element
    assert doc.edge == target_edge


def test_schema():
    XRDDoc.schema()
