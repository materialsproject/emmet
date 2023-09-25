from typing import TYPE_CHECKING, Union

import pytest
from matcalc.util import get_universal_calculator
from pymatgen.analysis.elasticity import ElasticTensor
from pymatgen.core import Structure
from pymatgen.util.testing import PymatgenTest

from emmet.core.ml import MLIPDoc

if TYPE_CHECKING:
    from ase.calculators.calculator import Calculator

struct = PymatgenTest.get_structure("Si")


expected_keys = {
    # -- metadata --
    "material_id": str,
    "structure": Structure,
    "deprecated": bool,
    "matcalc_version": type(None),  # str,
    "model_name": type(None),  # str,
    "model_version": type(None),  # str,
    # -- relaxation --
    "final_structure": Structure,
    "energy": float,
    "volume": float,
    "a": float,
    "b": float,
    "c": float,
    "alpha": float,
    "beta": float,
    "gamma": float,
    # -- eos --
    "eos": dict,
    "bulk_modulus_bm": float,
    # -- phonon --
    "temperatures": list,
    "free_energy": list,
    "entropy": list,
    "heat_capacity": list,
    # -- elasticity --
    "elastic_tensor": ElasticTensor,
    "shear_modulus_vrh": float,
    "bulk_modulus_vrh": float,
    "youngs_modulus": float,
}


@pytest.mark.parametrize("calculator", [get_universal_calculator("chgnet"), "m3gnet"])
def test_mlip_doc(calculator: Union[str, "Calculator"]) -> None:
    doc = MLIPDoc(
        structure=struct, calculator=calculator, material_id="mp-33", deprecated=False
    )

    # check that all expected keys are present
    missing = sorted({*expected_keys} - {*doc.__dict__})
    assert not missing, f"keys {missing=}"

    # check that all keys have expected type
    for key, typ in expected_keys.items():
        actual = getattr(doc, key)
        assert isinstance(
            actual, typ
        ), f"{key=} expected type={typ.__name__}, got {type(actual).__name__}"
