import numpy as np
import pyarrow as pa
import pytest
from monty.serialization import loadfn
from pymatgen.core import Structure

from emmet.core.absorption import AbsorptionDoc
from emmet.core.utils import jsanitize


@pytest.fixture(scope="module")
def absorption_test_doc(test_dir):
    data = loadfn(test_dir / "sample_absorptions.json")
    structure = Structure.from_dict(jsanitize(data["input"]["structure"]))
    task_id = data["task_id"]
    kpoints = data["orig_inputs"]["kpoints"]

    doc = AbsorptionDoc.from_structure(
        structure=structure,
        material_id="mp-{}".format(task_id),
        task_id=task_id,
        deprecated=False,
        energies=data["output"]["dielectric"]["energy"],
        real_d=data["output"]["dielectric"]["real"],
        imag_d=data["output"]["dielectric"]["imag"],
        absorption_co=data["output"]["optical_absorption_coeff"],
        bandgap=data["output"]["bandgap"],
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


def test_arrow(absorption_test_doc):
    arrow_struct = pa.scalar(
        absorption_test_doc.model_dump(context={"format": "arrow"}),
        type=AbsorptionDoc.arrow_type(),
    )

    test_arrow_doc = AbsorptionDoc(**arrow_struct.as_py(maps_as_pydicts="strict"))

    assert absorption_test_doc == test_arrow_doc
