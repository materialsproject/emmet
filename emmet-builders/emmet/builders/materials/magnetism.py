from emmet.builders.base import BaseBuilderInput
from emmet.builders.utils import filter_map
from emmet.core.magnetism import MagnetismDoc
from emmet.core.material import PropertyOrigin


class MagnetismBuilderInput(BaseBuilderInput):
    total_magnetization: float
    origins: list[PropertyOrigin]


def build_magnetism_docs(
    input_documents: list[MagnetismBuilderInput], **kwargs
) -> list[MagnetismDoc]:
    """
    Generate magnetism documents from input structures.

    Transforms a list of MagnetismBuilderInput documents containing
    Pymatgen structures into corresponding MagnetismDoc instances by
    analyzing the magnetic configuration of each structure.

    Caller is responsible for creating MagnetismBuilderInput instances
    within their data pipeline context.

    Args:
        input_documents: List of MagnetismBuilderInput documents to process.

    Returns:
        list[MagnetismDoc]
    """

    return list(
        filter_map(
            MagnetismDoc.from_structure,
            input_documents,
            work_keys=[
                "deprecated",
                "material_id",
                "structure",
                "origins",
                "total_magnetization",
            ],
            **kwargs
        )
    )
