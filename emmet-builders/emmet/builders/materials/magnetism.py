from emmet.builders.base import BaseBuilderInput
from emmet.builders.utils import try_call
from emmet.core.magnetism import MagnetismDoc
from emmet.core.material import PropertyOrigin


class MagnetismBuilderInput(BaseBuilderInput):
    total_magnetization: float
    origins: list[PropertyOrigin]


def build_magnetism_docs(
    input_documents: list[BaseBuilderInput],
) -> list[MagnetismDoc]:
    """
    Generate magnetism documents from input structures.

    Transforms a list of BaseBuilderInput documents containing
    Pymatgen structures into corresponding MagnetismDoc instances by
    analyzing the magnetic configuration of each structure.

    Caller is responsible for creating BaseBuilderInput instances
    within their data pipeline context.

    Args:
        input_documents: List of BaseBuilderInput documents to process.

    Returns:
        list[MagnetismDoc]
    """
    return list(
        filter(
            lambda y: y is not None,
            map(
                lambda x: try_call(
                    MagnetismDoc.from_structure,
                    deprecated=x.deprecated,
                    material_id=x.material_id,
                    structure=x.structure,
                    origins=x.origins,
                    total_magnetization=x.total_magnetization,
                ),
                input_documents,
            ),
        )
    )
