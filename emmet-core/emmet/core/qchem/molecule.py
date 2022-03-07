""" Core definition of a Molecule Document """
from typing import Any, Dict, List, Mapping, Union

from pydantic import Field

from pymatgen.core.structure import Molecule
from pymatgen.analysis.graphs import MoleculeGraph
from pymatgen.analysis.local_env import OpenBabelNN, metal_edge_extender
from pymatgen.analysis.molecule_matcher import MoleculeMatcher

from emmet.core.mpid import MPID
from emmet.core.settings import EmmetSettings
from emmet.core.material import MoleculeDoc as CoreMoleculeDoc
from emmet.core.material import PropertyOrigin
from emmet.core.structure import MoleculeMetadata
from emmet.core.qchem.calc_types import CalcType, LevelOfTheory, TaskType
from emmet.core.qchem.task import TaskDocument


__author__ = "Evan Spotte-Smith <ewcspottesmith@lbl.gov>"


SETTINGS = EmmetSettings()


def evaluate_lot(
    lot: Union[LevelOfTheory, str],
    funct_scores: Dict[str, int] = SETTINGS.QCHEM_FUNCTIONAL_QUALITY_SCORES,
    basis_scores: Dict[str, int] = SETTINGS.QCHEM_BASIS_QUALITY_SCORES,
    solvent_scores: Dict[str, int] = SETTINGS.QCHEM_SOLVENT_MODEL_QUALITY_SCORES,
):
    """
    Score the various components of a level of theory (functional, basis set,
    and solvent model), where a lower score is better than a higher score.

    :param lot: Level of theory to be evaluated
    :param funct_scores: Scores for various density functionals
    :param basis_scores: Scores for various basis sets
    :param solvent_scores: Scores for various implicit solvent models
    :return:
    """

    if isinstance(lot, LevelOfTheory):
        lot_comp = lot.value.split("/")
    else:
        lot_comp = lot.split("/")

    return (
        -1 * funct_scores.get(lot_comp[0], 0),
        -1 * basis_scores.get(lot_comp[1], 0),
        -1 * solvent_scores.get(lot_comp[2].split("(")[0], 0),
    )


def evaluate_task(
    task: TaskDocument,
    funct_scores: Dict[str, int] = SETTINGS.QCHEM_FUNCTIONAL_QUALITY_SCORES,
    basis_scores: Dict[str, int] = SETTINGS.QCHEM_BASIS_QUALITY_SCORES,
    solvent_scores: Dict[str, int] = SETTINGS.QCHEM_SOLVENT_MODEL_QUALITY_SCORES,
    task_quality_scores: Dict[str, int] = SETTINGS.QCHEM_TASK_QUALITY_SCORES,
):
    """
    Helper function to order optimization calcs by
    - Level of theory
    - Electronic energy

    Note that lower scores indicate a higher quality.

    :param task: Task to be evaluated
    :param funct_scores: Scores for various density functionals
    :param basis_scores: Scores for various basis sets
    :param solvent_scores: Scores for various implicit solvent models
    :param task_quality_scores: Scores for various task types
    :return:
    """

    lot = task.level_of_theory

    lot_eval = evaluate_lot(
        lot,
        funct_scores=funct_scores,
        basis_scores=basis_scores,
        solvent_scores=solvent_scores,
    )

    return (
        -1 * int(task.is_valid),
        sum(lot_eval),
        -1 * task_quality_scores.get(task.task_type.value, 0),
        task.output.final_energy,
    )


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
        None,
        description="List of property origins for tracking the provenance of properties",
    )

    entries: List[Dict[str, Any]] = Field(
        None,
        description="Dictionary representations of all task documents for this molecule",
    )

    best_entries: Mapping[LevelOfTheory, Dict[str, Any]] = Field(
        None,
        description="Mapping for tracking the best entries at each level of theory for Q-Chem calculations",
    )

    similar_molecules: List[MPID] = Field(
        None,
        description="List of MPIDs with of molecules similar (by e.g. structure) to this one",
    )

    @classmethod
    def from_tasks(
        cls,
        task_group: List[TaskDocument],
    ) -> "MoleculeDoc":

        """
        Converts a group of tasks into one molecule document

        Args:
            task_group: List of task document
        """
        if len(task_group) == 0:
            raise Exception("Must have more than one task in the group.")

        entries = [t.entry for t in task_group]

        # Metadata
        last_updated = max(task.last_updated for task in task_group)
        created_at = min(task.last_updated for task in task_group)
        task_ids = list({task.task_id for task in task_group})

        deprecated_tasks = {task.task_id for task in task_group if not task.is_valid}
        levels_of_theory = {task.task_id: task.level_of_theory for task in task_group}
        task_types = {task.task_id: task.task_type for task in task_group}
        calc_types = {task.task_id: task.calc_type for task in task_group}

        mols = [task.output.initial_molecule for task in task_group]

        # If we're dealing with single-atoms, process is much different
        if all([len(m) == 1 for m in mols]):
            sorted_tasks = sorted(task_group, key=evaluate_task)

            molecule_id = sorted_tasks[0].task_id

            molecule = sorted_tasks[0].output.initial_molecule

            # Initial molecules. No geometry should change for a single atom
            initial_molecules = [molecule]

            # Deprecated
            deprecated = all(task.task_id in deprecated_tasks for task in task_group)

            # Origins
            origins = [
                PropertyOrigin(
                    name="molecule",
                    task_id=molecule_id,
                    last_updated=sorted_tasks[0].last_updated,
                )
            ]

            # entries
            best_entries = {}
            all_lots = set(levels_of_theory.values())
            for lot in all_lots:
                relevant_calcs = sorted(
                    [
                        doc
                        for doc in task_group
                        if doc.level_of_theory == lot and doc.is_valid
                    ],
                    key=evaluate_task,
                )

                if len(relevant_calcs) > 0:
                    best_task_doc = relevant_calcs[0]
                    entry = best_task_doc.entry
                    entry["task_id"] = entry["entry_id"]
                    entry["entry_id"] = molecule_id
                    best_entries[lot] = entry

        else:
            geometry_optimizations = [
                task for task in task_group if task.task_type in [TaskType.Geometry_Optimization, TaskType.Frequency_Flattening_Geometry_Optimization]  # type: ignore
            ]

            # Molecule ID
            possible_mol_ids = [task.task_id for task in geometry_optimizations]

            molecule_id = min(possible_mol_ids)

            best_molecule_calc = sorted(geometry_optimizations, key=evaluate_task)[0]
            molecule = best_molecule_calc.output.optimized_molecule

            # Initial molecules
            initial_molecules = list()
            for task in task_group:
                if isinstance(task.orig["molecule"], Molecule):
                    initial_molecules.append(task.orig["molecule"])
                else:
                    initial_molecules.append(Molecule.from_dict(task.orig["molecule"]))

            mm = MoleculeMatcher()
            initial_molecules = [
                group[0] for group in mm.group_molecules(initial_molecules)
            ]

            # Deprecated
            deprecated = all(
                task.task_id in deprecated_tasks for task in geometry_optimizations
            )
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
            best_entries = {}
            all_lots = set(levels_of_theory.values())
            for lot in all_lots:
                relevant_calcs = sorted(
                    [
                        doc
                        for doc in geometry_optimizations
                        if doc.level_of_theory == lot and doc.is_valid
                    ],
                    key=evaluate_task,
                )

                if len(relevant_calcs) > 0:
                    best_task_doc = relevant_calcs[0]
                    entry = best_task_doc.entry
                    best_entries[lot] = entry

        for entry in entries:
            entry["entry_id"] = molecule_id

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
            entries=entries,
            best_entries=best_entries,
        )

    @classmethod
    def construct_deprecated_molecule(
        cls,
        task_group: List[TaskDocument],
    ) -> "MoleculeDoc":
        """
        Converts a group of tasks into a deprecated molecule document

        Args:
            task_group: List of task document
        """
        if len(task_group) == 0:
            raise Exception("Must have more than one task in the group.")

        # Metadata
        last_updated = max(task.last_updated for task in task_group)
        created_at = min(task.last_updated for task in task_group)
        task_ids = list({task.task_id for task in task_group})

        deprecated_tasks = {task.task_id for task in task_group}
        levels_of_theory = {task.task_id: task.level_of_theory for task in task_group}
        task_types = {task.task_id: task.task_type for task in task_group}
        calc_types = {task.task_id: task.calc_type for task in task_group}

        # Molecule ID
        molecule_id = min([task.task_id for task in task_group])

        # Choose any random structure for metadata
        molecule = task_group[0].output.initial_molecule

        # Deprecated
        deprecated = True

        return cls.from_molecule(
            molecule=molecule,
            molecule_id=molecule_id,
            last_updated=last_updated,
            created_at=created_at,
            task_ids=task_ids,
            calc_types=calc_types,
            levels_of_theory=levels_of_theory,
            task_types=task_types,
            deprecated=deprecated,
            deprecated_tasks=deprecated_tasks,
        )


def best_lot(
    mol_doc: MoleculeDoc,
    funct_scores: Dict[str, int] = SETTINGS.QCHEM_FUNCTIONAL_QUALITY_SCORES,
    basis_scores: Dict[str, int] = SETTINGS.QCHEM_BASIS_QUALITY_SCORES,
    solvent_scores: Dict[str, int] = SETTINGS.QCHEM_SOLVENT_MODEL_QUALITY_SCORES,
) -> LevelOfTheory:
    """

    Return the best level of theory used within a MoleculeDoc

    :param mol_doc: MoleculeDoc
    :param funct_scores: Scores for various density functionals
    :param basis_scores: Scores for various basis sets
    :param solvent_scores: Scores for various implicit solvent models

    :return: LevelOfTheory
    """

    sorted_lots = sorted(
        mol_doc.best_entries.keys(),
        key=lambda x: evaluate_lot(x, funct_scores, basis_scores, solvent_scores),
    )

    return sorted_lots[0]
