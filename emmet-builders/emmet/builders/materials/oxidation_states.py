from emmet.builders.base import BaseBuilderInput
from emmet.core.oxidation_states import OxidationStateDoc


def build_oxidation_states_docs(
    input_documents: list[BaseBuilderInput],
) -> list[OxidationStateDoc]:
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
        list[OxidationStateDoc]
    """
    return list(
        map(
            lambda x: OxidationStateDoc.from_structure(
                builder_meta=x.builder_meta,
                deprecated=x.deprecated,
                material_id=x.material_id,
                structure=x.structure,
            ),
            input_documents,
        )
    )
