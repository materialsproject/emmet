from typing import Iterator

from emmet.builders.base import BaseBuilderInput
from emmet.builders.utils import filter_map
from emmet.core.oxidation_states import OxidationStateDoc


def build_oxidation_states_docs(
    input_documents: list[BaseBuilderInput], **kwargs
) -> Iterator[OxidationStateDoc]:
    """
    Generate oxidation state documents from input structures.

    Transforms a list of BaseBuilderInput documents containing
    Pymatgen structures into corresponding OxidationStateDoc instances by
    analyzing the oxidation states of each structure.

    Caller is responsible for creating BaseBuilderInput instances
    within their data pipeline context.

    Args:
        input_documents: List of BaseBuilderInput documents to process.

    Returns:
        Iterator[OxidationStateDoc]
    """
    return filter_map(
        OxidationStateDoc.from_structure,
        input_documents,
        work_keys=[
            "deprecated",
            "material_id",
            "structure",
            "builder_meta",
        ],
        **kwargs
    )
