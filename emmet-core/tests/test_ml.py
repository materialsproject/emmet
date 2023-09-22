from matcalc.util import get_universal_calculator
from pymatgen.analysis.elasticity import ElasticTensor
from pymatgen.core import Structure
from pymatgen.util.testing import PymatgenTest

from emmet.core.ml import MLIPDoc

struct = PymatgenTest.get_structure("Si")


expected_keys = {
    # -- metadata --
    "material_id": str,
    "structure": Structure,
    "deprecated": bool,
    "calculator": str,
    "version": str,
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


def test_mlip_doc_with_calc_as_str() -> None:
    doc = MLIPDoc(
        structure=struct, calculator="m3gnet", material_id="mp-33", deprecated=False
    )
    for key, typ in expected_keys.items():
        actual = getattr(doc, key)
        assert isinstance(
            actual, typ
        ), f"{key=} expected type={typ.__name__}, got {type(actual).__name__}"


def test_mlip_doc_with_calc_as_model() -> None:
    # %%
    calculator = get_universal_calculator("chgnet")
    doc = MLIPDoc(
        structure=struct,
        calculator=calculator,
        material_id="mp-33",
        deprecated=False,
    )
    actual = {*doc.__dict__}
    missing = sorted({*expected_keys} - actual)
    assert not missing, f"keys {missing=}"
