import numpy as np

from emmet.builders.base import BaseBuilderInput
from emmet.core.similarity import (
    CrystalNNSimilarity,
    M3GNetSimilarity,
    SimilarityDoc,
    SimilarityEntry,
    SimilarityMethod,
)

SIM_METHOD_TO_SCORER = {
    SimilarityMethod(k): v
    for k, v in {
        "CrystalNN": CrystalNNSimilarity,
        "M3GNet": M3GNetSimilarity,
    }.items()
}


class SimilarityBuilderInput(BaseBuilderInput):
    """Augment base builder input with extra fields."""

    similarity_method: SimilarityMethod
    feature_vector: list[float]


# this could probably be parallelized over `similarity_method`
def build_feature_vectors(
    input_documents: list[BaseBuilderInput],
    similarity_method: SimilarityMethod | str = SimilarityMethod.CRYSTALNN,
) -> list[SimilarityBuilderInput]:
    """Generate similarity feature vectors.

    Args:
        input_documents : list of BaseBuilderInput to process
        similarity_method : SimilarityMethod = SimilarityMethod.CRYSTALNN
            The method to use in building similarity docs.
    Returns:
        list of SimilarityBuilderInput
    """
    if isinstance(similarity_method, str):
        similarity_method = (
            SimilarityMethod[similarity_method]
            if similarity_method in SimilarityMethod.__members__
            else SimilarityMethod(similarity_method)
        )

    if scorer_cls := SIM_METHOD_TO_SCORER.get(similarity_method):
        scorer = scorer_cls()
    else:
        raise ValueError(f"Unsupported {similarity_method=}")

    return list(
        map(
            lambda x: SimilarityBuilderInput(
                material_id=x.material_id,
                structure=x.structure,
                similarity_method=similarity_method,
                feature_vector=scorer._featurize_structure(x.structure),
            ),
            input_documents,
        )
    )


def build_similarity_docs(
    input_documents: list[SimilarityBuilderInput],
    num_closest: int = 100,
) -> list[SimilarityDoc]:
    """Generate similarity feature vectors.

    All input docs should use the same similarity method.
    A check is performed at the start to ensure this.

    Args:
        input_documents : list of SimilarityBuilderInput to process
        num_closest : int = 100
            The number of most similar materials to identify
            for each material
    Returns:
        list of SimilarityDoc
    """

    if (
        len(distinct_sim_methods := {doc.similarity_method for doc in input_documents})
        > 1
    ):
        raise ValueError(
            f"Multiple similarity methods found: {', '.join(distinct_sim_methods)}"
        )

    scorer_cls = SIM_METHOD_TO_SCORER[method := input_documents[0].similarity_method]
    material_ids, vectors, structures = np.array(
        [doc.material_id, doc.feature_vector, doc.structure] for doc in input_documents
    ).T

    similarity_docs = []
    for i, material_id in enumerate(material_ids):
        closest_idxs, closest_dist = scorer_cls._get_closest_vectors(
            i, vectors, num_closest
        )
        similarity_docs.append(
            SimilarityDoc.from_structure(
                meta_structure=structures[i],
                material_id=material_id,
                feature_vector=vectors[i],
                method=method,
                sim=[
                    SimilarityEntry(
                        task_id=material_ids[jdx],
                        nelements=len(structures[jdx].composition.elements),
                        dissimilarity=100.0 - closest_dist[j],
                        formula=structures[jdx].formula,
                    )
                    for j, jdx in enumerate(closest_idxs)
                ],
            )
        )
    return similarity_docs
