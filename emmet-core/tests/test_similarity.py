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
    SimilarityDoc,
    SimilarityEntry,
    _vector_from_hex_and_norm,
    _vector_to_hex_and_norm,
)


structures = {
    "fcc_cu": Structure(
        3.5 * np.array([[0.0, 0.5, 0.5], [0.5, 0.0, 0.5], [0.5, 0.5, 0.0]]),
        ["Cu"],
        [[0.0, 0.0, 0.0]],
    ),  # fcc Cu
    "dc_cu_cl": Structure(
        4 * np.array([[0.0, 0.5, 0.5], [0.5, 0.0, 0.5], [0.5, 0.5, 0.0]]),
        ["Cu", "Cl"],
        [[0.0, 0.0, 0.0], [0.25, 0.25, 0.25]],
    ),  # diamond cubic CuCl
    "hcp_mo_s": Structure(
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
}


@pytest.mark.skipif(CrystalNNFingerprint is None, reason="matminer is not installed.")
def test_crystalnn_featurize():

    scorer = CrystalNNSimilarity()
    feature_vectors, dist_matrix = scorer.get_all_similarity_scores(
        list(structures.values())
    )
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

    num_matches = 2
    similarity_docs = scorer.build_similarity_collection_from_structures(
        structures,
        num_procs=1,
        num_top=num_matches,
    )

    # Ensure that similarity docs are correctly constructed,
    # and order of docs follows order of structures in the
    # source dict.
    # Also check that the number of included similarity entries
    # is the same as specified by `num_matches`
    assert all(
        (
            isinstance(similarity_docs[i], SimilarityDoc)
            and len(similarity_docs[i].sim) == num_matches
            and similarity_docs[i].material_id == idx
            and all(
                isinstance(entry, SimilarityEntry) for entry in similarity_docs[i].sim
            )
        )
        for i, idx in enumerate(structures.keys())
    )

    # Check that the feature vectors are the same as before
    assert np.all(
        np.abs(fv - similarity_docs[i].feature_vector) < 1e-6
        for i, fv in enumerate(feature_vectors)
    )

    # Check that the matched similarity entries have the same
    # similarity scores as computed in `ref_matrix`
    id_to_index = {idfr: i for i, idfr in enumerate(structures.keys())}
    assert all(
        all(
            100 - entry.dissimilarity
            == pytest.approx(ref_matrix[i, id_to_index[entry.task_id]])
            for entry in doc.sim
        )
        for i, doc in enumerate(similarity_docs)
    )

    # Ensure roundtrip conversion to/from hex str does not modify vectors
    assert all(
        np.allclose(fv, _vector_from_hex_and_norm(*_vector_to_hex_and_norm(fv)))
        for fv in feature_vectors
    )


@pytest.mark.skipif(matgl is None, reason="matgl is not installed.")
def test_m3gnet_featurize():

    scorer = M3GNetSimilarity()
    fvs, dist_matrix = scorer.get_all_similarity_scores(list(structures.values()))

    assert fvs.shape == (len(structures), 128)

    ref_matrix = np.array(
        [
            [100.0, 3.274432636807312, 0.1410324007577568],
            [3.274432636807312, 100.0, 0.20956578539322868],
            [0.1410324007577568, 0.20956578539322868, 100.0],
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
