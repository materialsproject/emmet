import pytest
from pymatgen.core import Structure
from monty.serialization import loadfn

from emmet.core.magnetism import MagnetismDoc
from emmet.core.utils import jsanitize


@pytest.fixture(scope="session")
def magnetism_test_data(test_dir):
    return loadfn(test_dir / "magnetism/magnetism_mats_sample.json")


def test_magnetism_doc(magnetism_test_data):
    test_orderings = {"mp-1034331": "FM", "mp-753472": "NM"}

    for material in magnetism_test_data:
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
