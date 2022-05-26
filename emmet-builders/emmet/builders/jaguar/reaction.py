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
from emmet.core.jaguar.reactions import ReactionDoc


__author__ = "Evan Spotte-Smith <ewcspottesmith@lbl.gov>"


SETTINGS = EmmetBuildSettings()


class ReactionAssociationBuilder(Builder):
    """
    The ReactionAssociationBuilder connects transition-states (TS) with their
    corresponding reaction endpoints (reactants and products). It also
    calculates the properties of the corresponding reaction, including reaction
    thermodynamics and bond changes.

    The process is as follows:

        1.) Separate transition-states by overall formula
        2.) Search minima for documents with
            - The same formula
            - The same charge
            - The same spin multiplicity (conical intersections between different
            PES are not currently considered)
            - A geometry optimized at same level of theory as the TS...
                - where the initial structure of that geometry optimization lies
                    along the reaction coordinate of the transition-state
        3.) If there are multiple viable minima for the same endpoint (reactant
            or product), take the lowest-energy document
        4.) Combine TS and minima to form ReactionDoc

    Note that this builder will not perform any filtering - in particular, if
    given calculations representing essentially the same reaction (but perhaps
    with the TS or the product in a different conformation), it will produce
    multiple different ReactionDocs. Reducing redundant reactions is the job
    of the ReactionBuilder.

    Also note that, at present, this builder cannot handle cases where one of
    the endpoints failed to optimize because various reactants or products
    moved away to infinite separation. Accounting for such cases is a goal for a
    future version of this code.
    """

    def __init__(
        self,
        transition_states: Store,
        minima: Store,
        assoc: Store,
        query: Optional[Dict] = None,
        settings: Optional[EmmetBuildSettings] = None,
        **kwargs,
    ):
        """
        Args:
            transition_states:  Store of TransitionStateDocs
            minima: Store of PESMinimumDocs
            assoc: Store to be populated with ReactionDocs
            query: dictionary to limit tasks to be analyzed
            settings: EmmetSettings to use in the build process
        """

        self.transition_states = transition_states
        self.minima = minima
        self.assoc = assoc
        self.query = query if query else dict()
        self.settings = EmmetBuildSettings.autoload(settings)
        self.kwargs = kwargs

        super().__init__(sources=[transition_states, minima], targets=[assoc])

    def ensure_indexes(self):
        """
        Ensures indices on the collections needed for building
        """

        # Search index for minima
        self.minima.ensure_index("molecule_id")
        self.minima.ensure_index("last_updated")
        self.minima.ensure_index("task_ids")
        self.minima.ensure_index("formula_alphabetical")

        # Search index for transition-states
        self.transition_states.ensure_index("molecule_id")
        self.transition_states.ensure_index("last_updated")
        self.transition_states.ensure_index("task_ids")
        self.transition_states.ensure_index("formula_alphabetical")

        # Search index for reactions
        self.assoc.ensure_index("reaction_id")
        self.assoc.ensure_index("transition_state_id")
        self.assoc.ensure_index("reactant_id")
        self.assoc.ensure_index("product_id")
        self.assoc.ensure_index("formla_alphabetical")

    def prechunk(self, number_splits: int) -> Iterable[Dict]:  # pragma: no cover
        """Prechunk the ReactionAssociationBuilder for distributed computation"""

        temp_query = dict(self.query)
        temp_query["success"] = True

        self.logger.info("Finding tasks to process")
        all_ts = list(
            self.transition_states.query(temp_query, [self.transition_states.key,
                                                      "formula_alphabetical"])
        )

        processed_ts = set(self.assoc.distinct("transition_state_id"))
        to_process_ts = {d[self.transition_states.key] for d in all_ts} - processed_ts
        to_process_forms = {
            d["formula_alphabetical"]
            for d in all_ts
            if d[self.transition_states.key] in to_process_ts
        }

        N = ceil(len(to_process_forms) / number_splits)

        for formula_chunk in grouper(to_process_forms, N):
            yield {"query": {"formula_alphabetical": {"$in": list(formula_chunk)}}}

    def get_items(self) -> Iterator[List[Dict]]:
        """
        Gets all transition-states to process into ReactionDocs.

        Returns:
            generator or list relevant transition-states to process into documents
        """

        self.logger.info("Reaction Association Builder started")

        self.logger.info("Setting indexes")
        self.ensure_indexes()

        # Save timestamp to mark buildtime
        self.timestamp = datetime.utcnow()

        # Get all processed tasks
        temp_query = dict(self.query)
        temp_query["deprecated"] = False

        self.logger.info("Finding tasks to process")
        all_ts = list(
            self.transition_states.query(temp_query, [self.transition_states.key,
                                                      "formula_alphabetical"])
        )

        processed_ts = set(self.assoc.distinct("transition_state_id"))
        to_process_ts = {d[self.transition_states.key] for d in all_ts} - processed_ts
        to_process_forms = {
            d["formula_alphabetical"]
            for d in all_ts
            if d[self.transition_states.key] in to_process_ts
        }

        self.logger.info(f"Found {len(to_process_ts)} unprocessed transition-states")
        self.logger.info(f"Found {len(to_process_forms)} unprocessed formulas")

        # Set total for builder bars to have a total
        self.total = len(to_process_forms)

        for formula in to_process_forms:
            ts_query = dict(temp_query)
            ts_query["formula_alphabetical"] = formula
            tss = list(
                self.transition_states.query(criteria=ts_query)
            )

            #TODO: Do I need to do validation?
            # Presumably if these TS have already been turned into documents
            # using another builder, they should be fine?

            yield tss

    def process_item(self, items: List[Dict]) -> List[Dict]:
        """
        Process the tasks into a ReactionDoc

        Args:
            tasks [dict] : a list of TransitionStateDocs

        Returns:
            [dict] : a list of new ReactionDocs
        """

        tasks = [TaskDocument(**task) for task in items if task["is_valid"]]
        formula = tasks[0].formula_alphabetical
        task_ids = [task.calcid for task in tasks]
        self.logger.debug(f"Processing {formula} : {task_ids}")
        minima = list()

        for group in filter_and_group_tasks(tasks, self.settings):
            try:
                minima.append(PESMinimumDoc.from_tasks(group))
            except Exception as e:
                failed_ids = list({t_.calcid for t_ in group})
                doc = PESPointDoc.construct_deprecated_pes_point(tasks)
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