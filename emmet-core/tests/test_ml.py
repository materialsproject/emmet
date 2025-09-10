import pytest

# from matcalc.utils import get_universal_calculator
import numpy as np
from pymatgen.core import Structure
from pymatgen.util.testing import STRUCTURES_DIR

from emmet.core.elasticity import BulkModulus, ElasticTensorDoc, ShearModulus
from emmet.core.math import matrix_3x3_to_voigt
from emmet.core.ml import MLDoc, MatPESTrainDoc
from emmet.core.tasks import TaskDoc
from emmet.core.testing_utils import DataArchive

from tests.conftest import get_test_object


# if TYPE_CHECKING:
#    from ase.calculators.calculator import Calculator

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


# @pytest.mark.parametrize(
#    ("calculator", "prop_kwargs"),
#    [
#        (get_universal_calculator("chgnet"), None),
#        ("M3GNet-MP-2021.2.8-PES", {"ElasticityCalc": {"relax_structure": False}}),
#    ],
# )
@pytest.mark.skip(reason="Temporary skip. Needs attention.")
def test_ml_doc(calculator, prop_kwargs: dict) -> None:
    struct = Structure.from_file(STRUCTURES_DIR / "Si.json")

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


def test_matpes_doc_from_task_doc(test_dir):

    with DataArchive.extract(
        test_dir / "vasp" / f"{get_test_object('SiOptimizeDouble').folder}.json.gz"
    ) as dir_name:
        task_doc = TaskDoc.from_directory(dir_name)

    matpes_train_docs = MatPESTrainDoc.from_task_doc(task_doc)

    assert len(matpes_train_docs) == sum(
        len(cr.output.ionic_steps) for cr in task_doc.calcs_reversed
    )

    ctr = 0
    for cr in task_doc.calcs_reversed[::-1]:
        for iistep, istep in enumerate(cr.output.ionic_steps):
            assert matpes_train_docs[ctr].energy == pytest.approx(istep.e_0_energy)
            assert np.allclose(matpes_train_docs[ctr].forces, istep.forces)

            assert np.allclose(
                matpes_train_docs[ctr].stress, matrix_3x3_to_voigt(istep.stress)
            )

            if iistep < len(cr.output.ionic_steps) - 1:
                assert matpes_train_docs[ctr].bandgap is None
                assert (
                    matpes_train_docs[ctr].structure.site_properties.get("magmom")
                    is None
                )
            else:
                assert matpes_train_docs[ctr].bandgap == pytest.approx(
                    cr.output.bandgap
                )
                assert np.allclose(
                    matpes_train_docs[ctr].structure.site_properties.get("magmom"),
                    cr.output.structure.site_properties.get("magmom"),
                )

            ctr += 1
