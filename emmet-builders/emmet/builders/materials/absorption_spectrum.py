from datetime import datetime
from typing import Iterator

from emmet.builders.base import BaseBuilderInput
from emmet.builders.utils import _parse_kpoints, filter_map
from emmet.core.absorption import AbsorptionDoc
from emmet.core.material import PropertyOrigin
from emmet.core.mpid_ext import MaterialIdentifierType
from emmet.core.tasks import CoreTaskDoc
from emmet.core.types.typing import DateTimeType


class AbsorptionBuilderInput(BaseBuilderInput):
    energies: list[float]
    real_d: list[list[float]]
    imag_d: list[list[float]]
    absorption_co: list[float]
    bandgap: float | None
    nkpoints: int | None
    last_updated: DateTimeType
    origins: list[PropertyOrigin]


def build_absorption_docs(
    input_documents: list[AbsorptionBuilderInput], **kwargs
) -> Iterator[AbsorptionDoc]:
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
       Iterator[AbsorbtionDoc]
    """
    return filter_map(
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


def obtain_blessed_absorption_builder_input(
    tasks: list[CoreTaskDoc],
    material_id: MaterialIdentifierType | None = None,
    material_last_updated: datetime | None = None,
) -> AbsorptionBuilderInput:
    """
    Yield an AbsorptionBuilderInput
    from a list of CoreTaskDocs using the 'best' document in the list.

    [Optional] Relevant material properties needed if running in context of
    building properties for 'material's:
       - material_id -> anchor identifier for all ``tasks``
       - material_last_updated -> when anchor material document was last updated

    Relevant CoreTaskDoc fields needed:
       - task_id
       - last_updated
       - input.kpoints
       - input.structure
       - orig_inputs.kpoints
       - output.frequency_dependent_dielectric
       - output.optical_absorption_coeff
       - output.bandgap

    CoreTaskDocs need to have non-null optical_absorption_coeff
    and frequency_dependent_dielectric
    """
    relevant_tasks = [
        {
            "structure": task.input.structure,
            "task_id": task.task_id,
            "nkpoints": _parse_kpoints(task),
            "energies": task.output.frequency_dependent_dielectric.energy,
            "real_d": task.output.frequency_dependent_dielectric.real,
            "imag_d": task.output.frequency_dependent_dielectric.imaginary,
            "absorption_co": task.output.optical_absorption_coeff,
            "bandgap": task.output.bandgap,
            "task_last_updated": task.last_updated,
        }
        for task in tasks
        if task.input is not None
        and task.input.structure is not None
        and task.output is not None
        and task.output.optical_absorption_coeff is not None
        and task.output.frequency_dependent_dielectric is not None
        and task.output.frequency_dependent_dielectric.energy is not None
        and task.output.frequency_dependent_dielectric.real is not None
        and task.output.frequency_dependent_dielectric.imaginary is not None
    ]

    best_task = sorted(
        relevant_tasks,
        key=lambda doc: (
            # Entries with any None sort last (False < True, reversed)
            doc["nkpoints"] is not None and doc["task_last_updated"] is not None,
            doc["nkpoints"],
            doc["task_last_updated"],
        ),
        reverse=True,
    )[0]

    doc = {
        "material_id": material_id,
        "last_updated": material_last_updated,
        "origins": [
            PropertyOrigin(
                name="absorption",
                task_id=best_task["task_id"],
                last_updated=best_task["task_last_updated"],
            )
        ],
        **best_task,
    }

    return AbsorptionBuilderInput(**doc)
