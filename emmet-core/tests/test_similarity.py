"""Test structure similarity features."""

import pytest

from pymatgen.core import Structure
import numpy as np

from emmet.core.similarity import (
    CrystalNNSimilarity,
    M3GNetSimilarity,
    CrystalNNFingerprint,
    matgl,
    vector_difference_matrix,
    SimilarityScorer,
)


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


@pytest.mark.skipif(CrystalNNFingerprint is None, reason="matminer is not installed.")
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


@pytest.mark.skipif(matgl is None, reason="matminer is not installed.")
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


def test_vector_diff_mat():

    vectors = np.random.random((7, 11))
    brute_force_diffs = np.zeros(2 * (vectors.shape[0],))
    for i in range(vectors.shape[0]):
        for j in range(vectors.shape[0]):
            brute_force_diffs[i, j] = np.linalg.norm(vectors[i] - vectors[j])
    assert np.all(np.abs(brute_force_diffs - vector_difference_matrix(vectors)) < 1e-12)


def test_vendi():

    assert all(
        abs(rank - SimilarityScorer.get_vendi_score(np.eye(rank))) < 1e-12
        for rank in range(1, 6)
    )

    assert all(
        abs(1.0 - SimilarityScorer.get_vendi_score(np.ones((rank, rank)))) < 1e-12
        for rank in range(1, 6)
    )
