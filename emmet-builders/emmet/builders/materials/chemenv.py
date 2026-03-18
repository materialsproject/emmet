from emmet.builders.base import BaseBuilderInput
from emmet.builders.utils import filter_map
from emmet.core.chemenv import ChemEnvDoc


def build_chemenv_docs(
    input_documents: list[BaseBuilderInput], **kwargs
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
        filter_map(
            ChemEnvDoc.from_structure,
            input_documents,
            work_keys=["deprecated", "material_id", "structure", "builder_meta"],
            **kwargs
        )
    )
