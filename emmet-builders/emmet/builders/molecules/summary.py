from datetime import datetime
from itertools import chain
from math import ceil
from typing import Optional, Iterable, Iterator, List, Dict

from maggma.builders import Builder
from maggma.core import Store
from maggma.utils import grouper

from emmet.core.molecules.summary import SummaryDoc
from emmet.core.utils import jsanitize
from emmet.builders.settings import EmmetBuildSettings


__author__ = "Evan Spotte-Smith"

SETTINGS = EmmetBuildSettings()


class SummaryBuilder(Builder):
    """
    The SummaryBuilder collects all property documents and gathers their properties
    into a single SummaryDoc

    The process is as follows:
        1. Gather MoleculeDocs by formula
        2. For each doc, grab the relevant property docs
        3. Convert property docs to SummaryDoc
    """

    def __init__(
        self,
        molecules: Store,
        charges: Store,
        spins: Store,
        bonds: Store,
        orbitals: Store,
        redox: Store,
        thermo: Store,
        vibes: Store,
        summary: Store,
        query: Optional[Dict] = None,
        settings: Optional[EmmetBuildSettings] = None,
        **kwargs,
    ):

        self.molecules = molecules
        self.charges = charges
        self.spins = spins
        self.bonds = bonds
        self.orbitals = orbitals
        self.redox = redox
        self.thermo = thermo
        self.vibes = vibes
        self.summary = summary
        self.query = query if query else dict()
        self.settings = EmmetBuildSettings.autoload(settings)
        self.kwargs = kwargs

        super().__init__(
            sources=[molecules, charges, spins, bonds, orbitals, redox, thermo, vibes],
            targets=[summary],
        )

    def ensure_indexes(self):
        """
        Ensures indices on the collections needed for building
        """

        # Search index for molecules
        self.molecules.ensure_index("molecule_id")
        self.molecules.ensure_index("last_updated")
        self.molecules.ensure_index("task_ids")
        self.molecules.ensure_index("formula_alphabetical")

        # Search index for charges
        self.charges.ensure_index("molecule_id")
        self.charges.ensure_index("method")
        self.charges.ensure_index("task_id")
        self.charges.ensure_index("last_updated")
        self.charges.ensure_index("formula_alphabetical")

        # Search index for charges
        self.spins.ensure_index("molecule_id")
        self.spins.ensure_index("method")
        self.spins.ensure_index("task_id")
        self.spins.ensure_index("last_updated")
        self.spins.ensure_index("formula_alphabetical")

        # Search index for charges
        self.bonds.ensure_index("molecule_id")
        self.bonds.ensure_index("method")
        self.bonds.ensure_index("task_id")
        self.bonds.ensure_index("last_updated")
        self.bonds.ensure_index("formula_alphabetical")

        # Search index for orbitals
        self.orbitals.ensure_index("molecule_id")
        self.orbitals.ensure_index("task_id")
        self.orbitals.ensure_index("last_updated")
        self.orbitals.ensure_index("formula_alphabetical")

        # Search index for orbitals
        self.redox.ensure_index("molecule_id")
        self.redox.ensure_index("task_id")
        self.redox.ensure_index("last_updated")
        self.redox.ensure_index("formula_alphabetical")

        # Search index for thermo
        self.thermo.ensure_index("molecule_id")
        self.thermo.ensure_index("task_id")
        self.thermo.ensure_index("last_updated")
        self.thermo.ensure_index("formula_alphabetical")

        # Search index for vibrational properties
        self.vibes.ensure_index("molecule_id")
        self.vibes.ensure_index("task_id")
        self.vibes.ensure_index("last_updated")
        self.vibes.ensure_index("formula_alphabetical")

        # Search index for molecules
        self.summary.ensure_index("molecule_id")
        self.summary.ensure_index("last_updated")
        self.summary.ensure_index("formula_alphabetical")

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

        processed_docs = set([e for e in self.summary.distinct("molecule_id")])
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
        Gets all items to process into summary documents.
        This does no datetime checking; relying on on whether
        task_ids are included in the summary Store

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

        processed_docs = set([e for e in self.summary.distinct("molecule_id")])
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
        Process the tasks into a SummaryDoc

        Args:
            tasks List[Dict] : a list of MoleculeDocs in dict form

        Returns:
            [dict] : a list of new orbital docs
        """

        mols = items
        formula = mols[0]["formula_alphabetical"]
        mol_ids = [m["molecule_id"] for m in mols]
        self.logger.debug(f"Processing {formula} : {mol_ids}")

        summary_docs = list()

        for mol in mols:
            mol_id = mol["molecule_id"]
            d = {
                "molecules": mol,
                "partial_charges": list(self.charges.query({"molecule_id": mol_id})),
                "partial_spins": list(self.spins.query({"molecule_id": mol_id})),
                "bonding": list(self.bonds.query({"molecule_id": mol_id})),
                "orbitals": self.orbitals.query_one({"molecule_id": mol_id}),
                "redox": self.redox.query_one({"molecule_id": mol_id}),
                "thermo": self.thermo.query_one({"molecule_id": mol_id}),
                "vibration": self.vibes.query_one({"molecule_id": mol_id}),
            }

            to_delete = list()

            for k, v in d.items():
                if isinstance(v, list) and len(v) == 0:
                    to_delete.append(k)

            for td in to_delete:
                del d[td]

            summary_doc = SummaryDoc.from_docs(molecule_id=mol_id, **d)
            summary_docs.append(summary_doc)

        self.logger.debug(f"Produced {len(summary_docs)} summary docs for {formula}")

        return jsanitize([doc.dict() for doc in summary_docs], allow_bson=True)

    def update_targets(self, items: List[List[Dict]]):
        """
        Inserts the new documents into the summary collection

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
            self.logger.info(f"Updating {len(docs)} summary documents")
            self.summary.remove_docs({self.summary.key: {"$in": molecule_ids}})
            self.summary.update(
                docs=docs,
                key=["molecule_id"],
            )
        else:
            self.logger.info("No items to update")
