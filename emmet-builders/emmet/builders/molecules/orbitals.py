from datetime import datetime
from itertools import chain
from math import ceil
from typing import Optional, Iterable, Iterator, List, Dict

from maggma.builders import Builder
from maggma.core import Store
from maggma.utils import grouper

from emmet.core.qchem.task import TaskDocument
from emmet.core.qchem.molecule import MoleculeDoc, evaluate_lot
from emmet.core.molecules.orbitals import OrbitalDoc
from emmet.core.utils import jsanitize
from emmet.builders.settings import EmmetBuildSettings


__author__ = "Evan Spotte-Smith"

SETTINGS = EmmetBuildSettings()


class OrbitalBuilder(Builder):
    """
    The OrbitalBuilder extracts the highest-quality natural bonding orbital data
    from a MoleculeDoc (lowest electronic energy, highest level of theory).

    The process is as follows:
        1. Gather MoleculeDocs by formula
        2. For each doc, grab the best TaskDoc (doc including NBO data using
            the highest level of theory with lowest electronic energy for the
            molecule)
        3. Convert TaskDoc to OrbitalDoc
    """

    def __init__(
        self,
        tasks: Store,
        molecules: Store,
        orbitals: Store,
        query: Optional[Dict] = None,
        settings: Optional[EmmetBuildSettings] = None,
        **kwargs,
    ):

        self.tasks = tasks
        self.molecules = molecules
        self.orbitals = orbitals
        self.query = query if query else dict()
        self.settings = EmmetBuildSettings.autoload(settings)
        self.kwargs = kwargs

        super().__init__(sources=[tasks, molecules], targets=[orbitals])

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
        self.molecules.ensure_index("formula_alphabetical")

        # Search index for orbitals
        self.orbitals.ensure_index("molecule_id")
        self.orbitals.ensure_index("task_id")
        self.orbitals.ensure_index("last_updated")
        self.orbitals.ensure_index("formula_alphabetical")

    def prechunk(self, number_splits: int) -> Iterable[Dict]:  # pragma: no cover
        """Prechunk the builder for distributed computation"""

        temp_query = dict(self.query)
        temp_query["deprecated"] = False

        self.logger.info("Finding documents to process")
        all_mols = list(
            self.molecules.query(
                temp_query, [self.molecules.key, "formula_alphabetical"]
            )
        )

        processed_docs = set([e for e in self.orbitals.distinct("molecule_id")])
        to_process_docs = {d[self.molecules.key] for d in all_mols} - processed_docs
        to_process_forms = {
            d["formula_alphabetical"]
            for d in all_mols
            if d[self.molecules.key] in to_process_docs
        }

        N = ceil(len(to_process_forms) / number_splits)

        for formula_chunk in grouper(to_process_forms, N):
            yield {"query": {"formula_alphabetical": {"$in": list(formula_chunk)}}}

    def get_items(self) -> Iterator[List[Dict]]:
        """
        Gets all items to process into orbital documents.
        This does no datetime checking; relying on on whether
        task_ids are included in the orbitals Store

        Returns:
            generator or list relevant tasks and molecules to process into documents
        """

        self.logger.info("Orbital builder started")
        self.logger.info("Setting indexes")
        self.ensure_indexes()

        # Save timestamp to mark buildtime
        self.timestamp = datetime.utcnow()

        # Get all processed molecules
        temp_query = dict(self.query)
        temp_query["deprecated"] = False

        self.logger.info("Finding documents to process")
        all_mols = list(
            self.molecules.query(
                temp_query, [self.molecules.key, "formula_alphabetical"]
            )
        )

        processed_docs = set([e for e in self.orbitals.distinct("molecule_id")])
        to_process_docs = {d[self.molecules.key] for d in all_mols} - processed_docs
        to_process_forms = {
            d["formula_alphabetical"]
            for d in all_mols
            if d[self.molecules.key] in to_process_docs
        }

        self.logger.info(f"Found {len(to_process_docs)} unprocessed documents")
        self.logger.info(f"Found {len(to_process_forms)} unprocessed formulas")

        # Set total for builder bars to have a total
        self.total = len(to_process_forms)

        for formula in to_process_forms:
            mol_query = dict(temp_query)
            mol_query["formula_alphabetical"] = formula
            molecules = list(self.molecules.query(criteria=mol_query))

            yield molecules

    def process_item(self, items: List[Dict]) -> List[Dict]:
        """
        Process the tasks into an OrbitalDoc

        Args:
            tasks List[Dict] : a list of MoleculeDocs in dict form

        Returns:
            [dict] : a list of new orbital docs
        """

        mols = [MoleculeDoc(**item) for item in items]
        formula = mols[0].formula_alphabetical
        mol_ids = [m.molecule_id for m in mols]
        self.logger.info(f"Processing {formula} : {mol_ids}")

        orbital_docs = list()

        for mol in mols:
            # Must have NBO, and must specifically use NBO7
            orbital_entries = [
                e
                for e in mol.entries
                if e["output"]["nbo"] is not None
                and e["orig"]["rem"].get("run_nbo6", False)
            ]

            # No documents with NBO data; no documents to be made
            if len(orbital_entries) == 0:
                continue
            else:
                sorted_entries = sorted(
                    orbital_entries,
                    key=lambda x: (
                        sum(evaluate_lot(x["level_of_theory"])),
                        x["energy"],
                    ),
                )

                for best in sorted_entries:
                    task = best["task_id"]

                    task_doc = TaskDocument(
                        **self.tasks.query_one({"task_id": int(task)})
                    )

                    orbital_doc = OrbitalDoc.from_task(
                        task_doc, molecule_id=mol.molecule_id, deprecated=False
                    )

                    if orbital_doc is not None:
                        orbital_docs.append(orbital_doc)

        self.logger.debug(f"Produced {len(orbital_docs)} orbital docs for {formula}")

        return jsanitize([doc.dict() for doc in orbital_docs], allow_bson=True)

    def update_targets(self, items: List[List[Dict]]):
        """
        Inserts the new documents into the orbitals collection

        Args:
            items [[dict]]: A list of documents to update
        """

        docs = list(chain.from_iterable(items))  # type: ignore

        # Add timestamp
        for item in docs:
            item.update(
                {
                    "_bt": self.timestamp,
                }
            )

        molecule_ids = list({item["molecule_id"] for item in docs})

        if len(items) > 0:
            self.logger.info(f"Updating {len(docs)} orbital documents")
            self.orbitals.remove_docs({self.orbitals.key: {"$in": molecule_ids}})
            self.orbitals.update(
                docs=docs,
                key=["molecule_id"],
            )
        else:
            self.logger.info("No items to update")
