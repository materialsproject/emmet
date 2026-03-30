import numpy as np
from pydantic import BaseModel, Field
from pymatgen.io.validation.check_kpoints_kspacing import (
    get_kpoint_divisions_from_kspacing,
)

from emmet.builders.utils import filter_map
from emmet.core.materials import MaterialsDoc
from emmet.core.math import Matrix3D, Vector6D
from emmet.core.polar import DielectricDoc, PiezoelectricDoc
from emmet.core.tasks import CoreTaskDoc
from emmet.core.types.pymatgen_types.structure_adapter import StructureType
from emmet.core.types.typing import IdentifierType, NullableDateTimeType
from emmet.core.vasp.calc_types.enums import TaskType

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


PIEZO_TENSOR_TYPE = tuple[Vector6D, Vector6D, Vector6D]


class MaterialsTasksMap(BaseModel):
    material_id: IdentifierType
    task_ids: list[IdentifierType] = Field(default_factory=list)


class LinearResponseBuilderInput(BaseModel):

    structure: StructureType
    material_id: IdentifierType
    task_id: IdentifierType
    nkpoints: int
    epsilon_static: Matrix3D | None
    epsilon_ionic: Matrix3D | None
    piezo_static: PIEZO_TENSOR_TYPE | None
    piezo_ionic: PIEZO_TENSOR_TYPE | None
    is_hubbard: int
    last_updated: NullableDateTimeType
    task_last_updated: NullableDateTimeType


# This needs to retrieve + process materials + dielectric tasks
def identify_relevant_tasks(
    materials_docs: list[MaterialsDoc],
) -> list[MaterialsTasksMap]:
    return list(
        filter(
            lambda y: len(y.task_ids) > 0,
            map(
                lambda doc: MaterialsTasksMap(
                    material_id=doc.material_id,
                    task_ids=[
                        task_id
                        for task_id, task_type in doc.task_types.items()
                        if task_type == TaskType.DFPT_Dielectric
                    ],
                ),
                materials_docs,
            ),
        )
    )


def _parse_kpoints(task: CoreTaskDoc) -> int:

    for inp_field in ("input", "orig_inputs"):
        if (
            kpts := getattr(getattr(task, inp_field, None), "kpoints", None)
        ) is not None:
            break

    if kpts is None:
        if isinstance(dk := (task.input.incar or {}).get("KSPACING"), float):
            return np.prod(get_kpoint_divisions_from_kspacing(task.structure, dk))
        return 0

    if kpts.style.name in ("Monkhorst", "Gamma"):
        return np.prod(kpts.kpts[0])
    return task.orig_inputs.kpoints.num_kpts


def build_linear_response_input(
    material_doc: MaterialsDoc, tasks: list[CoreTaskDoc]
) -> LinearResponseBuilderInput | None:

    relevant_tasks = [
        LinearResponseBuilderInput(
            structure=task.input.structure,
            material_id=material_doc.material_id,
            task_id=task.task_id,
            nkpoints=_parse_kpoints(task),
            **{
                k: task.output.outcar.get(k)
                for k in (
                    "epsilon_static",
                    "epsilon_ionic",
                    "piezo_static",
                    "piezo_ionic",
                )
            },
            is_hubbard=int(task.input.is_hubbard),
            last_updated=material_doc.last_updated,
            task_last_updated=task.last_updated,
        )
        for task in tasks
        if task.output.bandgap > 0.0
    ]

    if len(relevant_tasks) == 0:
        return None

    return sorted(
        relevant_tasks,
        key=lambda doc: (
            doc.is_hubbard,
            doc.nkpoints,
            doc.updated_on,
        ),
        reverse=True,
    )[0]


def build_dielectric_docs(
    linear_resp_input: list[LinearResponseBuilderInput],
) -> list[DielectricDoc]:
    return list(
        filter(
            lambda y: y is not None,
            map(
                lambda doc: DielectricDoc.from_ionic_and_electronic(
                    structure=doc.structure,
                    material_id=doc.material_id,
                    origins=[
                        {
                            "name": "piezoelectric",
                            "task_id": doc.task_id,
                            "last_updated": doc.task_last_updated,
                        }
                    ],
                    deprecated=False,
                    ionic=doc.epsilon_ionic,
                    electronic=doc.epsilon_static,
                    last_updated=doc.last_updated,
                ),
                linear_resp_input,
            ),
        )
    )


def build_piezo_docs(
    linear_resp_input: list[LinearResponseBuilderInput],
) -> list[PiezoelectricDoc]:
    return list(
        filter(
            lambda y: y is not None,
            map(
                lambda doc: (
                    PiezoelectricDoc.from_ionic_and_electronic(
                        structure=doc.structure,
                        material_id=doc.material_id,
                        origins=[
                            {
                                "name": "piezoelectric",
                                "task_id": doc.task_id,
                                "last_updated": doc.task_last_updated,
                            }
                        ],
                        deprecated=False,
                        ionic=doc.piezo_ionic,
                        electronic=doc.piezo_static,
                        last_updated=doc.last_updated,
                    )
                    if doc.structure.get_space_group_info()[0]
                    not in CENTROSYMMETRIC_SPACE_GROUPS
                    else None
                ),
                linear_resp_input,
            ),
        )
    )
