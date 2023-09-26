import pytest
from pymatgen.core import Element, Lattice, Structure

from emmet.core.structure import StructureMetadata
from emmet.core.symmetry import CrystalSystem, SymmetryData


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

    assert symm_doc.model_dump()["crystal_system"] == CrystalSystem.cubic
    assert str(symm_doc.model_dump()["crystal_system"]) == "Cubic"


def test_structure_metadata(structure):
    meta_doc = StructureMetadata.from_structure(structure)

    assert meta_doc.nsites == 1
    assert meta_doc.elements == [Element.Fe]
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


def test_composition(structure):
    meta_doc = StructureMetadata.from_structure(structure)
    comp_meta_doc = StructureMetadata.from_composition(structure.composition)

    assert meta_doc.elements == comp_meta_doc.elements
    assert meta_doc.nelements == comp_meta_doc.nelements
    assert meta_doc.formula_pretty == comp_meta_doc.formula_pretty
    assert meta_doc.formula_anonymous == comp_meta_doc.formula_anonymous
    assert meta_doc.chemsys == comp_meta_doc.chemsys


def test_schema():
    StructureMetadata.schema()
