""" Core definition of a Materials Document """

import json
from typing import Dict, List, Mapping, Optional

from pydantic import BaseModel, Field, field_validator, model_serializer
from pymatgen.analysis.structure_analyzer import SpacegroupAnalyzer
from pymatgen.analysis.structure_matcher import StructureMatcher

from emmet.core import ARROW_COMPATIBLE
from emmet.core.base import EmmetMeta
from emmet.core.material import MaterialsDoc as CoreMaterialsDoc
from emmet.core.material import PropertyOrigin
from emmet.core.serialization_adapters.computed_entries_adapter import (
    AnnotatedComputedStructureEntry,
)
from emmet.core.settings import EmmetSettings
from emmet.core.structure import StructureMetadata
from emmet.core.tasks import TaskDoc
from emmet.core.utils import jsanitize
from emmet.core.vasp.calc_types import CalcType, RunType, TaskType

SETTINGS = EmmetSettings()


class BlessedCalcs(BaseModel, populate_by_name=True):
    GGA: AnnotatedComputedStructureEntry | None = Field(None)
    GGA_U: AnnotatedComputedStructureEntry | None = Field(None, alias="GGA+U")
    PBESol: AnnotatedComputedStructureEntry | None = Field(None, alias="PBEsol")
    SCAN: AnnotatedComputedStructureEntry | None = Field(None)
    R2SCAN: AnnotatedComputedStructureEntry | None = Field(None, alias="r2SCAN")
    HSE: AnnotatedComputedStructureEntry | None = Field(None)

    @model_serializer(mode="wrap")
    def model_serialization(self, default_serializer, info):
        default_serialized_model = default_serializer(self, info)

        format = info.context.get("format") if info.context else "standard"
        if format == "arrow":
            arrow_compat_model = jsanitize(default_serialized_model, allow_bson=True)
            for entry in arrow_compat_model.values():
                # cast as str, de-serializing unions is not yet supported in pyarrow
                if entry:
                    entry["energy_adjustments"] = json.dumps(
                        entry["energy_adjustments"]
                    )
            return arrow_compat_model

        return default_serialized_model

    @field_validator("*", mode="before")
    def entry_deserializer(cls, entry):
        if ARROW_COMPATIBLE:
            if isinstance(entry, dict) and isinstance(
                entry.get("energy_adjustments"), str
            ):
                entry["energy_adjustments"] = json.loads(entry["energy_adjustments"])
        return entry


class MaterialsDoc(CoreMaterialsDoc, StructureMetadata):
    calc_types: Optional[Mapping[str, CalcType]] = Field(  # type: ignore
        None,
        description="Calculation types for all the calculations that make up this material",
    )
    task_types: Optional[Mapping[str, TaskType]] = Field(
        None,
        description="Task types for all the calculations that make up this material",
    )
    run_types: Optional[Mapping[str, RunType]] = Field(
        None,
        description="Run types for all the calculations that make up this material",
    )

    origins: Optional[List[PropertyOrigin]] = Field(
        None, description="Mappingionary for tracking the provenance of properties"
    )

    entries: Optional[BlessedCalcs] = Field(
        None, description="Dictionary for tracking entries for VASP calculations"
    )

    @classmethod
    def from_tasks(
        cls,
        task_group: List[TaskDoc],
        structure_quality_scores: Dict[
            str, int
        ] = SETTINGS.VASP_STRUCTURE_QUALITY_SCORES,
        use_statics: bool = SETTINGS.VASP_USE_STATICS,
        commercial_license: bool = True,
    ) -> "MaterialsDoc":
        """
        Converts a group of tasks into one material

        Args:
            task_group: List of task document
            structure_quality_scores: quality scores for various calculation types
            use_statics: Use statics to define a material
            commercial_license: Whether the data should be licensed with BY-C (otherwise BY-NC).
        """
        if len(task_group) == 0:
            raise Exception("Must have more than one task in the group.")

        # Metadata
        last_updated = max(task.last_updated for task in task_group)
        created_at = min(task.completed_at for task in task_group)
        task_ids = list({task.task_id for task in task_group})

        deprecated_tasks = {task.task_id for task in task_group if not task.is_valid}
        run_types = {task.task_id: task.run_type for task in task_group}
        task_types = {task.task_id: task.task_type for task in task_group}
        calc_types = {task.task_id: task.calc_type for task in task_group}

        structure_optimizations = [
            task for task in task_group if task.task_type == TaskType.Structure_Optimization  # type: ignore
        ]
        statics = [task for task in task_group if task.task_type == TaskType.Static]  # type: ignore
        structure_calcs = (
            structure_optimizations + statics
            if use_statics
            else structure_optimizations
        )

        validity_check = [doc for doc in structure_calcs if doc.is_valid]
        if not validity_check:
            raise ValueError("Group must contain at least one valid task")

        # Material ID
        possible_mat_ids = [task.task_id for task in structure_optimizations]

        if use_statics:
            possible_mat_ids += [task.task_id for task in statics]

        material_id = min(possible_mat_ids)

        # Always prefer a static over a structure opt
        structure_task_quality_scores = {"Structure Optimization": 1, "Static": 2}

        def _structure_eval(task: TaskDoc):
            """
            Helper function to order structures optimization and statics calcs by
            - Functional Type
            - Spin polarization
            - Special Tags
            - Energy
            """

            task_run_type = task.run_type
            _SPECIAL_TAGS = ["LASPH", "ISPIN"]
            special_tags = sum(
                (
                    task.input.parameters.get(tag, False)
                    if task.input.parameters
                    else False
                )
                for tag in _SPECIAL_TAGS
            )

            return (
                -1 * int(task.is_valid),
                -1 * structure_quality_scores.get(task_run_type.value, 0),
                -1 * structure_task_quality_scores.get(task.task_type.value, 0),
                -1 * special_tags,
                task.output.energy_per_atom,
            )

        best_structure_calc = sorted(structure_calcs, key=_structure_eval)[0]
        structure = best_structure_calc.output.structure

        # Initial Structures
        initial_structures = [task.input.structure for task in task_group]
        sm = StructureMatcher(
            ltol=0.1, stol=0.1, angle_tol=0.1, scale=False, attempt_supercell=False
        )
        initial_structures = [
            group[0] for group in sm.group_structures(initial_structures)
        ]

        # Deprecated
        deprecated = all(task.task_id in deprecated_tasks for task in structure_calcs)
        deprecated = deprecated or best_structure_calc.task_id in deprecated_tasks

        # Origins
        origins = [
            PropertyOrigin(
                name="structure",
                task_id=best_structure_calc.task_id,
                last_updated=best_structure_calc.last_updated,
            )
        ]

        # Entries
        # **current materials docs must contain at last one GGA or GGA+U entry

        # Always prefer a static over a structure opt
        entry_task_quality_scores = {"Structure Optimization": 1, "Static": 2}

        def _entry_eval(task: TaskDoc):
            """
            Helper function to order entries and statics calcs by
            - Spin polarization
            - Special Tags
            - Energy
            """

            _SPECIAL_TAGS = ["LASPH", "ISPIN"]
            special_tags = sum(
                (
                    task.input.parameters.get(tag, False)
                    if task.input.parameters
                    else False
                )
                for tag in _SPECIAL_TAGS
            )

            return (
                -1 * int(task.is_valid),
                -1 * entry_task_quality_scores.get(task.task_type.value, 0),
                -1 * special_tags,
                task.output.energy_per_atom,
            )

        # Entries
        # **current materials docs must contain at last one GGA or GGA+U entry
        entries = {}
        all_run_types = set(run_types.values())

        for rt in all_run_types:
            relevant_calcs = sorted(
                [doc for doc in structure_calcs if doc.run_type == rt and doc.is_valid],
                key=_entry_eval,
            )

            if len(relevant_calcs) > 0:
                best_task_doc = relevant_calcs[0]
                entry = best_task_doc.structure_entry
                entry.data["task_id"] = entry.entry_id
                entry.data["material_id"] = material_id
                entry.entry_id = "{}-{}".format(material_id, rt.value)
                entry.parameters["is_hubbard"] = best_task_doc.input.is_hubbard
                entry.parameters["hubbards"] = best_task_doc.input.hubbards
                entries[rt] = entry

        if not any(
            run_type in entries
            for run_type in (RunType.GGA, RunType.GGA_U, RunType.r2SCAN)
        ):
            raise ValueError(
                "Individual material entry must contain at least one GGA, GGA+U, or r2SCAN calculation"
            )

        # Builder meta and license
        builder_meta = EmmetMeta(license="BY-C" if commercial_license else "BY-NC")

        return cls.from_structure(
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
            builder_meta=builder_meta,
        )

    @classmethod
    def construct_deprecated_material(
        cls,
        task_group: List[TaskDoc],
        commercial_license: bool = True,
    ) -> "MaterialsDoc":
        """
        Converts a group of tasks into a deprecated material

        Args:
            task_group: List of task document
            commercial_license: Whether the data should be licensed with BY-C (otherwise BY-NC).
        """
        if len(task_group) == 0:
            raise Exception("Must have more than one task in the group.")

        # Metadata
        last_updated = max(task.last_updated for task in task_group)
        created_at = min(task.completed_at for task in task_group)
        task_ids = list({task.task_id for task in task_group})

        deprecated_tasks = {task.task_id for task in task_group}
        run_types = {task.task_id: task.run_type for task in task_group}
        task_types = {task.task_id: task.task_type for task in task_group}
        calc_types = {task.task_id: task.calc_type for task in task_group}

        # Material ID
        material_id = min([task.task_id for task in task_group])

        # Choose any random structure for metadata
        structure = SpacegroupAnalyzer(
            task_group[0].output.structure, symprec=0.1
        ).get_conventional_standard_structure()

        # Deprecated
        deprecated = True

        # Builder meta and license
        builder_meta = EmmetMeta(license="BY-C" if commercial_license else "BY-NC")

        return cls.from_structure(
            structure=structure,
            material_id=material_id,
            last_updated=last_updated,
            created_at=created_at,
            task_ids=task_ids,
            calc_types=calc_types,
            run_types=run_types,
            task_types=task_types,
            deprecated=deprecated,
            deprecated_tasks=deprecated_tasks,
            builder_meta=builder_meta,
        )
