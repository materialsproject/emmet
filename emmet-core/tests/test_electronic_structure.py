import pytest
from monty.serialization import loadfn

from emmet.core import ARROW_COMPATIBLE
from emmet.core.electronic_structure import ElectronicStructureDoc
from emmet.core.utils import jsanitize

if ARROW_COMPATIBLE:
    import pyarrow as pa

    from emmet.core.arrow import arrowize


@pytest.fixture(scope="session")
def structure(test_dir):
    """
    Fe (mp-13) structure with correct magmoms
    """
    structure = loadfn(test_dir / "electronic_structure/Fe_structure.json.gz")
    return structure


@pytest.fixture(scope="session")
def bandstructure(test_dir):
    """
    Fe (mp-13) line-mode band structure
    """
    bs = loadfn(test_dir / "electronic_structure/Fe_bs.json.gz")
    return bs


@pytest.fixture(scope="session")
def dos(test_dir):
    """
    Fe (mp-13) dos
    """
    dos = loadfn(test_dir / "electronic_structure/Fe_dos.json.gz")
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
        meta_structure=structure,
    )

    assert es_doc.material_id == "mp-13"
    assert es_doc.band_gap == 0.0
    assert es_doc.cbm is None
    assert es_doc.vbm is None
    assert es_doc.efermi == 5.18804178
    assert es_doc.is_gap_direct is False
    assert es_doc.is_metal is True
    assert str(es_doc.magnetic_ordering) == "Ordering.FM"

    assert es_doc.bandstructure.setyawan_curtarolo.task_id == "mp-1056141"
    assert es_doc.bandstructure.setyawan_curtarolo.band_gap == 0.0
    assert es_doc.bandstructure.setyawan_curtarolo.efermi == 5.18804178
    assert es_doc.bandstructure.setyawan_curtarolo.nbands == 96.0


@pytest.fixture
def bandstructure_fs(test_dir):
    bs = loadfn(test_dir / "electronic_structure/es_bs_objs.json.gz")
    return bs


@pytest.fixture
def dos_fs(test_dir):
    dos = loadfn(test_dir / "electronic_structure/es_dos_objs.json.gz")
    return dos


def test_from_bsdos_2(bandstructure_fs, dos_fs):
    dos = dos_fs[0]["data"]
    bs = bandstructure_fs[0]["data"]

    es_doc = ElectronicStructureDoc.from_bsdos(
        material_id="mp-25375",
        dos={"mp-823888": dos},
        is_gap_direct=False,
        is_metal=True,
        deprecated=False,
        setyawan_curtarolo={"mp-1612487": bs},
        meta_structure=dos.structure,
    )

    assert es_doc.material_id == "mp-25375"
    assert es_doc.band_gap == pytest.approx(0.0)
    assert es_doc.cbm == pytest.approx(2.75448867)
    assert es_doc.vbm == pytest.approx(2.75448867)
    assert es_doc.efermi == pytest.approx(2.75448867)
    assert es_doc.is_gap_direct is False
    assert es_doc.is_metal is True
    assert str(es_doc.magnetic_ordering) == "Ordering.NM"

    assert es_doc.bandstructure.setyawan_curtarolo.task_id == "mp-1612487"
    assert es_doc.bandstructure.setyawan_curtarolo.band_gap == pytest.approx(1.9916)
    assert es_doc.bandstructure.setyawan_curtarolo.efermi == pytest.approx(2.49084067)
    assert es_doc.bandstructure.setyawan_curtarolo.nbands == pytest.approx(64.0)


@pytest.mark.skipif(
    not ARROW_COMPATIBLE, reason="pyarrow must be installed to run this test."
)
def test_arrow(bandstructure_fs, dos_fs):
    dos = dos_fs[0]["data"]
    bs = bandstructure_fs[0]["data"]

    doc = ElectronicStructureDoc.from_bsdos(
        material_id="mp-25375",
        dos={"mp-823888": dos},
        is_gap_direct=False,
        is_metal=True,
        deprecated=False,
        setyawan_curtarolo={"mp-1612487": bs},
        meta_structure=dos.structure,
    )

    arrow_struct = pa.scalar(
        doc.model_dump(context={"format": "arrow"}),
        type=arrowize(ElectronicStructureDoc),
    )
    test_arrow_doc = ElectronicStructureDoc(
        **arrow_struct.as_py(maps_as_pydicts="strict")
    )

    # have to compare dicts due to dumping model to json the first time:
    #     DOS spins and orbital types don't rehydrate into pmg objects (Spin, OrbitalType)
    # str representation of the doesn't map back to the enum vals in pmg (ints)
    assert jsanitize(doc.model_dump(), allow_bson=True) == jsanitize(
        test_arrow_doc.model_dump(), allow_bson=True
    )
