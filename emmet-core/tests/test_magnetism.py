import pyarrow as pa
import pytest
from monty.serialization import loadfn
from pymatgen.core import Structure

from emmet.core.magnetism import MagnetismDoc
from emmet.core.utils import jsanitize


@pytest.fixture(scope="module")
def magnetism_mats(test_dir):
    return loadfn(test_dir / "magnetism/magnetism_mats_sample.json")


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


def test_magnetism_arrow_round_trip_serialization(magnetism_mats):
    doc = MagnetismDoc.from_structure(
        structure=Structure.from_dict(jsanitize(magnetism_mats[0]["structure"])),
        material_id=magnetism_mats[0]["task_id"],
        total_magnetization=magnetism_mats[0]["magnetism"]["total_magnetization"],
        deprecated=False,
    )

    sanitized_doc = jsanitize(doc.model_dump(), allow_bson=True)
    test_arrow_doc = MagnetismDoc(
        **pa.array([sanitized_doc], type=MagnetismDoc.arrow_type())
        .to_pandas(maps_as_pydicts="strict")
        .iloc[0]
    )

    assert doc == test_arrow_doc
