import pytest
from pymatgen.core import Structure
from monty.serialization import loadfn
from emmet.core.absorption import AbsorptionDoc
from emmet.core.utils import jsanitize


@pytest.fixture(scope="session")
def absorption_test_data(test_dir):
    return loadfn(test_dir / "absorption_sample.json")


def test_absorption_doc(absorption_test_data):
    absorption_coeff = [
    0.0,
    2317691757.40953,
    13906150544.4572,
    27775300832.5449,
    46306540408.7808,
    81049489741.5921,
    111164174925.437,
    145911403000.282,
    203819738807.946,
    250033089158.484]

    imag_dielectric =   [0.0,
    0.0001,
    0.0003,
    0.0004,
    0.0005,
    0.0007,
    0.0008,
    0.0009,
    0.0011,
    0.0012]

    real_dielectric = [ 2.7721,
    2.7722,
    2.7722,
    2.7723,
    2.7724,
    2.7726,
    2.7728,
    2.773,
    2.7732,
    2.7735]

    energies = [0.0,
    1.34874e-13,
    2.69748e-13,
    4.04091e-13,
    5.38965e-13,
    6.73839e-13,
    8.08713e-13,
    9.43587e-13,
    1.078461e-12,
    1.212804e-12]

    for data in absorption_test_data:
        structure = Structure.from_dict(jsanitize(data["structure"]))
        material_id = data["material_id"]

        doc = AbsorptionDoc.from_structure(
            structure=structure,
            material_id=material_id,
            energies = data['output']['dielectric']['energy'],
            real_d = data['output']['dielectric']['imag'],
            imag_d = data['output']['dielectric']['real'],
            absorption_co = data['output']['optical_absorption_coeff'],
            bandgap = data['output']['output'],
            nkpoints= data['orig_inputs']['kpoints']['nkpoints'],
            is_hubbard= False
            )

        assert doc is not None
        assert doc.property_name == "absorption spectrum"
        assert doc.material_id == "mp-571222"
        assert doc.energies[0:10] == energies
        assert doc.absorption_coefficient[0:10] == absorption_coeff
        assert doc.average_real_dielectric[0:10] == real_dielectric
        assert doc.average_imag_dielectric[0:10] == imag_dielectric
        assert doc.bandgap == 4.2734

