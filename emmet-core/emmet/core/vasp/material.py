""" Core definition of a Materials Document """
from datetime import datetime
from functools import partial
from typing import ClassVar, List, Mapping, Optional, Sequence, Union

from pydantic import BaseModel, Field, create_model
from pymatgen.analysis.structure_matcher import ElementComparator, StructureMatcher

from emmet.core import SETTINGS
from emmet.core.material import MaterialsDoc as CoreMaterialsDoc
from emmet.core.material import PropertyOrigin as CorePropertyOrigin
from emmet.core.structure import StructureMetadata
from emmet.core.vasp.calc_types import CalcType, RunType, TaskType
from emmet.core.vasp.task import TaskDocument
from emmet.stubs import ComputedEntry, Structure


class PropertyOrigin(CorePropertyOrigin):
    """
    Provenance document for the origin of properties in a material document from VASP calculations
    """

    calc_type: CalcType = Field(
        ..., description="The original calculation type this propeprty comes from"
    )


class MaterialsDoc(CoreMaterialsDoc, StructureMetadata):

    calc_types: Mapping[str, CalcType] = Field(
        None,
        description="Calculation types for all the calculations that make up this material",
    )
    task_types: Mapping[str, TaskType] = Field(
        None,
        description="Task types for all the calculations that make up this material",
    )
    run_types: Mapping[str, RunType] = Field(
        None,
        description="Run types for all the calculations that make up this material",
    )

    origins: Sequence[PropertyOrigin] = Field(
        None, description="Mappingionary for tracking the provenance of properties"
    )

    entries: Mapping[RunType, ComputedEntry] = Field(
        None, description="Dictionary for tracking entries for VASP calculations"
    )

    @classmethod
    def from_tasks(cls, task_group: List[TaskDocument]) -> "MaterialsDoc":
        """
        Converts a group of tasks into one material
        """

        # Metadata
        last_updated = max(task.last_updated for task in task_group)
        created_at = min(task.completed_at for task in task_group)
        task_ids = list({task.task_id for task in task_group})
        sandboxes = list({sbxn for task in task_group for sbxn in task.sandboxes})

        deprecated_tasks = list(
            {task.task_id for task in task_group if not task.is_valid}
        )
        run_types = {t.task_id: t.run_type for t in task_group}
        task_types = {t.task_id: t.task_type for t in task_group}
        calc_types = {t.task_id: t.calc_type for t in task_group}

        structure_optimizations = [
            task for task in task_group if task.task_type == "Structure Optimization"
        ]
        statics = [task for task in task_group if task.task_type == "Static"]

        # Material ID
        possible_mat_ids = [task.task_id for task in structure_optimizations]
        possible_mat_ids = sorted(possible_mat_ids, key=ID_to_int)

        if len(possible_mat_ids) == 0:
            raise Exception(f"Could not find a material ID for {task_ids}")
        else:
            material_id = possible_mat_ids[0]

        def _structure_eval(task: TaskDocument):
            """
            Helper function to order structures optimziation and statics calcs by
            - Functional Type
            - Spin polarization
            - Special Tags
            - Energy
            """
            qual_score = SETTINGS.vasp_qual_scores

            ispin = task.output.parameters.get("ISPIN", 1)
            energy = task.output.energy_per_atom
            task_run_type = task.run_type
            special_tags = [
                task.output.parameters.get(tag, False)
                for tag in SETTINGS.VASP_SPECIAL_TAGS
            ]

            is_valid = task.task_id in deprecated_tasks

            return (
                -1 * is_valid,
                -1 * qual_score.get(task_run_type, 0),
                -1 * ispin,
                -1 * sum(special_tags),
                energy,
            )

        structure_calcs = structure_optimizations + statics
        best_structure_calc = sorted(structure_calcs, key=_structure_eval)[0]
        structure = best_structure_calc.output.structure

        # Initial Structures
        initial_structures = [t.input.structure for t in task_group]
        sm = StructureMatcher(
            ltol=0.1, stol=0.1, angle_tol=0.1, scale=False, attempt_supercell=False
        )
        initial_structures = [
            group[0] for group in sm.group_structures(initial_structures)
        ]

        # Deprecated
        deprecated = all(t.task_id in deprecated_tasks for t in structure_optimizations)

        # Origins
        origins = [
            PropertyOrigin(
                name="structure",
                task_type=best_structure_calc.task_type,
                calc_type=best_structure_calc.calc_type,
                task_id=best_structure_calc.task_id,
                last_updated=best_structure_calc.last_updated,
            )
        ]

        # entries
        entries = {}
        all_run_types = set(run_types.keys())
        for rt in all_run_types:

            relevant_calcs = sorted(
                [doc for doc in structure_calcs if doc.run_type == rt],
                key=_structure_eval,
            )
            if len(relevant_calcs) > 0:
                best_task_doc = relevant_calcs[0]
                entry = best_task_doc.entry
                entry.data["task_id"] = entry.entry_id
                entry.entry_id = material_id
                entries[rt] = entry

        # Warnings
        # TODO: What warning should we process?

        return MaterialsDoc.from_structure(
            structure=structure,
            material_id=material_id,
            last_updated=last_updated,
            created_at=created_at,
            task_ids=task_ids,
            calc_types=calc_types,
            run_types=run_types,
            task_types=task_types,
            initial_structures=initial_structures,
            deprecated=deprecated,
            deprecated_tasks=deprecated_tasks,
            origins=origins,
            entries=entries,
            sandboxes=sandboxes if sandboxes else None,
        )


def ID_to_int(s_id: str) -> int:
    """
    Converts a string id to tuple
    falls back to assuming ID is an Int if it can't process
    Assumes string IDs are of form "[chars]-[int]" such as mp-234
    """
    if isinstance(s_id, str):
        return (s_id.split("-")[0], int(str(s_id).split("-")[-1]))
    elif isinstance(s_id, (int, float)):
        return s_id
    else:
        return None
