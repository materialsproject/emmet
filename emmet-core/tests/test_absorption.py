import numpy as np
import pytest
from monty.serialization import loadfn
from pymatgen.core import Structure

from emmet.core import ARROW_COMPATIBLE
from emmet.core.absorption import AbsorptionDoc
from emmet.core.utils import jsanitize

if ARROW_COMPATIBLE:
    import pyarrow as pa

    from emmet.core.arrow import arrowize


@pytest.fixture(scope="session")
def absorption_test_data(test_dir):
    return loadfn(test_dir / "sample_absorptions.json.gz")


@pytest.fixture(scope="module")
def absorption_test_doc(absorption_test_data):
    structure = Structure.from_dict(
        jsanitize(absorption_test_data["input"]["structure"])
    )
    task_id = absorption_test_data["task_id"]
    kpoints = absorption_test_data["orig_inputs"]["kpoints"]

    cr = absorption_test_data["calcs_reversed"][0]["output"]
    doc = AbsorptionDoc.from_structure(
        structure=structure,
        material_id="mp-{}".format(task_id),
        task_id=task_id,
        deprecated=False,
        energies=cr["frequency_dependent_dielectric"]["energy"],
        real_d=cr["frequency_dependent_dielectric"]["real"],
        imag_d=cr["frequency_dependent_dielectric"]["imaginary"],
        absorption_co=cr["optical_absorption_coeff"],
        bandgap=absorption_test_data["output"]["bandgap"],
        nkpoints=kpoints.num_kpts,
        is_hubbard=False,
    )

    return doc


def test_absorption_doc(absorption_test_doc):
    absorption_coeff = np.array(
        [
            0,
            5504161142.509,
            16485480924.4252,
            41235259342.4927,
            76990619286.8861,
            109929386572.273,
            164921201202.527,
            230913400825.579,
            285790460873.292,
            371002598552.062,
        ]
    )

    imag_dielectric = [0.0, 0.0002, 0.0003]

    energies = [
        0,
        0.0309,
        0.0617,
        0.0926,
        0.1235,
        0.1543,
        0.1852,
        0.2161,
        0.2469,
        0.2778,
    ]

    assert absorption_test_doc is not None
    assert absorption_test_doc.property_name == "Optical absorption spectrum"
    assert absorption_test_doc.energies[0:10] == energies
    assert absorption_test_doc.material_id == "mp-1316"
    assert absorption_test_doc.absorption_coefficient[0:10] == list(absorption_coeff)
    assert absorption_test_doc.average_imaginary_dielectric[0:3] == imag_dielectric
    assert absorption_test_doc.bandgap == 4.4652


@pytest.mark.skipif(
    not ARROW_COMPATIBLE, reason="pyarrow must be installed to run this test."
)
def test_arrow(absorption_test_doc):
    arrow_struct = pa.scalar(
        absorption_test_doc.model_dump(context={"format": "arrow"}),
        type=arrowize(AbsorptionDoc),
    )

    test_arrow_doc = AbsorptionDoc(**arrow_struct.as_py(maps_as_pydicts="strict"))

    assert absorption_test_doc.model_dump() == test_arrow_doc.model_dump()
