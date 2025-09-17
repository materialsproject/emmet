import pytest
from monty.serialization import loadfn
from pymatgen.core import Structure

from emmet.core import ARROW_COMPATIBLE
from emmet.core.magnetism import MagnetismDoc
from emmet.core.utils import jsanitize

if ARROW_COMPATIBLE:
    import pyarrow as pa

    from emmet.core.arrow import arrowize


@pytest.fixture(scope="module")
def magnetism_mats(test_dir):
    return loadfn(test_dir / "magnetism/magnetism_mats_sample.json.gz")


def test_magnetism_doc(magnetism_mats):
    test_orderings = {"mp-1034331": "FM", "mp-753472": "NM"}

    for material in magnetism_mats:
        structure = Structure.from_dict(jsanitize(material["structure"]))
        total_magnetization = material["magnetism"]["total_magnetization"]
        material_id = material["task_id"]

        doc = MagnetismDoc.from_structure(
            structure=structure,
            material_id=material_id,
            total_magnetization=total_magnetization,
            deprecated=False,
        )
        assert doc is not None
        assert doc.total_magnetization == pytest.approx(abs(total_magnetization))

        if material_id in test_orderings:
            assert doc.ordering == test_orderings[material_id]


@pytest.mark.skipif(
    not ARROW_COMPATIBLE, reason="pyarrow must be installed to run this test."
)
def test_arrow(magnetism_mats):
    doc = MagnetismDoc.from_structure(
        structure=Structure.from_dict(jsanitize(magnetism_mats[0]["structure"])),
        material_id=magnetism_mats[0]["task_id"],
        total_magnetization=magnetism_mats[0]["magnetism"]["total_magnetization"],
        deprecated=False,
    )
    arrow_struct = pa.scalar(
        doc.model_dump(context={"format": "arrow"}), type=arrowize(MagnetismDoc)
    )
    test_arrow_doc = MagnetismDoc(**arrow_struct.as_py(maps_as_pydicts="strict"))

    assert doc.model_dump() == test_arrow_doc.model_dump()
