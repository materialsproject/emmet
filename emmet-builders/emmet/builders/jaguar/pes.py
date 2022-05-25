from datetime import datetime
from itertools import chain
from math import ceil
from typing import Dict, Iterable, Iterator, List, Optional


from maggma.builders import Builder
from maggma.stores import Store
from maggma.utils import grouper

from emmet.builders.settings import EmmetBuildSettings
from emmet.core.utils import group_molecules, jsanitize
from emmet.core.jaguar.pes import (
    best_lot,
    evaluate_lot,
    PESPointDoc,
    PESMinimumDoc,
    TransitionStateDoc)
from emmet.core.jaguar.task import TaskDocument


__author__ = "Evan Spotte-Smith <ewcspottesmith@lbl.gov>"


SETTINGS = EmmetBuildSettings()


def evaluate_point(
    pes_point: PESPointDoc,
    funct_scores: Dict[str, int] = SETTINGS.JAGUAR_FUNCTIONAL_QUALITY_SCORES,
    basis_scores: Dict[str, int] = SETTINGS.JAGUAR_BASIS_QUALITY_SCORES,
    solvent_scores: Dict[str, int] = SETTINGS.JAGUAR_SOLVENT_MODEL_QUALITY_SCORES,
):
    """
    Helper function to order optimization calcs by
    - Level of theory
    - Electronic energy

    :param mol_doc: Molecule to be evaluated
    :param funct_scores: Scores for various density functionals
    :param basis_scores: Scores for various basis sets
    :param solvent_scores: Scores for various implicit solvent models
    :return:
    """

    best = best_lot(pes_point, funct_scores, basis_scores, solvent_scores)

    lot_eval = evaluate_lot(best, funct_scores, basis_scores, solvent_scores)

    return (
        -1 * int(pes_point.deprecated),
        sum(lot_eval),
        pes_point.best_entries[best]["energy"],
    )


def filter_and_group_tasks(
    self, tasks: List[TaskDocument]
) -> Iterator[List[TaskDocument]]:
    """
    Groups tasks by identical structure
    """

    filtered_tasks = [
        task
        for task in tasks
        if any(
            allowed_type is task.task_type
            for allowed_type in self.settings.JAGUAR_ALLOWED_TASK_TYPES
        )
    ]

    molecules = list()
    lots = list()

    for idx, task in enumerate(filtered_tasks):
        if task.output.optimized_molecule:
            m = task.output.optimized_molecule
        else:
            m = task.output.initial_molecule
        m.index: int = idx  # type: ignore
        molecules.append(m)
        lots.append(task.level_of_theory.value)

    grouped_molecules = group_molecules(molecules, lots)
    for group in grouped_molecules:
        grouped_tasks = [filtered_tasks[mol.index] for mol in group]  # type: ignore
        yield grouped_tasks


class PESMinimumBuilder(Builder):
    """
    The PESMinimumBuilder matches Jaguar task documents that represent minima of
    a potential energy surface (no imaginary frequencies, or one negligible
    imaginary frequency) by composition and collects tasks associated with
    identical structures.

    The process is as follows:

        1.) Find all documents with the same formula
        2.) Select only task documents for the task_types we can select
        properties from
        3.) Aggregate task documents based on nuclear geometry
        4.) Create PESMinimumDocs, filtering based on the characteristic
        frequencies calculated in the tasks
    """

    def __init__(
        self,
        tasks: Store,
        minima: Store,
        query: Optional[Dict] = None,
        settings: Optional[EmmetBuildSettings] = None,
        negative_threshold: float = -75.0,
        **kwargs,
    ):
        """
        Args:
            tasks:  Store of task documents
            minima: Store of PESMinimumDocs to prepare
            query: dictionary to limit tasks to be analyzed
            settings: EmmetSettings to use in the build process
            negative_threshold: Threshold for imaginary frequencies. Points
                with one imaginary frequency >= this value will be considered
                as valid.
        """

        self.tasks = tasks
        self.minima = minima
        self.query = query if query else dict()
        self.settings = EmmetBuildSettings.autoload(settings)
        self.negative_threshold = negative_threshold
        self.kwargs = kwargs

        super().__init__(sources=[tasks], targets=[minima])

    def ensure_indexes(self):
        """
        Ensures indices on the collections needed for building
        """

        # Basic search index for tasks
        self.tasks.ensure_index("calcid")
        self.tasks.ensure_index("last_updated")
        self.tasks.ensure_index("success")
        self.tasks.ensure_index("formula_alphabetical")

        # Search index for minima
        self.minima.ensure_index("molecule_id")
        self.minima.ensure_index("last_updated")
        self.minima.ensure_index("task_ids")
        self.minima.ensure_index("formula_alphabetical")

    def prechunk(self, number_splits: int) -> Iterable[Dict]:  # pragma: no cover
        """Prechunk the PESMinimumBuilder for distributed computation"""

        temp_query = dict(self.query)
        temp_query["success"] = True

        self.logger.info("Finding tasks to process")
        all_tasks = list(
            self.tasks.query(temp_query, [self.tasks.key, "formula_alphabetical"])
        )

        processed_tasks = set(self.minima.distinct("task_ids"))
        to_process_tasks = {d[self.tasks.key] for d in all_tasks} - processed_tasks
        to_process_forms = {
            d["formula_alphabetical"]
            for d in all_tasks
            if d[self.tasks.key] in to_process_tasks
        }

        N = ceil(len(to_process_forms) / number_splits)

        for formula_chunk in grouper(to_process_forms, N):
            yield {"query": {"formula_alphabetical": {"$in": list(formula_chunk)}}}

    def get_items(self) -> Iterator[List[Dict]]:
        """
        Gets all items to process into PESMinimumDocs.
        This does no datetime checking; relying on on whether
        task_ids are included in the minima Store

        Returns:
            generator or list relevant tasks and molecules to process into documents
        """

        self.logger.info("PES Minimum builder started")
        self.logger.info(
            f"Allowed task types: {[task_type.value for task_type in self.settings.JAGUAR_ALLOWED_TASK_TYPES]}"
        )

        self.logger.info("Setting indexes")
        self.ensure_indexes()

        # Save timestamp to mark buildtime
        self.timestamp = datetime.utcnow()

        # Get all processed tasks
        temp_query = dict(self.query)
        temp_query["success"] = True

        self.logger.info("Finding tasks to process")
        all_tasks = list(
            self.tasks.query(temp_query, [self.tasks.key, "formula_alphabetical"])
        )

        processed_tasks = set(self.minima.distinct("task_ids"))
        to_process_tasks = {d[self.tasks.key] for d in all_tasks} - processed_tasks
        to_process_forms = {
            d["formula_alphabetical"]
            for d in all_tasks
            if d[self.tasks.key] in to_process_tasks
        }

        self.logger.info(f"Found {len(to_process_tasks)} unprocessed tasks")
        self.logger.info(f"Found {len(to_process_forms)} unprocessed formulas")

        # Set total for builder bars to have a total
        self.total = len(to_process_forms)

        projected_fields = [
            "calcid",
            "tags",
            "additional_data",
            "charge",
            "spin_multiplicity",
            "nelectrons",
            "errors",
            "success",
            "walltime",
            "input",
            "output",
            "last_updated",
            "job_type",
            "formula_alphabetical"
        ]

        for formula in to_process_forms:
            tasks_query = dict(temp_query)
            tasks_query["formula_alphabetical"] = formula
            tasks = list(
                self.tasks.query(criteria=tasks_query, properties=projected_fields)
            )
            for t in tasks:
                # TODO: Validation
                # basic validation here ensures that tasks that do not have the requisite
                # information to form TaskDocuments do not snag building
                try:
                    TaskDocument(**t)
                    t["is_valid"] = True
                except Exception as e:
                    self.logger.info(
                        f"Processing task {t['calcid']} failed with Exception - {e}"
                    )
                    t["is_valid"] = False

            yield tasks

    def process_item(self, items: List[Dict]) -> List[Dict]:
        """
        Process the tasks into a PESMinimumDoc

        Args:
            tasks [dict] : a list of task docs

        Returns:
            [dict] : a list of new PESMinimumDocs
        """

        tasks = [TaskDocument(**task) for task in items if task["is_valid"]]
        formula = tasks[0].formula_alphabetical
        task_ids = [task.calcid for task in tasks]
        self.logger.debug(f"Processing {formula} : {task_ids}")
        minima = list()

        for group in filter_and_group_tasks(tasks):
            try:
                minima.append(PESMinimumDoc.from_tasks(group))
            except Exception as e:
                failed_ids = list({t_.calcid for t_ in group})
                doc = PESPointDoc.construct_deprecated_molecule(tasks)
                doc.warnings.append(str(e))
                minima.append(doc)
                self.logger.warn(
                    f"Failed making PESMinimum for {failed_ids}."
                    f" Inserted as deprecated molecule: {doc.molecule_id}"
                )

        self.logger.debug(f"Produced {len(minima)} molecules for {formula}")

        return jsanitize([doc.dict() for doc in minima], allow_bson=True)

    def update_targets(self, items: List[Dict]):
        """
        Inserts the new minima into the minima collection

        Args:
            items [[dict]]: A list of PESMinimumDocs to update
        """

        docs = list(chain.from_iterable(items))  # type: ignore

        true_minima = list()

        for item in docs:
            item.update({"_bt": self.timestamp})
            frequencies = item.get("frequencies")
            # Assume a species with no frequencies is a valid minimum
            if frequencies is None or len(frequencies) < 2:
                true_minima.append(item)
            # All positive, or one small negative frequency
            elif frequencies[0] >= self.negative_threshold and frequencies[1] > 0:
                true_minima.append(item)
            else:
                continue

        molecule_ids = list({item["molecule_id"] for item in true_minima})

        if len(items) > 0:
            self.logger.info(f"Updating {len(docs)} molecules")
            self.minima.remove_docs({self.minima.key: {"$in": molecule_ids}})
            self.minima.update(
                docs=true_minima,
                key=["molecule_id"],
            )
        else:
            self.logger.info("No items to update")


class TransitionStateBuilder(Builder):
    """
    The TransitionStateBuilder matches Jaguar task documents that represent
    transition-states (points on a potential energy surface with one imaginary frequency,
    or with two imaginary frequencies where the second is very small) by
    composition and collects tasks associated with identical structures.

    The process is as follows:

        1.) Find all documents with the same formula
        2.) Select only task documents for the task_types we can select
        properties from
        3.) Aggregate task documents based on nuclear geometry
        4.) Create TransitionStateDocs, filtering based on the
        characteristic frequencies calculated in the tasks
    """

    def __init__(
        self,
        tasks: Store,
        transition_states: Store,
        query: Optional[Dict] = None,
        settings: Optional[EmmetBuildSettings] = None,
        negative_threshold: float = -75.0,
        **kwargs,
    ):
        """
        Args:
            tasks:  Store of task documents
            transition_states: Store of TransitionStateDocs to prepare
            query: dictionary to limit tasks to be analyzed
            settings: EmmetSettings to use in the build process
            negative_threshold: Threshold for imaginary frequencies. Points
                with a second imaginary frequency >= this value will be
                considered as valid.
        """

        self.tasks = tasks
        self.transition_states = transition_states
        self.query = query if query else dict()
        self.settings = EmmetBuildSettings.autoload(settings)
        self.negative_threshold = negative_threshold
        self.kwargs = kwargs

        super().__init__(sources=[tasks], targets=[transition_states])

    def ensure_indexes(self):
        """
        Ensures indices on the collections needed for building
        """

        # Basic search index for tasks
        self.tasks.ensure_index("calcid")
        self.tasks.ensure_index("last_updated")
        self.tasks.ensure_index("success")
        self.tasks.ensure_index("formula_alphabetical")

        # Search index for transition-states
        self.transition_states.ensure_index("molecule_id")
        self.transition_states.ensure_index("last_updated")
        self.transition_states.ensure_index("task_ids")
        self.transition_states.ensure_index("formula_alphabetical")

    def prechunk(self, number_splits: int) -> Iterable[Dict]:  # pragma: no cover
        """Prechunk the TransitionStateBuilder for distributed computation"""

        temp_query = dict(self.query)
        temp_query["success"] = True

        self.logger.info("Finding tasks to process")
        all_tasks = list(
            self.tasks.query(temp_query, [self.tasks.key, "formula_alphabetical"])
        )

        processed_tasks = set(self.transition_states.distinct("task_ids"))
        to_process_tasks = {d[self.tasks.key] for d in all_tasks} - processed_tasks
        to_process_forms = {
            d["formula_alphabetical"]
            for d in all_tasks
            if d[self.tasks.key] in to_process_tasks
        }

        N = ceil(len(to_process_forms) / number_splits)

        for formula_chunk in grouper(to_process_forms, N):
            yield {"query": {"formula_alphabetical": {"$in": list(formula_chunk)}}}

    def get_items(self) -> Iterator[List[Dict]]:
        """
        Gets all items to process into TransitionStateDocs.
        This does no datetime checking; relying on on whether
        task_ids are included in the transition_states Store

        Returns:
            generator or list relevant tasks and molecules to process into documents
        """

        self.logger.info("Transition-State builder started")
        self.logger.info(
            f"Allowed task types: {[task_type.value for task_type in self.settings.JAGUAR_ALLOWED_TASK_TYPES]}"
        )

        self.logger.info("Setting indexes")
        self.ensure_indexes()

        # Save timestamp to mark buildtime
        self.timestamp = datetime.utcnow()

        # Get all processed tasks
        temp_query = dict(self.query)
        temp_query["success"] = True

        self.logger.info("Finding tasks to process")
        all_tasks = list(
            self.tasks.query(temp_query, [self.tasks.key, "formula_alphabetical"])
        )

        processed_tasks = set(self.transition_states.distinct("task_ids"))
        to_process_tasks = {d[self.tasks.key] for d in all_tasks} - processed_tasks
        to_process_forms = {
            d["formula_alphabetical"]
            for d in all_tasks
            if d[self.tasks.key] in to_process_tasks
        }

        self.logger.info(f"Found {len(to_process_tasks)} unprocessed tasks")
        self.logger.info(f"Found {len(to_process_forms)} unprocessed formulas")

        # Set total for builder bars to have a total
        self.total = len(to_process_forms)

        projected_fields = [
            "calcid",
            "tags",
            "additional_data",
            "charge",
            "spin_multiplicity",
            "nelectrons",
            "errors",
            "success",
            "walltime",
            "input",
            "output",
            "last_updated",
            "job_type",
            "formula_alphabetical"
        ]

        for formula in to_process_forms:
            tasks_query = dict(temp_query)
            tasks_query["formula_alphabetical"] = formula
            tasks = list(
                self.tasks.query(criteria=tasks_query, properties=projected_fields)
            )
            for t in tasks:
                # TODO: Validation
                # basic validation here ensures that tasks that do not have the requisite
                # information to form TaskDocuments do not snag building
                try:
                    TaskDocument(**t)
                    t["is_valid"] = True
                except Exception as e:
                    self.logger.info(
                        f"Processing task {t['calcid']} failed with Exception - {e}"
                    )
                    t["is_valid"] = False

            yield tasks

    def process_item(self, items: List[Dict]) -> List[Dict]:
        """
        Process the tasks into a TransitionStateDoc

        Args:
            tasks [dict] : a list of task docs

        Returns:
            [dict] : a list of new TransitionStateDocs
        """

        tasks = [TaskDocument(**task) for task in items if task["is_valid"]]
        formula = tasks[0].formula_alphabetical
        task_ids = [task.calcid for task in tasks]
        self.logger.debug(f"Processing {formula} : {task_ids}")
        transition_states = list()

        for group in filter_and_group_tasks(tasks):
            try:
                transition_states.append(TransitionStateDoc.from_tasks(group))
            except Exception as e:
                failed_ids = list({t_.calcid for t_ in group})
                doc = PESPointDoc.construct_deprecated_molecule(tasks)
                doc.warnings.append(str(e))
                transition_states.append(doc)
                self.logger.warn(
                    f"Failed making TransitionState for {failed_ids}."
                    f" Inserted as deprecated molecule: {doc.molecule_id}"
                )

        self.logger.debug(f"Produced {len(transition_states)} molecules for {formula}")

        return jsanitize([doc.dict() for doc in transition_states], allow_bson=True)

    def update_targets(self, items: List[Dict]):
        """
        Inserts the new minima into the minima collection

        Args:
            items [[dict]]: A list of PESMinimumDocs to update
        """

        docs = list(chain.from_iterable(items))  # type: ignore

        true_ts = list()

        for item in docs:
            item.update({"_bt": self.timestamp})
            frequencies = item.get("frequencies")

            # Don't allow minima (no imaginary frequencies) or cases where we
            # haven't calculated the frequencies
            if frequencies is None or len(frequencies) == 0:
                continue
            elif frequencies[0] is None or frequencies[0] > 0.0:
                continue

            # Don't allow more than two imaginary frequencies, and don't allow
            # a second imaginary frequency with magnitude greater than the
            # threshold
            if len(frequencies) == 1:
                true_ts.append(item)
            elif len(frequencies) == 2 and frequencies[1] >= self.negative_threshold:
                true_ts.append(item)
            elif frequencies[1] >= self.negative_threshold and frequencies[2] > 0:
                true_ts.append(item)
            else:
                continue

        molecule_ids = list({item["molecule_id"] for item in true_ts})

        if len(items) > 0:
            self.logger.info(f"Updating {len(docs)} molecules")
            self.transition_states.remove_docs({self.minima.key: {"$in": molecule_ids}})
            self.transition_states.update(
                docs=true_ts,
                key=["molecule_id"],
            )
        else:
            self.logger.info("No items to update")