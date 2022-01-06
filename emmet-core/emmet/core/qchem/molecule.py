""" Core definition of a Molecule Document """
from typing import Any, Dict, List, Mapping

from pydantic import Field

from pymatgen.core.structure import Molecule
from pymatgen.analysis.graphs import MoleculeGraph
from pymatgen.analysis.local_env import OpenBabelNN, metal_edge_extender
from pymatgen.analysis.molecule_matcher import MoleculeMatcher

from emmet.core import SETTINGS
from emmet.core.material import MoleculeDoc as CoreMoleculeDoc
from emmet.core.material import PropertyOrigin
from emmet.core.structure import MoleculeMetadata
from emmet.core.qchem.calc_types import CalcType, LevelOfTheory, TaskType
from emmet.core.qchem.task import TaskDocument


class MoleculeDoc(CoreMoleculeDoc, MoleculeMetadata):

    calc_types: Mapping[str, CalcType] = Field(  # type: ignore
        None,
        description="Calculation types for all the calculations that make up this molecule",
    )
    task_types: Mapping[str, TaskType] = Field(
        None,
        description="Task types for all the calculations that make up this molecule",
    )
    levels_of_theory: Mapping[str, LevelOfTheory] = Field(
        None,
        description="Levels of theory types for all the calculations that make up this material",
    )

    origins: List[PropertyOrigin] = Field(
        None, description="List of property origins for tracking the provenance of properties"
    )

    entries: Mapping[LevelOfTheory, Dict[str, Any]] = Field(
        None, description="Mapping for tracking entries for Q-Chem calculations"
    )

    @classmethod
    def from_tasks(
            cls,
            task_group: List[TaskDocument],
            funct_scores: Dict[str, int] = SETTINGS.QCHEM_FUNCTIONAL_QUALITY_SCORES,
            basis_scores: Dict[str, int] = SETTINGS.QCHEM_BASIS_QUALITY_SCORES,
            solvent_scores: Dict[str, int] = SETTINGS.QCHEM_SOLVENT_MODEL_QUALITY_SCORES,
    ) -> "MoleculeDoc":

        """
        Converts a group of tasks into one molecule document

        Args:
            task_group: List of task document
            quality_scores: quality scores for various density functionals
        """
        if len(task_group) == 0:
            raise Exception("Must have more than one task in the group.")

        # Metadata
        last_updated = max(task.last_updated for task in task_group)
        created_at = min(task.completed_at for task in task_group)
        task_ids = list({task.task_id for task in task_group})

        deprecated_tasks = {task.task_id for task in task_group if not task.is_valid}
        levels_of_theory = {task.task_id: task.level_of_theory for task in task_group}
        task_types = {task.task_id: task.task_type for task in task_group}
        calc_types = {task.task_id: task.calc_type for task in task_group}

        geometry_optimizations = [
            task for task in task_group if task.task_type in [TaskType.geometry_optimization, TaskType.frequency_flattening_geometry_optimization] # type: ignore
        ]

        # Material ID
        possible_mol_ids = [task.task_id for task in geometry_optimizations]

        molecule_id = min(possible_mol_ids)

        # Always prefer a static over a structure opt
        task_quality_scores = {"geometry optimization": 1, "frequency-flattening geometry optimization": 2}

        def _evaluate_molecule(task: TaskDocument):
            """
            Helper function to order optimization calcs by
            - Level of theory
            - Spin polarization
            - Special Tags
            - Energy
            """

            lot_comp = task.level_of_theory.value.split("/")


            return (
                -1 * int(task.is_valid),
                -1 * funct_scores.get(lot_comp[0], 0),
                -1 * basis_scores.get(lot_comp[1], 0),
                -1 * solvent_scores.get(lot_comp[2].split("(")[0], 0),
                -1 * task_quality_scores.get(task.task_type.value, 0),
                task.output.final_energy,
            )

        best_molecule_calc = sorted(geometry_optimizations, key=_evaluate_molecule)[0]
        molecule = best_molecule_calc.output.molecule

        # Initial Structures
        initial_molecules = [task.orig["molecule"] for task in task_group]
        mm = MoleculeMatcher()
        initial_molecules = [
            group[0] for group in mm.group_structures(initial_molecules)
        ]

        # Deprecated
        deprecated = all(task.task_id in deprecated_tasks for task in geometry_optimizations)
        deprecated = deprecated or best_molecule_calc.task_id in deprecated_tasks

        # Origins
        origins = [
            PropertyOrigin(
                name="molecule",
                task_id=best_molecule_calc.task_id,
                last_updated=best_molecule_calc.last_updated,
            )
        ]

        # entries
        entries = {}
        all_lots = set(levels_of_theory.values())
        for lot in all_lots:
            relevant_calcs = sorted(
                [doc for doc in geometry_optimizations if doc.level_of_theory == lot and doc.is_valid],
                key=_evaluate_molecule,
            )

            if len(relevant_calcs) > 0:
                best_task_doc = relevant_calcs[0]
                entry = best_task_doc.entry
                entry["task_id"] = entry["entry_id"]
                entry["entry_id"] = molecule_id
                entries[lot] = entry

        return cls.from_molecule(
            molecule=molecule,
            molecule_id=molecule_id,
            initial_molecules=initial_molecules,
            last_updated=last_updated,
            created_at=created_at,
            task_ids=task_ids,
            calc_types=calc_types,
            levels_of_theory=levels_of_theory,
            task_types=task_types,
            deprecated=deprecated,
            deprecated_tasks=deprecated_tasks,
            origins=origins,
            entries=entries
        )
