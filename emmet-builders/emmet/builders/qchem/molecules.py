from datetime import datetime
from itertools import chain
from math import ceil
from typing import Dict, Iterable, Iterator, List, Optional

from maggma.builders import Builder
from maggma.stores import Store
from maggma.utils import grouper

from emmet.builders.settings import EmmetBuildSettings
from emmet.core.utils import group_structures, jsanitize
from emmet.core.qchem.molecule import MoleculeDoc
from emmet.core.qchem.task import TaskDocument
from emmet.core.molecules.bonds import make_mol_graph


__author__ = "Evan Spotte-Smith <ewcspottesmith@lbl.gov>"


SETTINGS = EmmetBuildSettings()


class MoleculesBuilder(Builder):
    """
    The MoleculesBuilder matches Q-Chem task documents by composition, charge, spin multiplicity,
    and bonding into molecules documents. The purpose of this builder is to group calculations
    and pick the best molecular structures (based on electronic energy)

    The process is as follows:

        1.) Find all documents with the same formula
        2.) Select only task documents for the task_types we can select properties from
        3.) Aggregate task documents based on composition, bonding, charge, and spin
        4.) Create a MoleculeDoc from the group of task documents
    """

    def __init__(
        self,
        tasks: Store,
        molecules: Store,
        query: Optional[Dict] = None,
        settings: Optional[EmmetBuildSettings] = None,
        **kwargs,
    ):
        """
        Args:
            tasks:  Store of task documents
            molecules: Store of molecules documents to prepare
            query: dictionary to limit tasks to be analyzed
            settings: EmmetSettings to use in the build process
        """

        self.tasks = tasks
        self.molecules = molecules
        self.query = query if query else dict()
        self.settings = EmmetBuildSettings.autoload(settings)
        self.kwargs = kwargs

        super().__init__(sources=[tasks], targets=[molecules])

    def ensure_indexes(self):
        """
        Ensures indices on the collections needed for building
        """

        # Basic search index for tasks
        self.tasks.ensure_index("task_id")
        self.tasks.ensure_index("last_updated")
        self.tasks.ensure_index("state")
        self.tasks.ensure_index("formula_alphabetical")

        # Search index for molecules
        self.molecules.ensure_index("molecule_id")
        self.molecules.ensure_index("last_updated")
        self.molecules.ensure_index("task_ids")

    def prechunk(self, number_splits: int) -> Iterable[Dict]:  # pragma: no cover
        """Prechunk the molecule builder for distributed computation"""

        temp_query = dict(self.query)
        temp_query["state"] = "successful"

        self.logger.info("Finding tasks to process")
        all_tasks = list(
            self.tasks.query(temp_query, [self.tasks.key, "formula_alphabetical"])
        )

        processed_tasks = set(self.molecules.distinct("task_ids"))
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
        Gets all items to process into molecules (and other) documents.
        This does no datetime checking; relying on on whether
        task_ids are included in the molecules Store

        Returns:
            generator or list relevant tasks and molecules to process into documents
        """
        pass

    def process_item(self, items: List[Dict]) -> List[Dict]:
        """
        Process the tasks into a MoleculeDoc

        Args:
            tasks [dict] : a list of task docs

        Returns:
            [dict] : a list of new molecule docs
        """
        pass

    def update_targets(self, items: List[Dict]):
        """
        Inserts the new molecules into the molecules collection

        Args:
            items [[dict]]: A list of molecules to update
        """
        pass

    def filter_and_group_tasks(
        self, tasks: List[TaskDocument]
    ) -> Iterator[List[TaskDocument]]:
        """
        Groups tasks by matching charges, partial spins, and bonding connectivity
        """
        pass