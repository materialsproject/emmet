from typing import TYPE_CHECKING, Union

import pytest
from matcalc.util import get_universal_calculator
from pymatgen.core import Structure
from pymatgen.util.testing import PymatgenTest

from emmet.core.elasticity import BulkModulus, ElasticTensorDoc, ShearModulus
from emmet.core.ml import MLDoc

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
    "elastic_tensor": ElasticTensorDoc,
    "shear_modulus": ShearModulus,
    "bulk_modulus": BulkModulus,
    "young_modulus": float,
}


@pytest.mark.parametrize(
    ("calculator", "prop_kwargs"),
    [
        (get_universal_calculator("chgnet"), None),
        ("m3gnet", {"ElasticityCalc": {"relax_structure": False}}),
    ],
)
def test_ml_doc(calculator: Union[str, "Calculator"], prop_kwargs: dict) -> None:
    doc = MLDoc(
        structure=struct,
        calculator=calculator,
        material_id="mp-33",
        deprecated=False,
        prop_kwargs=prop_kwargs,
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
