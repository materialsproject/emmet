from emmet.core.electronic_structure import ElectronicStructureDoc
import pytest
from monty.serialization import loadfn


@pytest.fixture(scope="session")
def structure(test_dir):
    """
    Fe (mp-13) structure with correct magmoms
    """
    structure = loadfn(test_dir / "Fe_structure.json")
    return structure


@pytest.fixture(scope="session")
def bandstructure(test_dir):
    """
    Fe (mp-13) line-mode band structure
    """
    bs = loadfn(test_dir / "Fe_bs.json")
    return bs


@pytest.fixture(scope="session")
def dos(test_dir):
    """
    Fe (mp-13) dos
    """
    dos = loadfn(test_dir / "Fe_dos.json")
    return dos


def test_from_bsdos(bandstructure, dos, structure):

    es_doc = ElectronicStructureDoc.from_bsdos(
        material_id="mp-13",
        dos={"mp-1671247": dos},
        is_gap_direct=False,
        is_metal=True,
        setyawan_curtarolo={"mp-1056141": bandstructure},
        structures={"mp-1671247": structure, "mp-1056141": structure},
    )

    assert str(es_doc.material_id) == "mp-13"
    assert es_doc.band_gap == 0.0
    assert es_doc.cbm == 5.0607
    assert es_doc.vbm == 5.1977
    assert es_doc.efermi == 5.0962618
    assert es_doc.is_gap_direct is False
    assert es_doc.is_metal is True
    assert str(es_doc.magnetic_ordering) == "Ordering.FM"

    assert str(es_doc.bandstructure.setyawan_curtarolo.task_id) == "mp-1056141"
    assert es_doc.bandstructure.setyawan_curtarolo.band_gap == 0.0
    assert es_doc.bandstructure.setyawan_curtarolo.efermi == 5.18804178
    assert es_doc.bandstructure.setyawan_curtarolo.nbands == 96.0

