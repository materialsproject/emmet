from datetime import datetime
from typing import Iterator, Literal, TypeVar

from emmet.builders.base import BaseBuilderInput
from emmet.builders.utils import _parse_kpoints, filter_map
from emmet.core.material import PropertyOrigin
from emmet.core.math import Matrix3D, Vector6D
from emmet.core.polar import DielectricDoc, PiezoelectricDoc
from emmet.core.tasks import CoreTaskDoc
from emmet.core.types.typing import MaterialIdentifierType, NullableDateTimeType

PIEZO_TENSOR_TYPE = tuple[Vector6D, Vector6D, Vector6D]


class BaseLinearResponseInput(BaseBuilderInput):
    last_updated: NullableDateTimeType
    origins: list[PropertyOrigin]


class DielectricBuilderInput(BaseLinearResponseInput):
    epsilon_static: Matrix3D
    epsilon_ionic: Matrix3D


class PiezoelectricBuilderInput(BaseLinearResponseInput):
    piezo_static: PIEZO_TENSOR_TYPE
    piezo_ionic: PIEZO_TENSOR_TYPE


def build_dielectric_docs(
    linear_resp_input: list[DielectricBuilderInput], **kwargs
) -> Iterator[DielectricDoc]:
    return filter_map(
        DielectricDoc.from_ionic_and_electronic,
        linear_resp_input,
        work_keys=[
            "deprecated",
            "material_id",
            "structure",
            "origins",
            "epsilon_static",
            "epsilon_ionic",
            "last_updated",
        ],
        **kwargs,
    )


def build_piezo_docs(
    linear_resp_input: list[PiezoelectricBuilderInput],
    **kwargs,
) -> Iterator[PiezoelectricDoc]:
    return filter_map(
        PiezoelectricDoc.from_ionic_and_electronic,
        linear_resp_input,
        work_keys=[
            "deprecated",
            "material_id",
            "structure",
            "origins",
            "piezo_static",
            "piezo_ionic",
            "last_updated",
        ],
        **kwargs,
    )


# -----------------------------------------------------------------------------
# Helper funcs + types
# -----------------------------------------------------------------------------

CENTROSYMMETRIC_SPACE_GROUPS = [
    "-1",
    "2/m",
    "mmm",
    "4/m",
    "4/mmm",
    "-3",
    "-3m",
    "6/m",
    "6/mmm",
    "m-3",
    "m-3m",
]


def filter_piezo_tasks(
    tasks: list[CoreTaskDoc],
) -> list[CoreTaskDoc | None]:
    """
    Yields list of CoreTaskDocs with spacegroups appropriate for
    ``build_piezo_docs``

    Can be used to filter input ``tasks`` for ``obtain_blessed_linear_builder_input``
    """
    return list(
        filter(
            lambda x: x.input.structure.get_space_group_info()[0]
            in CENTROSYMMETRIC_SPACE_GROUPS,
            tasks,
        )
    )


T = TypeVar("T", DielectricBuilderInput, PiezoelectricBuilderInput)


def obtain_blessed_linear_builder_input(
    tasks: list[CoreTaskDoc],
    property_name: Literal["dielectric", "piezoelectric"],
    target: T,
    material_id: MaterialIdentifierType | None = None,
    material_last_updated: datetime | None = None,
) -> T:
    """
    Yield a target document [``DielectricBuilderInput | PiezoelectricBuilderInput``]
    from a list of CoreTaskDocs using the 'best' document in the list.

    [Optional] Relevant material properties needed if running in context of
    building properties for 'material's:
       - material_id -> anchor identifier for all ``tasks``
       - material_last_updated -> when anchor material document was last updated

    Relevant CoreTaskDoc fields needed:
        - task_id
        - last_updated
        - input.is_hubbard
        - input.kpoints
        - input.structure
        - orig_inputs.kpoints
        - output.outcar
        - output.bandgap
        - output.epsilon_ionic
        - output.epsilon_static
    CoreTaskDocs need to have non-null bandgap
    """
    relevant_tasks = [
        {
            "structure": task.input.structure,
            "task_id": task.task_id,
            "nkpoints": _parse_kpoints(task),
            **{
                k: getattr(task.output, k)
                for k in (
                    "epsilon_static",
                    "epsilon_ionic",
                )
            },
            **{
                k: task.output.outcar.get(k)
                for k in (
                    "piezo_static",
                    "piezo_ionic",
                )
            },
            "is_hubbard": int(task.input.is_hubbard),
            "task_last_updated": task.last_updated,
        }
        for task in tasks
        if task.output.bandgap > 0.0
    ]

    best_task = sorted(
        relevant_tasks,
        key=lambda doc: (
            # Entries with any None sort last (False < True, reversed)
            doc["is_hubbard"] is not None
            and doc["nkpoints"] is not None
            and doc["task_last_updated"] is not None,
            doc["is_hubbard"],
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
                name=property_name,
                task_id=best_task["task_id"],
                last_updated=best_task["task_last_updated"],
            )
        ],
        **best_task,
    }

    return target(**doc)
