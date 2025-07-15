"""Test structure similarity features."""

from emmet.core.similarity import CrystalNNSimilarity, M3GNetSimilarity
from pymatgen.core import Structure
import numpy as np

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


def test_crystalnn_featurize():

    scorer = CrystalNNSimilarity()
    feature_vectors, dist_matrix = scorer.get_similarity_scores(structures)
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
    assert dist_matrix.shape == (len(structures), len(structures))
    assert np.all(np.abs(dist_matrix - dist_matrix.T) < 1e-6)  # should be symmetric
    assert np.all(np.abs(dist_matrix - ref_matrix) < 1e-6)


def test_m3gnet_featurize():

    scorer = M3GNetSimilarity()
    fvs, dist_matrix = scorer.get_similarity_scores(structures)

    assert fvs.shape == (len(structures), 128)

    ref_matrix = np.array(
        [
            [0.0, 2.047832416267483, 3.628188818893276],
            [2.047832416267483, 0.0, 3.429993254965302],
            [3.628188818893276, 3.429993254965302, 0.0],
        ]
    )

    assert np.all(np.abs(dist_matrix - dist_matrix.T) < 1e-6)  # should be symmetric
    assert np.all(np.abs(dist_matrix - ref_matrix) < 1e-6)
