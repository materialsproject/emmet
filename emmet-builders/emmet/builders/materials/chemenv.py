from emmet.builders.base import BaseBuilderInput
from emmet.builders.utils import try_call
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
        filter(
            lambda y: y is not None,
            map(
                lambda x: try_call(
                    ChemEnvDoc.from_structure,
                    deprecated=x.deprecated,
                    material_id=x.material_id,
                    structure=x.structure,
                ),
                input_documents,
            ),
        )
    )
