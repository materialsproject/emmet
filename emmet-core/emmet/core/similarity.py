"""Define metrics of similarity between structures."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
from pydantic import BaseModel, Field

try:
    from matminer.featurizers.structure.sites import SiteStatsFingerprint
    from matminer.featurizers.site.fingerprint import CrystalNNFingerprint
except ImportError:
    SiteStatsFingerprint = None
    CrystalNNFingerprint = None

try:
    import matgl
except ImportError:
    matgl = None  # type: ignore[assignment]


if TYPE_CHECKING:

    from matminer.featurizers.base import BaseFeaturizer
    from pymatgen.core import Structure


def vector_difference_matrix(
    v: np.ndarray,
    noise_floor: float = 1e-14,
    spread_rows: bool = False,
) -> np.ndarray:
    """Construct a symmetric matrix of vector differences.

    Given a list of vectors v, a symmetric matrix D such that:
        D_ij = | v_i - v_j |
        D_ji = D_ij

    if spread_rows is True, then this will return only the
    upper triangle of D_ij, j >= i, and perform a loop
    over the rows of D.

    Parameters
    -----------
    v : numpy ndarray
        List of vectors. Axis = 0 should indicate distinct vectors,
        and axis = 1 their components.
    noise_floor : float = 1e-15
        Any values less than noise_floor will be zeroed out.
        Helps with loss of precision.
    spread_rows : bool = False
        Whether to loop over rows and only construct the upper
        triangle.
    """

    vlen = v.shape[0]
    v_diff = np.zeros(2 * (vlen,))

    norms = np.zeros(vlen)
    _ = np.einsum("ik,ik->i", v, v, out=norms)

    if not spread_rows:
        inner = np.zeros(2 * (vlen,))
        _ = np.einsum("ik,jk->ij", v, v, out=inner)
        for i in range(vlen):
            v_diff[:, i] = norms + norms[i] - 2 * inner[:, i]
    else:

        for i in range(vlen):
            inner = np.einsum("jk,k->j", v[i:], v[i])
            v_diff[i, i:] = norms[i] + norms[i:] - 2 * inner

    v_diff[v_diff < noise_floor] = 0.0
    return v_diff ** (0.5)


class SimilarityScorer:
    """Mixin for ranking the similarity between structures.

    Parameters
    -----------
    fingerprinter: BaseFeaturizer or None (default)
        A structural featurizer. If None, defaults to the
        featurizer used in the above reference.
    """

    def _featurize_structure(self, structure: Structure) -> np.ndarray:
        """Featurize a single structure using a user implemented method

        Parameters
        -----------
        structure : Structure

        Returns
        -----------
        np.ndarray
        """
        raise NotImplementedError

    def _post_process_distance(self, distances: np.ndarray) -> np.ndarray:
        """Optional postprocessing to be implemented by the user.

        This can allow for weighting the difference in structural feature vectors.
        See CrystalNNSimilarity for an example.

        Parameters
        -----------
        distances : a matrix of structure feature vector distances.

        Returns
        -----------
        np.ndarray
        """
        return distances

    def get_similarity_scores(
        self,
        structures: list[Structure],
        num_procs: int = 1,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Rank the similarity between structures using CrystalNN.

        Reference: 10.1039/C9RA07755C

        Parameters
        -----------
        structures : list of Structure objects
        num_procs : int = 1
            Number of parallel processes to run in featurizing structures.

        Returns
        -----------
        tuple of np.ndarray, np.ndarray
            The first array contains the structure feature vectors,
            and the second their similarity scores.
        """

        if num_procs > 1:
            import multiprocessing

            with multiprocessing.Pool(num_procs) as pool:
                _feature_vectors = pool.map(self._featurize_structure, structures)
        else:
            _feature_vectors = [
                self._featurize_structure(structure) for structure in structures
            ]

        feature_vectors = np.array(_feature_vectors)

        distances = vector_difference_matrix(feature_vectors)
        return feature_vectors, self._post_process_distance(distances)

    @staticmethod
    def get_vendi_score(feature_vectors: np.ndarray) -> float:
        """Get the Vendi score of a set of feature vectors.

        Uses the conventions described in arXiv:2210.02410
        Describes the diveristy of a set of structures.

        Parameters
        -----------
        feature_vectors : np.ndarray
            The feature vectors, such as those from
            SimilarityScorer._featurize_structure
            Each row should be a distinct feature vector.

        Returns
        -----------
        float, the Vendi score.
            A Vendi score close to feature_vectors.shape[0] indicates
            high sample diversity, and a Vendi score close to
            1 indicates low sample diversity.
        """

        # Remove NaN rows
        non_nan_fv = feature_vectors[~np.any(np.isnan(feature_vectors), axis=1)]

        norms = np.einsum("ik,ik->i", non_nan_fv, non_nan_fv) ** (-0.5)
        norm_fv = np.einsum("ij,i->ij", non_nan_fv, norms)

        k_mat = np.einsum("ik,jk->ij", norm_fv, norm_fv)

        num_samp = non_nan_fv.shape[0]
        eigs = np.linalg.eigvalsh(k_mat) / num_samp
        log_eigs = np.zeros(num_samp)
        mask = eigs > 0.0
        log_eigs[mask] = np.log(eigs[mask])
        return np.exp(-np.einsum("i,i", eigs, log_eigs))


class CrystalNNSimilarity(SimilarityScorer):
    """Rank the similarity between structures using CrystalNN.

    Reference: 10.1039/C9RA07755C

    Parameters
    -----------
    fingerprinter: BaseFeaturizer or None (default)
        A structural featurizer. If None, defaults to the
        featurizer used in the above reference.
    """

    def __init__(self, fingerprinter: BaseFeaturizer | None = None) -> None:

        if fingerprinter is None and SiteStatsFingerprint is None:
            raise ImportError(
                "Please `pip install matminer` to use featurizer functionality."
            )

        self.fingerprinter = fingerprinter or SiteStatsFingerprint(
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
        self.num_feature = len(self.fingerprinter.feature_labels())

    def _featurize_structure(self, structure: Structure) -> np.ndarray:
        """Featurize a single structure using CrystalNN.

        Parameters
        -----------
        structure : Structure

        Returns
        -----------
        np.ndarray
        """

        try:
            return np.array(self.fingerprinter.featurize(structure))
        except Exception:
            return np.nan * np.ones(self.num_feature)

    def _post_process_distance(self, distances: np.ndarray) -> np.ndarray:
        """Use exponential weighting of feature vector distances.

        Parameters
        -----------
        distances : a matrix of structure feature vector distances.

        Returns
        -----------
        np.ndarray
        """
        return 100 * np.exp(-distances)


class M3GNetSimilarity(SimilarityScorer):
    """Obtain structural similarity using an M3GNet formation energy model.

    Parameters
    -----------
    model :  str or Path
        Model for computing feature vectors of a structure.
        Defaults to "M3GNet-MP-2018.6.1-Eform"
    """

    def __init__(self, model: str | Path = "M3GNet-MP-2018.6.1-Eform"):

        if matgl is None:
            raise ValueError("`pip install matgl` to use these features.")

        self.model = matgl.load_model(Path(model)).model

    def _featurize_structure(self, structure: Structure) -> np.ndarray:
        """Featurize a single structure using M3GNet-Eform.

        Parameters
        -----------
        structure : Structure

        Returns
        -----------
        np.ndarray
        """
        results = self.model.predict_structure(structure, return_features=True)
        return results["readout"].detach().cpu().numpy()[0]


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
