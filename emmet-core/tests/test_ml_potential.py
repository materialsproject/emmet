import pytest
from emmet.core.ml_potential import MLIPDoc
from matcalc.util import get_universal_calculator
from pymatgen.analysis.elasticity import ElasticTensor
from pymatgen.core import Structure

from . import test_structures


@pytest.mark.parametrize("structure", test_structures.values())
def test_mlip_doc(structure: Structure):
    expected_keys = {
        "material_id": str,
        "structure": Structure,
        "deprecated": bool,
        "model": str,
        "version": str,
        "final_structure": Structure,
        "energy": float,
        "volume": float,
        "a": float,
        "b": float,
        "c": float,
        "alpha": float,
        "beta": float,
        "gamma": float,
        "eos": dict,
        "bulk_modulus": float,
        "temperature": ElasticTensor,
        "free_energy": float,
        "entropy": float,
        "heat_capacities": float,
        "elastic_tensor": ElasticTensor,
        "shear_modulus_vrh": float,
        "bulk_modulus_vrh": float,
        "youngs_modulus": float,
    }
    m3gnet_doc = MLIPDoc(
        structure=structure, calculator="m3gnet", material_id="mp-33", deprecated=False
    )
    for key, typ in expected_keys.items():
        assert isinstance(m3gnet_doc[key], typ)

    calculator = get_universal_calculator("chgnet")
    chgnet_doc = MLIPDoc(
        structure=structure,
        calculator=calculator,
        material_id="mp-33",
        deprecated=False,
    )
    assert {*chgnet_doc} >= {*expected_keys}
