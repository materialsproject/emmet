import pytest
from maggma.stores import JSONStore
from monty.serialization import loadfn
from pymatgen.electronic_structure.bandstructure import BandStructureSymmLine
from pymatgen.electronic_structure.dos import CompleteDos

from emmet.core.electronic_structure import ElectronicStructureDoc


@pytest.fixture(scope="session")
def structure(test_dir):
    """
    Fe (mp-13) structure with correct magmoms
    """
    structure = loadfn(test_dir / "electronic_structure/Fe_structure.json")
    return structure


@pytest.fixture(scope="session")
def bandstructure(test_dir):
    """
    Fe (mp-13) line-mode band structure
    """
    bs = loadfn(test_dir / "electronic_structure/Fe_bs.json")
    return bs


@pytest.fixture(scope="session")
def dos(test_dir):
    """
    Fe (mp-13) dos
    """
    dos = loadfn(test_dir / "electronic_structure/Fe_dos.json")
    return dos

def test_from_bsdos_1(bandstructure, dos, structure):

    es_doc = ElectronicStructureDoc.from_bsdos(
        material_id="mp-13",
        dos={"mp-1671247": dos},
        is_gap_direct=False,
        is_metal=True,
        deprecated=False,
        setyawan_curtarolo={"mp-1056141": bandstructure},
        structures={"mp-1671247": structure, "mp-1056141": structure},
    )

    assert str(es_doc.material_id) == "mp-13"
    assert es_doc.band_gap == 0.0
    assert es_doc.cbm is None
    assert es_doc.vbm is None
    assert es_doc.efermi == 5.18804178
    assert es_doc.is_gap_direct is False
    assert es_doc.is_metal is True
    assert str(es_doc.magnetic_ordering) == "Ordering.FM"

    assert str(es_doc.bandstructure.setyawan_curtarolo.task_id) == "mp-1056141"
    assert es_doc.bandstructure.setyawan_curtarolo.band_gap == 0.0
    assert es_doc.bandstructure.setyawan_curtarolo.efermi == 5.18804178
    assert es_doc.bandstructure.setyawan_curtarolo.nbands == 96.0


@pytest.fixture
def bandstructure_fs(test_dir):
    return JSONStore(
        test_dir / "electronic_structure/es_bs_objs.json.gz", key="task_id"
    )


@pytest.fixture
def dos_fs(test_dir):
    return JSONStore(
        test_dir / "electronic_structure/es_dos_objs.json.gz", key="task_id"
    )


def test_from_bsdos_2(bandstructure_fs, dos_fs):

    dos_fs.connect()
    bandstructure_fs.connect()

    dos = CompleteDos.from_dict(dos_fs.query_one({"task_id": "mp-823888"})["data"])
    bs = BandStructureSymmLine.from_dict(
        bandstructure_fs.query_one({"task_id": "mp-1612487"})["data"]
    )

    es_doc = ElectronicStructureDoc.from_bsdos(
        material_id="mp-25375",
        dos={"mp-823888": dos},
        is_gap_direct=False,
        is_metal=True,
        deprecated=False,
        setyawan_curtarolo={"mp-1612487": bs},
    )

    assert str(es_doc.material_id) == "mp-25375"
    assert es_doc.band_gap == 0.0
    assert es_doc.cbm == 2.7102
    assert es_doc.vbm == 2.9396
    assert es_doc.efermi == 2.75448867
    assert es_doc.is_gap_direct is False
    assert es_doc.is_metal is True
    assert str(es_doc.magnetic_ordering) == "Ordering.NM"

    assert str(es_doc.bandstructure.setyawan_curtarolo.task_id) == "mp-1612487"
    assert es_doc.bandstructure.setyawan_curtarolo.band_gap == 1.9916
    assert es_doc.bandstructure.setyawan_curtarolo.efermi == 2.49084067
    assert es_doc.bandstructure.setyawan_curtarolo.nbands == 64.0
