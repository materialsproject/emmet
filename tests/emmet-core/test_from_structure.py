import pytest
from pymatgen import Lattice
from emmet.stubs import Structure
from emmet.core.symmetry import SymmetryData, CrystalSystem
from emmet.core.structure import StructureMetadata


@pytest.fixture
def structure():
    test_latt = Lattice.cubic(3.0)
    test_struc = Structure(lattice=test_latt, species=["Fe"], coords=[[0, 0, 0]])
    return test_struc


def test_symmetry(structure):

    symm_doc = SymmetryData.from_structure(structure)

    assert symm_doc.number == 221
    assert symm_doc.point_group == "m-3m"
    assert symm_doc.symbol == "Pm-3m"
    assert symm_doc.crystal_system == CrystalSystem.cubic


def test_structure_metadata(structure):

    meta_doc = StructureMetadata.from_structure(structure)

    assert meta_doc.nsites == 1
    assert meta_doc.elements == ["Fe"]
    assert meta_doc.nelements == 1
    assert meta_doc.formula_pretty == "Fe"
    assert meta_doc.formula_anonymous == "A"
    assert meta_doc.chemsys == "Fe"
    assert meta_doc.volume == 27.0
    assert meta_doc.density == 3.4345483027509993
    assert meta_doc.density_atomic == 27.0


def test_structure_metadata_fewer_fields(structure):

    meta_doc = StructureMetadata.from_structure(
        structure, fields=["nsites", "nelements", "volume"]
    )

    assert meta_doc.nsites == 1
    assert meta_doc.nelements == 1
    assert meta_doc.volume == 27.0
