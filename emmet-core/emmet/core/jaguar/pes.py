""" Core definition of document describing points on a Potential Energy Surface """
from typing import Any, Dict, List, Mapping, Union

from pydantic import Field

from pymatgen.core.structure import Molecule
from pymatgen.analysis.molecule_matcher import MoleculeMatcher

from emmet.core.mpid import MPID
from emmet.core.settings import EmmetSettings
from emmet.core.material import MoleculeDoc as CoreMoleculeDoc
from emmet.core.material import PropertyOrigin
from emmet.core.structure import MoleculeMetadata
from emmet.core.jaguar.calc_types import CalcType, LevelOfTheory, TaskType
from emmet.core.jaguar.task import TaskDocument


__author__ = "Evan Spotte-Smith <ewcspottesmith@lbl.gov>"


SETTINGS = EmmetSettings()


def evaluate_lot(
    lot: Union[LevelOfTheory, str],
    funct_scores: Dict[str, int] = SETTINGS.JAGUAR_FUNCTIONAL_QUALITY_SCORES,
    basis_scores: Dict[str, int] = SETTINGS.JAGUAR_BASIS_QUALITY_SCORES,
    solvent_scores: Dict[str, int] = SETTINGS.JAGUAR_SOLVENT_MODEL_QUALITY_SCORES,
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
    funct_scores: Dict[str, int] = SETTINGS.JAGUAR_FUNCTIONAL_QUALITY_SCORES,
    basis_scores: Dict[str, int] = SETTINGS.JAGUAR_BASIS_QUALITY_SCORES,
    solvent_scores: Dict[str, int] = SETTINGS.JAGUAR_SOLVENT_MODEL_QUALITY_SCORES,
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
        task.output.energy,
    )


class PESPointDoc(CoreMoleculeDoc, MoleculeMetadata):

    calc_types: Mapping[str, CalcType] = Field(  # type: ignore
        None,
        description="Calculation types for all the calculations that make up this point on a PES",
    )
    task_types: Mapping[str, TaskType] = Field(
        None,
        description="Task types for all the calculations that make up this point on a PES",
    )
    levels_of_theory: Mapping[str, LevelOfTheory] = Field(
        None,
        description="Levels of theory types for all the calculations that make up this point on a PES",
    )

    origins: List[PropertyOrigin] = Field(
        None,
        description="List of property origins for tracking the provenance of properties",
    )

    entries: List[Dict[str, Any]] = Field(
        None,
        description="Dictionary representations of all task documents for this point on a PES",
    )

    best_entries: Mapping[LevelOfTheory, Dict[str, Any]] = Field(
        None,
        description="Mapping for tracking the best entries at each level of theory for Jaguar calculations",
    )

    similar_points: List[MPID] = Field(
        None,
        description="List of IDs with of points on a PES that are similar (by e.g. structure, type [TS, minimum, etc.]) to this one",
    )

    @classmethod
    def from_tasks(
        cls,
        task_group: List[TaskDocument],
    ) -> "PESPointDoc":

        """
        Converts a group of tasks into one document describing a point on a
        Potential Energy Surface (PES)

        Args:
            task_group: List of task document
        """
        if len(task_group) == 0:
            raise Exception("Must have more than one task in the group.")

        entries = [t.entry for t in task_group]

        # Metadata
        last_updated = max(task.last_updated for task in task_group)
        calc_ids = list({task.calcid for task in task_group})

        deprecated_tasks = {task.calcid for task in task_group if not task.is_valid}
        levels_of_theory = {task.calcid: task.level_of_theory for task in task_group}
        task_types = {task.calcid: task.task_type for task in task_group}
        calc_types = {task.calcid: task.calc_type for task in task_group}

        initial_structures = list()
        for task in task_group:
            if isinstance(task.input["molecule"], Molecule):
                initial_structures.append(task.input["molecule"])
            else:
                initial_structures.append(Molecule.from_dict(task.input["molecule"]))

        # If we're dealing with single-atoms, process is much different
        if all([len(m) == 1 for m in initial_structures]):
            sorted_tasks = sorted(task_group, key=evaluate_task)

            point_id = sorted_tasks[0].calcid

            molecule = sorted_tasks[0].output.molecule

            # Output molecules. No geometry should change for a single atom
            initial_molecules = [molecule]

            # Deprecated
            deprecated = all(task.calcid in deprecated_tasks for task in task_group)

            # Origins
            origins = [
                PropertyOrigin(
                    name="molecule",
                    task_id=point_id,
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
                    entry["calcid"] = entry["entry_id"]
                    entry["entry_id"] = point_id
                    best_entries[lot] = entry

        else:
            geometry_optimizations = [
                task
                for task in task_group
                if task.task_type
                in [
                    TaskType.Geometry_Optimization,
                    TaskType.Transition_State_Geometry_Optimization,
                ]  # type: ignore
            ]

            # Molecule ID
            possible_mol_ids = [task.calcid for task in geometry_optimizations]

            point_id = min(possible_mol_ids)

            best_structure_calc = sorted(geometry_optimizations, key=evaluate_task)[0]
            molecule = best_structure_calc.output.molecule

            mm = MoleculeMatcher()
            initial_molecules = [
                group[0] for group in mm.group_molecules(initial_structures)
            ]

            # Deprecated
            deprecated = all(
                task.calcid in deprecated_tasks for task in geometry_optimizations
            )
            deprecated = deprecated or best_structure_calc.calcid in deprecated_tasks

            # Origins
            origins = [
                PropertyOrigin(
                    name="molecule",
                    task_id=best_structure_calc.calcid,
                    last_updated=best_structure_calc.last_updated,
                )
            ]

            # entries
            best_entries = dict()
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
            entry["entry_id"] = point_id

        return cls.from_molecule(
            molecule=molecule,
            molecule_id=point_id,
            initial_molecules=initial_molecules,
            last_updated=last_updated,
            task_ids=calc_ids,
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
    ) -> "PESPointDoc":
        """
        Converts a group of tasks into a deprecated PESPointDoc

        Args:
            task_group: List of task document
        """
        if len(task_group) == 0:
            raise Exception("Must have more than one task in the group.")

        # Metadata
        last_updated = max(task.last_updated for task in task_group)
        created_at = min(task.last_updated for task in task_group)
        calc_ids = list({task.calcid for task in task_group})

        deprecated_tasks = {task.calcid for task in task_group}
        levels_of_theory = {task.calcid: task.level_of_theory for task in task_group}
        task_types = {task.calcid: task.task_type for task in task_group}
        calc_types = {task.calcid: task.calc_type for task in task_group}

        # Molecule ID
        point_id = min([task.calcid for task in task_group])

        # Choose any random structure for metadata
        if isinstance(task_group[0].input["molecule"], Molecule):
            molecule = task_group[0].input["molecule"]
        else:
            molecule = Molecule.from_dict(task_group[0].input["molecule"])

        # Deprecated
        deprecated = True

        return cls.from_molecule(
            molecule=molecule,
            molecule_id=point_id,
            last_updated=last_updated,
            created_at=created_at,
            task_ids=calc_ids,
            calc_types=calc_types,
            levels_of_theory=levels_of_theory,
            task_types=task_types,
            deprecated=deprecated,
            deprecated_tasks=deprecated_tasks,
        )


class PESMinimumDoc(PESPointDoc):
    pass


class TransitionStateDoc(PESPointDoc):
    pass


def best_lot(
    doc: PESPointDoc,
    funct_scores: Dict[str, int] = SETTINGS.JAGUAR_FUNCTIONAL_QUALITY_SCORES,
    basis_scores: Dict[str, int] = SETTINGS.JAGUAR_BASIS_QUALITY_SCORES,
    solvent_scores: Dict[str, int] = SETTINGS.JAGUAR_SOLVENT_MODEL_QUALITY_SCORES,
) -> LevelOfTheory:
    """

    Return the best level of theory used within a MoleculeDoc

    :param doc: PESPointDoc
    :param funct_scores: Scores for various density functionals
    :param basis_scores: Scores for various basis sets
    :param solvent_scores: Scores for various implicit solvent models

    :return: LevelOfTheory
    """

    sorted_lots = sorted(
        doc.best_entries.keys(),
        key=lambda x: evaluate_lot(x, funct_scores, basis_scores, solvent_scores),
    )

    return sorted_lots[0]
