from itertools import groupby
from typing import Iterator

from emmet.builders.settings import EmmetBuildSettings
from emmet.core.tasks import CoreTaskDoc
from emmet.core.utils import group_structures, undeform_structure
from emmet.core.vasp.calc_types import TaskType
from emmet.core.vasp.material import MaterialsDoc
from pydantic import Field


class ValidationTaskDoc(CoreTaskDoc):
    """
    Wrapper for TaskDoc to ensure compatiblity with validation checks
    in MaterialsDoc.from_tasks(...) if validation builder is skipped
    """

    is_valid: bool = Field(True)


def build_material_docs(
    input_documents: list[ValidationTaskDoc],
    settings: EmmetBuildSettings = EmmetBuildSettings(),
) -> list[MaterialsDoc]:
    """
    Aggregate ValidationTaskDocs into MaterialsDocs by chemical formula.
    Caller is responsible for creating ValidationTaskDoc instances within
    their data pipeline context.

    Groups input documents by formula_pretty, performs structure matching
    on each formula group, and constructs a MaterialsDoc for each group of
    task documents with matching structures within each formula group.

    Args:
        input_documents: List of ValidationTaskDoc objects to process. Must contain
            ALL documents for each unique formula_pretty value to avoid incorrect
            material splitting. Documents for the same formula should not be split
            across multiple function calls.
        settings: Builder configuration settings, defaults defined in EmmetBuildSettings.
            Relevant settings: VASP_STRUCTURE_QUALITY_SCORES, VASP_USE_STATICS,
            VASP_ALLOWED_VASP_TYPES, LTOL, STOL, ANGLE_TOL, and SYMPREC.

    Returns:
        list[MaterialsDoc]
    """

    input_documents.sort(key=lambda x: x.formula_pretty)
    materials = []
    for _, group in groupby(input_documents, key=lambda x: x.formula_pretty):
        # TODO: logging - task_ids = [task.task_id for task in group]
        group = list(group)
        task_transformations = [task.transformations for task in group]
        grouped_tasks = filter_and_group_tasks(group, task_transformations, settings)
        for group in grouped_tasks:
            try:
                doc = MaterialsDoc.from_tasks(
                    group,
                    structure_quality_scores=settings.VASP_STRUCTURE_QUALITY_SCORES,
                    use_statics=settings.VASP_USE_STATICS,
                )
                materials.append(doc)
            except Exception as e:
                # TODO: logging - failed_ids = list({t_.task_id for t_ in group})
                doc = MaterialsDoc.construct_deprecated_material(group)
                doc.warnings.append(str(e))
                materials.append(doc)

    return materials


def filter_and_group_tasks(
    tasks: list[ValidationTaskDoc],
    task_transformations: list[dict | None],
    settings: EmmetBuildSettings,
) -> Iterator[list[ValidationTaskDoc]]:
    """Groups tasks by structure matching"""

    filtered_tasks = []
    filtered_transformations = []
    for task, transformations in zip(tasks, task_transformations):
        if any(
            allowed_type == task.task_type
            for allowed_type in settings.VASP_ALLOWED_VASP_TYPES
        ):
            filtered_tasks.append(task)
            filtered_transformations.append(transformations)
    structures = []
    for idx, (task, transformations) in enumerate(
        zip(filtered_tasks, filtered_transformations)
    ):
        if task.task_type == TaskType.Deformation:
            if transformations is None:
                # Do not include deformed tasks without transformation information
                continue
            else:
                s = undeform_structure(task.input.structure, transformations)
        else:
            s = task.output.structure

        s.index = idx
        structures.append(s)

    grouped_structures = group_structures(
        structures,
        ltol=settings.LTOL,
        stol=settings.STOL,
        angle_tol=settings.ANGLE_TOL,
        symprec=settings.SYMPREC,
    )
    for group in grouped_structures:
        grouped_tasks = [filtered_tasks[struct.index] for struct in group]
        yield grouped_tasks
