from typing import List

import numpy as np
import pytest
from monty.serialization import loadfn
from pymatgen.analysis.elasticity import Deformation, Strain, Stress
from pymatgen.core.tensors import Tensor, TensorMapping

from emmet.core.elasticity import (
    ElasticityDoc,
    generate_derived_fitting_data,
    generate_primary_fitting_data,
)


@pytest.fixture(scope="session")
def fitting_data(test_dir):
    """Primary fitting data"""
    data = loadfn(test_dir / "elasticity/SiC_fitting_data.json")
    structure = data["structure"]
    deformations = [Deformation(x) for x in data["deformations"]]
    stresses = [Stress(x) for x in data["stresses"]]
    equilibrium_stress = Stress(data["equilibrium_stress"])

    return structure, deformations, stresses, equilibrium_stress


@pytest.fixture(scope="session")
def reference_data(test_dir):
    """Reference data"""
    data = loadfn(test_dir / "elasticity/SiC_reference_data.json")
    derived_strains = [Strain(x) for x in data["derived_strains"]]
    derived_stresses = [Stress(x) for x in data["derived_stresses"]]
    elastic_tensor_raw = data["elastic_tensor_raw"]

    return derived_strains, derived_stresses, elastic_tensor_raw


def test_generate_derived_fitting_data(fitting_data, reference_data):
    structure, deformations, stresses, equilibrium_stress = fitting_data
    ref_d_strains, ref_d_stresses, _ = reference_data

    strains, _, _, _ = generate_primary_fitting_data(deformations, stresses)
    _, d_strains, d_stresses, _ = generate_derived_fitting_data(
        structure, strains, stresses
    )

    def sequence_of_tensors_equal(a: List[Tensor], b: List[Tensor]):
        mapping = TensorMapping(
            tensors=a, values=[None for _ in range(len(a))], tol=1e-5
        )
        for i, x in enumerate(b):
            if x not in mapping:
                raise AssertionError(
                    f"Cannot find a corresponding tensor in `a` that matches tensor "
                    f"{i} in `b`"
                )

    sequence_of_tensors_equal(d_strains, ref_d_strains)
    sequence_of_tensors_equal(d_stresses, ref_d_stresses)


def test_from_deformations_and_stresses(fitting_data, reference_data):
    structure, deformations, stresses, equilibrium_stress = fitting_data
    _, _, ref_elastic_tensor = reference_data

    doc = ElasticityDoc.from_deformations_and_stresses(
        structure=structure,
        deformations=deformations,
        stresses=stresses,
        equilibrium_stress=equilibrium_stress,
        material_id=1,
    )

    assert np.allclose(doc.elastic_tensor.raw, ref_elastic_tensor, atol=1e-6)
