"""Test structure similarity features."""

from emmet.core.similarity import featurize_structures, structure_distance_matrix
from pymatgen.core import Structure
import numpy as np


def test_featurize():
    structures = [
        Structure(
            3.5 * np.array([[0.0, 0.5, 0.5], [0.5, 0.0, 0.5], [0.5, 0.5, 0.0]]),
            ["Cu"],
            [[0.0, 0.0, 0.0]],
        ),  # fcc Cu
        Structure(
            4 * np.array([[0.0, 0.5, 0.5], [0.5, 0.0, 0.5], [0.5, 0.5, 0.0]]),
            ["Cu", "Cl"],
            [[0.0, 0.0, 0.0], [0.25, 0.25, 0.25]],
        ),  # diamond cubic CuCl
        Structure(
            2.8
            * np.array(
                [
                    [0.5, -(3.0 ** (0.5)) / 2.0, 0.0],
                    [0.5, 3.0 ** (0.5) / 2.0, 0.0],
                    [0.0, 0.0, 2],
                ]
            ),
            ["Mo", "S"],
            [
                [2 / 3, 1 / 3, 0.25],
                [1 / 3, 2 / 3, 0.75],
            ],
        ),  # weird hcp MoS
    ]

    feature_vectors = featurize_structures(structures)
    assert feature_vectors.shape == (
        len(structures),
        122,
    )  # this majik number is defined by the fingerprint

    ref_matrix = np.array(
        [
            [100.0, 5.27097101, 35.0290187],
            [5.27097101, 100.0, 8.01686918],
            [35.0290187, 8.01686918, 100.0],
        ]
    )
    dist_matrix = structure_distance_matrix(feature_vectors)
    assert dist_matrix.shape == (len(structures), len(structures))
    assert np.all(np.abs(dist_matrix - dist_matrix.T) < 1e-6)  # should be symmetric
    assert np.all(np.abs(dist_matrix - ref_matrix) < 1e-6)
