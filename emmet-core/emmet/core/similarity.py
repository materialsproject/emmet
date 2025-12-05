"""Define metrics of similarity between structures."""

from __future__ import annotations

from functools import partial
import multiprocessing
from pathlib import Path
from typing import TYPE_CHECKING
import zlib

import numpy as np
from pydantic import BaseModel, Field

from emmet.core.material_property import PropertyDoc
from emmet.core.types.enums import ValueEnum

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


class SimilarityMethod(ValueEnum):
    """Indicate which method was used to score similarity."""

    CRYSTALNN = "CrystalNN"
    M3GNET = "M3GNet"


def _vector_to_hex_and_norm(vector: list[float]) -> tuple[str, float]:
    """Convert a list of floats to a hex string.

    Used internally to transfer/interpret vectors over a GET.

    Parameters
    -----------
    vector : Sequence of float

    Returns
    -----------
    str : the hex representation of the unit vector
    float : the norm of the vector
    """
    v = np.array(vector)
    vnorm = np.linalg.norm(v)
    return zlib.compress((v / vnorm).tobytes()).hex(), vnorm  # type: ignore[return-value]


def _vector_from_hex_and_norm(hexstr: str, vnorm: float) -> list[float]:
    """Convert a hex string to a list of floats.

    Used internally to transfer/interpret vectors over a GET.

    Parameters
    -----------
    str : the hex representation of the unit vector
    float : the norm of the vector

    Returns
    -----------
    list of float : the reconstructed vector
    """
    return (vnorm * np.frombuffer(zlib.decompress(bytes.fromhex(hexstr)))).tolist()


def _vector_difference_matrix_row(
    idxs: tuple[int, int],
    v: np.ndarray,
    norms: np.ndarray,
    dtype: np.dtype = np.dtype("float64"),
) -> tuple[tuple[int, int], np.ndarray]:
    """Compute the distance between a single vector and a list of other vectors.

    Parameters
    -----------
    idxs : the integer index of the vector in v to use as a fixed point
    v : the list of all possible vectors
    norms : the norms of the vectors in v
    dtype : the numpy dtype of working and returned arrays.

    Returns
    -----------
    int (copy of idxs) and np.ndarray of the squared vector distances.
    """
    inner = np.zeros((idxs[1] - idxs[0], v.shape[0]), dtype=dtype)
    _ = np.einsum("ik,jk->ij", v[idxs[0] : idxs[1]], v, out=inner)
    return idxs, np.array(
        [
            norms[idxs[0] : idxs[1]] + norms[i] - 2 * inner[:, i]
            for i in range(norms.shape[0])
        ],
        dtype=dtype,
    )


def vector_difference_matrix(
    v: np.ndarray,
    noise_floor: float = 1e-14,
    spread_rows: int = 0,
    dtype: np.dtype = np.dtype("float64"),
) -> np.ndarray:
    """Construct a symmetric matrix of vector differences.

    Given a list of vectors v, a symmetric matrix D such that:
        D_ij = | v_i - v_j |
        D_ji = D_ij

    if spread_rows is a positive int, then this will return only the
    upper triangle of D_ij, j >= i, and parallelize construction
    of the rows of D_ij.

    Parameters
    -----------
    v : numpy ndarray
        List of vectors. Axis = 0 should indicate distinct vectors,
        and axis = 1 their components.
    noise_floor : float = 1e-14
        Any values less than noise_floor will be zeroed out.
        Helps with loss of precision.
    spread_rows : int = 0
        The number of parallel processes to use in constructing
        the rows of D_ij
    dtype : the numpy dtype of the arrays used, defaults to float64
    """

    x = v.astype(dtype) if dtype != v.dtype else v.copy()
    vlen = x.shape[0]
    v_diff = np.zeros(2 * (vlen,), dtype=dtype)

    norms = np.zeros(vlen, dtype=dtype)
    _ = np.einsum("ik,ik->i", x, x, out=norms)

    if not spread_rows:
        inner = np.zeros(2 * (vlen,), dtype=dtype)
        _ = np.einsum("ik,jk->ij", x, x, out=inner)
        for i in range(vlen):
            v_diff[:, i] = norms + norms[i] - 2 * inner[:, i]
    else:
        func = partial(_vector_difference_matrix_row, v=x, norms=norms)
        with multiprocessing.Pool(spread_rows) as pool:
            vdiff_blocks = pool.map(
                func,
                [
                    (min(x), 1 + max(x))
                    for x in np.array_split(range(vlen), spread_rows)
                ],
            )

        for idxs, row in vdiff_blocks:
            v_diff[:, idxs[0] : idxs[1]] = row

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

    def _post_process_distance(
        self,
        distances: np.ndarray,
    ) -> np.ndarray:
        """Postprocess vector distances to yield consistent similarity scores.

        This method should return a percentage where 0% indicates no
        similarity, and 100% indicates identical structures.

        Defaults to normalizing vector distances by tanh.
        See CrystalNNSimilarity for another example.

        Parameters
        -----------
        distances : a matrix of structure feature vector distances.

        Returns
        -----------
        np.ndarray
        """
        return 100 * (1.0 - np.tanh(distances))

    def featurize_structures(
        self,
        structures: list[Structure],
        num_procs: int = 1,
    ):
        """Featurize structures using the user-defined _featurize_structure.

        This method may be preferred when dealing with huge sets
        of structures. In those cases, getting distances between
        structures may lead to memory errors.

        Parameters
        -----------
        structures : list of Structure objects
        num_procs : int = 1
            Number of parallel processes to run in featurizing structures.

        Returns
        -----------
        np.ndarray : the feature vectors of the input structures.
        """
        if num_procs > 1:
            with multiprocessing.Pool(num_procs) as pool:
                _feature_vectors = pool.map(self._featurize_structure, structures)
        else:
            _feature_vectors = [
                self._featurize_structure(structure) for structure in structures
            ]

        return np.array(_feature_vectors)

    def _get_closest_vectors(
        self, idx: int, v: np.ndarray, num: int
    ) -> tuple[np.ndarray, np.ndarray]:
        """Return only a subset of vectors most similar to a specified vector.

        Parameters
        -----------
        idx : the specific index of the vector list to isolate
        v : numpy ndarray, the list of vectors
        num : the number of closest vectors to return

        """
        dist = np.linalg.norm(v[idx] - v, axis=1)
        idxs = np.array([j for j in np.argpartition(dist, num) if j != idx])[:num]

        subset_dist = dist[idxs]
        sorted_subset_idx = np.argsort(subset_dist)

        return idxs[sorted_subset_idx], self._post_process_distance(
            subset_dist[sorted_subset_idx]
        )

    def get_all_similarity_scores(
        self,
        structures: list[Structure],
        num_procs: int = 1,
        **kwargs,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Rank the similarity between structures using CrystalNN.

        Parameters
        -----------
        structures : list of Structure objects
        num_procs : int = 1
            Number of parallel processes to run in featurizing structures.
        **kwargs
            Kwargs to pass to `vector_difference_matrix`

        Returns
        -----------
        tuple of np.ndarray, np.ndarray
            The first array contains the structure feature vectors,
            and the second their similarity scores.
        """

        feature_vectors = self.featurize_structures(structures, num_procs=num_procs)
        distances = vector_difference_matrix(feature_vectors, **kwargs)
        return feature_vectors, self._post_process_distance(distances)

    def get_most_similar(
        self,
        feature_vectors: np.ndarray,
        num_procs: int = 1,
        num_top: int = 100,
        labels: list[str] | None = None,
    ) -> dict[str, dict[str, list[str] | np.ndarray]]:
        """Rank the similarity between structures using CrystalNN.

        Parameters
        -----------
        feature_vectors : list of feature vectors
        num_procs : int = 1
            Number of parallel processes to run in featurizing structures.
        num_top : int or None
            If an int, returns that number of most similar structures
            indicated by their indices in the original list.
            If None, returns all distances.
        labels : list of str or None
            If a list of str, the labels corresponding to the feature vectors,
            e.g., MPIDs.
            If None, defaults to the list indices.

        Returns
        -----------
        dict[int,dict[str,np.ndarray]]], containing the index of
            the structure in `structures`, with a dict containing
            the `indices` of the top `num_top` most similar
            structures and their corresponding `distances`.
        """
        wrapped = partial(self._get_closest_vectors, v=feature_vectors, num=num_top)
        nfv = feature_vectors.shape[0]
        with multiprocessing.Pool(num_procs) as pool:
            meta = pool.map(wrapped, range(nfv))
        labels = labels or [str(idx) for idx in range(nfv)]
        return {
            labels[idx]: {
                "indices": [labels[idx] for idx in field[0]],
                "distances": field[1],
            }
            for idx, field in enumerate(meta)
        }

    def build_similarity_collection_from_structures(
        self,
        structures: dict[str, Structure],
        num_procs: int = 1,
        num_top: int = 100,
    ) -> list[SimilarityDoc]:
        """Build a collection of similarity documents.

        This defines the build pipeline for the MP similarity collection.

        Parameters
        -----------
        structures : dict of str (e.g., MPID) to a corresponding structure.
        num_procs : int = 1
            Number of parallel processes to run in featurizing structures.
        num_top : int or None
            If an int, returns that number of most similar structures
            indicated by their indices in the original list.
            If None, returns all distances.

        Returns
        -----------
        A list of SimilarityDoc.
        """

        identifiers = list(structures)
        ordered_structures = [structures[idx] for idx in identifiers]
        feature_vectors = self.featurize_structures(
            ordered_structures, num_procs=num_procs
        )
        sim_meta = self.get_most_similar(
            feature_vectors, num_procs=num_procs, num_top=num_top, labels=identifiers
        )
        return [
            SimilarityDoc.from_structure(
                meta_structure=structures[idx],
                material_id=idx,
                feature_vector=feature_vectors[i],
                sim=[
                    SimilarityEntry(
                        task_id=jdx,
                        nelements=len(structures[jdx].composition.elements),
                        dissimilarity=100.0 - meta["distances"][j],  # type: ignore[operator]
                        formula=structures[jdx].formula,
                    )
                    for j, jdx in enumerate(meta["indices"])
                ],
            )
            for i, (idx, meta) in enumerate(sim_meta.items())
        ]

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


class SimilarityDoc(PropertyDoc):
    """
    Model for a document containing structure similarity data
    """

    property_name: str = "similarity"

    sim: list[SimilarityEntry] | None = Field(
        None,
        description="List containing similar structure data for a given material.",
    )

    material_id: str | None = Field(
        None,
        description="The Materials Project ID for the material. This comes in the form: mp-******",
    )

    feature_vector: list[float] | None = Field(
        None, description="The feature / embedding vector of the structure."
    )

    method: SimilarityMethod | None = Field(
        None, description="The method used to score similarity."
    )
