"""Test NEB document class."""

from datetime import datetime
from pathlib import Path
import pytest
import shutil
from tempfile import TemporaryDirectory

from monty.serialization import loadfn
from pymatgen.core import Structure

from emmet.core.neb import NebTaskDoc, NebMethod
from emmet.core.tasks import InputDoc, OrigInputs
from emmet.core.utils import jsanitize
from emmet.core.vasp.calculation import Calculation

from tests.conftest import assert_schemas_equal


@pytest.mark.parametrize("from_dir", [True, False])
def test_neb_doc(test_dir, from_dir: bool):
    if from_dir:
        with TemporaryDirectory() as tmpdir:
            shutil.unpack_archive(test_dir / "neb_sample_calc.zip", tmpdir, "zip")
            neb_doc = NebTaskDoc.from_directory(Path(tmpdir) / "neb")
        neb_doc_dict = jsanitize(neb_doc)
    else:
        neb_doc_dict = loadfn(test_dir / "Si_neb_doc.json.bz2", cls=None)
        for k in (
            "completed_at",
            "last_updated",
        ):
            neb_doc_dict[k] = datetime.fromisoformat(neb_doc_dict[k]["string"])

        neb_doc = NebTaskDoc(**neb_doc_dict)

    assert neb_doc.num_images == 3
    assert len(neb_doc.image_structures) == neb_doc.num_images
    assert len(neb_doc.energies) == neb_doc.num_images
    assert len(neb_doc.structures) == neb_doc.num_images + 2 # always includes endpoints
    assert isinstance(neb_doc.orig_inputs, OrigInputs)

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

    # Check that image calculation dirs all have common root / expected format
    assert all(
        image_dir.startswith(neb_doc.dir_name)
        for image_dir in neb_doc.image_directories
    )
    assert all(
        Path(neb_doc.image_directories[image_idx])
        == Path(neb_doc.dir_name) / f"{image_idx+1:02}"
        for image_idx in range(neb_doc.num_images)
    )

    # Check that VASP objects pre-allocated for each image calc
    assert len(neb_doc.image_objects) == neb_doc.num_images

    assert all(
        energy == pytest.approx(neb_doc.image_calculations[idx].output.energy)
        for idx, energy in enumerate(neb_doc.image_energies)
    )
    assert len(neb_doc.image_energies) == neb_doc.num_images

def test_from_directories(test_dir):

    with TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        shutil.unpack_archive(test_dir / "neb_sample_calc.zip", tmpdir, "zip")
        neb_doc = NebTaskDoc.from_directories(
            [tmpdir / f"relax_endpoint_{idx+1}" for idx in range(2)],
            tmpdir / "neb",
        )

    assert all(isinstance(ep_calc,Calculation) for ep_calc in neb_doc.endpoint_calculations)
    
    assert all(
        "relax_endpoint_" in ep_dir for ep_dir in neb_doc.endpoint_directories
    )

    assert len(neb_doc.energies) == neb_doc.num_images + 2
    assert len(neb_doc.structures) == neb_doc.num_images + 2
    assert isinstance(neb_doc.barrier_analysis,dict)

    assert all(
        neb_doc.barrier_analysis.get(k) is not None
        for k in ("energies","frame_index","cubic_spline_pars","ts_frame_index","ts_energy","ts_in_frames","forward_barrier","reverse_barrier")
    )

    assert all(
        getattr(neb_doc,f"{direction}_barrier") == neb_doc.barrier_analysis[f"{direction}_barrier"]
        for direction in ("forward", "reverse")
    )
    