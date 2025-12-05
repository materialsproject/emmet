from emmet.builders.base import BaseBuilderInput
from emmet.core.chemenv import ChemEnvDoc


def build_chemenv_docs(
    input_documents: list[BaseBuilderInput],
) -> list[ChemEnvDoc]:
    """
    Generate chemical environment documents from input structures.

    Transforms a list of BaseBuilderInput documents containing
    Pymatgen structures into corresponding ChemEnvDoc instances by
    analyzing the chemical environment of each structure.

    Caller is responsible for creating BaseBuilderInput instances
    within their data pipeline context.

    Args:
        input_documents: List of BaseBuilderInput documents to process.

    Returns:
        list[ChemEnvDoc]
    """
    return list(
        map(
            lambda x: ChemEnvDoc.from_structure(
                builder_meta=x.builder_meta,
                deprecated=x.deprecated,
                material_id=x.material_id,
                structure=x.structure,
            ),
            input_documents,
        )
    )
