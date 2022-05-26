from datetime import datetime
from itertools import chain
from math import ceil
from typing import Optional, Iterable, Iterator, List, Dict

from maggma.builders import Builder
from maggma.core import Store
from maggma.utils import grouper

from emmet.core.qchem.molecule import MoleculeDoc
from emmet.core.molecules.redox import RedoxDoc
from emmet.core.utils import jsanitize
from emmet.builders.settings import EmmetBuildSettings


__author__ = "Evan Spotte-Smith"

SETTINGS = EmmetBuildSettings()


class RedoxBuilder(Builder):
    """
    The RedoxBuilder extracts the highest-quality redox data (vertical and
    adiabatic reduction and oxidation potentials, etc.)
    from a MoleculeDoc (lowest electronic energy, highest level of theory).

    The process is as follows:
        1. Gather MoleculeDocs by formula
        2. Collect entries for those MoleculeDocs
        3. Convert entries to RedoxDocs
    """

    def __init__(
        self,
        molecules: Store,
        redox: Store,
        query: Optional[Dict] = None,
        settings: Optional[EmmetBuildSettings] = None,
        **kwargs,
    ):

        self.molecules = molecules
        self.redox = redox
        self.query = query if query else dict()
        self.settings = EmmetBuildSettings.autoload(settings)
        self.kwargs = kwargs

        super().__init__(sources=[molecules], targets=[redox])

    def ensure_indexes(self):
        """
        Ensures indices on the collections needed for building
        """

        # Search index for molecules
        self.molecules.ensure_index("molecule_id")
        self.molecules.ensure_index("last_updated")
        self.molecules.ensure_index("task_ids")
        self.molecules.ensure_index("formula_alphabetical")

        # Search index for orbitals
        self.redox.ensure_index("molecule_id")
        self.redox.ensure_index("task_id")
        self.redox.ensure_index("last_updated")
        self.redox.ensure_index("formula_alphabetical")

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

        processed_docs = set([e for e in self.redox.distinct("molecule_id")])
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

        processed_docs = set([e for e in self.redox.distinct("molecule_id")])
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
        self.logger.debug(f"Processing {formula} : {mol_ids}")

        entries = list(chain.from_iterable([m.entries for m in mols]))

        redox_docs = RedoxDoc.from_entries(entries)

        self.logger.debug(f"Produced {len(redox_docs)} redox docs for {formula}")

        return jsanitize([doc.dict() for doc in redox_docs], allow_bson=True)

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
            self.logger.info(f"Updating {len(docs)} redox documents")
            self.redox.remove_docs({self.redox.key: {"$in": molecule_ids}})
            self.redox.update(
                docs=docs,
                key=["molecule_id"],
            )
        else:
            self.logger.info("No items to update")
