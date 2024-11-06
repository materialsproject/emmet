"""Test NEB document class."""

from datetime import datetime
import pytest

from monty.serialization import loadfn
from pymatgen.core import Structure

from emmet.core.neb import NebTaskDoc, NebMethod
from emmet.core.tasks import InputDoc
from emmet.core.vasp.calculation import Calculation

from tests.conftest import assert_schemas_equal


def test_neb_doc(test_dir):
    neb_doc_dict = loadfn(test_dir / "Si_neb_doc.json.bz2", cls=None)
    for k in (
        "completed_at",
        "last_updated",
    ):
        neb_doc_dict[k] = datetime.fromisoformat(neb_doc_dict[k]["string"])
    neb_doc = NebTaskDoc(**neb_doc_dict)

    assert neb_doc.num_images == 3

    # test that NEB image calculations are all VASP Calculation objects
    assert len(neb_doc.image_calculations) == neb_doc.num_images
    for image_idx, image_calc in enumerate(neb_doc.image_calculations):
        assert_schemas_equal(image_calc, neb_doc_dict["image_calculations"][image_idx])
        assert isinstance(image_calc, Calculation)

    assert isinstance(neb_doc.inputs, InputDoc)

    # check NEB method parsing
    if neb_doc.inputs.incar.get("LCLIMB", False):
        assert neb_doc.neb_method == NebMethod.CLIMBING_IMAGE
    else:
        assert neb_doc.neb_method == NebMethod.STANDARD

    # check that endpoint structures exist
    assert all(isinstance(ep, Structure) for ep in neb_doc.endpoint_structures)

    # Check that image calculation dirs all have common root:
    assert all(
        image_dir.startswith(neb_doc.dir_name)
        for image_dir in neb_doc.image_directories
    )

    # Check that VASP objects pre-allocated for each image calc
    assert len(neb_doc.image_objects) == neb_doc.num_images

    assert all(
        energy == pytest.approx(neb_doc.image_calculations[idx].output.energy)
        for idx, energy in enumerate(neb_doc.image_energies)
    )
    assert len(neb_doc.image_energies) == neb_doc.num_images
