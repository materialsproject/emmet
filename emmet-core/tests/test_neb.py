"""Test NEB document class."""

from pathlib import Path
import pytest
import shutil
from tempfile import TemporaryDirectory

from monty.serialization import loadfn
from pymatgen.core import Structure

from emmet.core.neb import (
    NebTaskDoc,
    NebMethod,
    BarrierAnalysis,
    NebIntermediateImagesDoc,
)
from emmet.core.tasks import InputDoc, OrigInputs
from emmet.core.vasp.calculation import Calculation, CalculationInput

from emmet.core.testing_utils import assert_schemas_equal


@pytest.fixture(scope="module")
def neb_test_dir(test_dir: Path) -> Path:
    return test_dir / "neb"


@pytest.mark.parametrize("from_dir", [True, False])
def test_neb_task_doc(neb_test_dir, from_dir: bool):
    if from_dir:
        with TemporaryDirectory() as tmpdir:
            shutil.unpack_archive(neb_test_dir / "neb_sample_calc.zip", tmpdir, "zip")
            neb_doc = NebIntermediateImagesDoc.from_directory(Path(tmpdir) / "neb")
        num_images = 3
        intermed_idxs = (0, 1, 2)
        assert isinstance(neb_doc.orig_inputs, OrigInputs)
        assert isinstance(neb_doc.inputs, InputDoc)
    else:
        neb_doc = NebTaskDoc(**loadfn(neb_test_dir / "Si_neb_doc.json.bz2"))
        num_images = 5
        intermed_idxs = (1, 2, 3)
        assert neb_doc.num_images == num_images
    neb_doc_dict = neb_doc.model_dump()

    assert len(neb_doc.images) == num_images
    assert len(neb_doc.energies) == num_images
    assert len(neb_doc.images) == num_images

    # test that NEB image calculations are all VASP Calculation objects
    assert len(neb_doc.calculations) == num_images
    for image_idx, image_calc in enumerate(neb_doc.calculations):
        assert_schemas_equal(image_calc, neb_doc_dict["calculations"][image_idx])
        assert isinstance(image_calc, Calculation)

    assert all(isinstance(doc.input, CalculationInput) for doc in neb_doc.calculations)

    # check NEB method parsing
    assert neb_doc.neb_method == NebMethod.CLIMBING_IMAGE

    # check that all structures exist
    assert all(isinstance(image, Structure) for image in neb_doc.images)

    # Check that image calculation dirs all have common root / expected format
    assert all(
        neb_doc.directories[idx].startswith(str(neb_doc.dir_name))
        for idx in intermed_idxs
    )

    assert all(
        Path(neb_doc.directories[idx]) == Path(neb_doc.dir_name) / f"{image_idx+1:02}"
        for image_idx, idx in enumerate(intermed_idxs)
    )

    # Check that VASP objects stored for each image calc
    assert len(neb_doc.objects) == num_images

    assert all(
        energy == pytest.approx(neb_doc.calculations[idx].output.energy)
        for idx, energy in enumerate(neb_doc.energies)
    )


def test_from_directories(neb_test_dir):
    with TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        shutil.unpack_archive(neb_test_dir / "neb_sample_calc.zip", tmpdir, "zip")
        neb_doc = NebTaskDoc.from_directories(
            [tmpdir / f"relax_endpoint_{idx+1}" for idx in range(2)],
            tmpdir / "neb",
        )

    assert all(isinstance(calc, Calculation) for calc in neb_doc.calculations)

    for i, ep_dir in enumerate(neb_doc.directories):
        if i == 0 or i == neb_doc.num_images - 1:
            assert "relax_endpoint_" in ep_dir
        else:
            assert f"neb/{i:02}" in ep_dir

    assert len(neb_doc.energies) == neb_doc.num_images
    assert len(neb_doc.images) == neb_doc.num_images
    assert isinstance(neb_doc.barrier_analysis, BarrierAnalysis)

    assert all(
        getattr(neb_doc.barrier_analysis, k, None) is not None
        for k in (
            "energies",
            "frame_index",
            "cubic_spline_pars",
            "ts_frame_index",
            "ts_energy",
            "ts_in_frames",
            "forward_barrier",
            "reverse_barrier",
        )
    )

    assert all(
        getattr(neb_doc, f"{direction}_barrier")
        == getattr(neb_doc.barrier_analysis, f"{direction}_barrier", None)
        for direction in ("forward", "reverse")
    )
