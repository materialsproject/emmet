from emmet.builders.base import BaseBuilderInput
from emmet.builders.utils import filter_map
from emmet.core.absorption import AbsorptionDoc
from emmet.core.material import PropertyOrigin
from emmet.core.types.typing import DateTimeType


class AbsorptionBuilderInput(BaseBuilderInput):
    energies: list[float]
    real_d: list[float]
    imag_d: list[float]
    absorption_co: list[float]
    bandgap: float | None
    nkpoints: int | None
    last_updated: DateTimeType
    origins: list[PropertyOrigin]


def build_absorption_docs(
    input_documents: list[AbsorptionBuilderInput], **kwargs
) -> list[AbsorptionDoc]:
    """
    Generate absorption documents from input structures.

    Transforms a list of AbsorptionBuilderInput documents containing
    Pymatgen structures into corresponding AbsorbtionDoc instances by
    generating an absorption spectrum based on frequency dependent
    dielectric function outputs.

    Caller is responsible for creating AbsorptionBuilderInput instances
    within their data pipeline context.

    Args:
        input_documents: List of AbsorptionBuilderInput documents to process.

    Returns:
       list[AbsorbtionDoc]
    """
    return list(
        filter_map(
            AbsorptionDoc.from_structure,
            input_documents,
            work_keys=[
                "energies",
                "real_d",
                "imag_d",
                "absorption_co",
                "bandgap",
                "nkpoints",
                "last_updated",
                "origins",
                # PropertyDoc.from_structure(...) kwargs
                "deprecated",
                "material_id",
                "structure",
            ],
            **kwargs
        )
    )
