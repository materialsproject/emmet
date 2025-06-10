"""Define metrics of similarity between structures."""
from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from pydantic import BaseModel, Field

from monty.dev import requires

try:
    from matminer.featurizers.structure.sites import SiteStatsFingerprint
    from matminer.featurizers.site.fingerprint import CrystalNNFingerprint
except ImportError:
    SiteStatsFingerprint = None
    CrystalNNFingerprint = None

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pymatgen.core import Structure


@requires(
    SiteStatsFingerprint is not None,
    message="Please `pip install matminer` to use this functionality.",
)
def featurize_structures(structures: Sequence[Structure]) -> np.ndarray:
    """Return the feature vector of structure for estimating similarities.

    Reference: 10.1039/C9RA07755C

    Parameters
    -----------
    structure : Structure

    Returns
    -----------
    list of np.ndarray
    """
    fingerprinter = SiteStatsFingerprint(
        CrystalNNFingerprint.from_preset(
            "ops",
            distance_cutoffs=None,
            x_diff_weight=None,
        ),
        stats=(
            "mean",
            "maximum",
        ),
    )

    nfeature = len(fingerprinter.feature_labels())
    fvs = np.zeros((len(structures), nfeature))
    for i, structure in enumerate(structures):
        try:
            fv = np.array(fingerprinter.featurize(structure))
        except Exception:
            fv = np.nan * np.ones(nfeature)
        fvs[i] = fv
    return fvs


def structure_distance_matrix(feature_vectors: np.ndarray) -> np.ndarray:
    """
    Return a matrix of similarity scores between structures.

    For N feature vectors, this returns an NxN symmetric matrix of
    similarity scores in percent between structures.

    Parameters
    -----------
    feature_vectors : np.ndarray

    Returns
    -----------
    np.ndarray, a rank-2 matrix of floats
    """
    dim = feature_vectors.shape[0]
    distance_matrix = np.zeros((dim, dim))
    for i in range(dim):
        distance_matrix[i] = np.exp(
            -np.linalg.norm(feature_vectors[i] - feature_vectors, axis=1)
        )
    return 100 * distance_matrix


class SimilarityEntry(BaseModel):
    """
    Find similar materials to a specified material based on crystal geometry.
    """

    task_id: str | None = Field(
        None,
        description="The Materials Project ID for the matched material. This comes in the form: mp-******.",
    )

    nelements: int | None = Field(
        None,
        description="Number of elements in the matched material.",
    )

    dissimilarity: float | None = Field(
        None,
        description="Dissimilarity measure for the matched material in %.",
    )

    formula: str | None = Field(
        None,
        description="Formula of the matched material.",
    )


class SimilarityDoc(BaseModel):
    """
    Model for a document containing structure similarity data
    """

    sim: list[SimilarityEntry] | None = Field(
        None,
        description="List containing similar structure data for a given material.",
    )

    material_id: str | None = Field(
        None,
        description="The Materials Project ID for the material. This comes in the form: mp-******",
    )
