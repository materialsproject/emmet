from collections import defaultdict
from datetime import datetime
from itertools import chain
from math import ceil
from typing import Optional, Iterable, Iterator, List, Dict

from maggma.builders import Builder
from maggma.core import Store
from maggma.utils import grouper

from emmet.core.qchem.task import TaskDocument
from emmet.core.qchem.molecule import MoleculeDoc, evaluate_lot
from emmet.core.molecules.vibration import VibrationDoc
from emmet.core.utils import jsanitize
from emmet.builders.settings import EmmetBuildSettings


__author__ = "Evan Spotte-Smith"

SETTINGS = EmmetBuildSettings()


class VibrationBuilder(Builder):
    """
    The VibrationBuilder extracts the highest-quality vibrational data from a
    MoleculeDoc (lowest electronic energy, highest level of theory for
    each solvent available).

    The process is as follows:
        1. Gather MoleculeDocs by formula
        2. For each doc, sort tasks by solvent
        3. For each solvent, grab the best TaskDoc (doc with vibrational
            information that has the highest level of theory with lowest
             electronic energy for the molecule)
        4. Convert TaskDoc to VibrationDoc

    Note that if no tasks associated with a given MoleculeDoc have vibrational
    data associated with them, then no VibrationDoc will be made for
    that molecule.
    """

    def __init__(
        self,
        tasks: Store,
        molecules: Store,
        vibes: Store,
        query: Optional[Dict] = None,
        settings: Optional[EmmetBuildSettings] = None,
        **kwargs,
    ):

        self.tasks = tasks
        self.molecules = molecules
        self.vibes = vibes
        self.query = query if query else dict()
        self.settings = EmmetBuildSettings.autoload(settings)
        self.kwargs = kwargs

        super().__init__(sources=[tasks, molecules], targets=[vibes])

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

        # Search index for vibrational properties
        self.vibes.ensure_index("molecule_id")
        self.vibes.ensure_index("task_id")
        self.vibes.ensure_index("solvent")
        self.vibes.ensure_index("lot_solvent")
        self.vibes.ensure_index("property_id")
        self.vibes.ensure_index("last_updated")
        self.vibes.ensure_index("formula_alphabetical")

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

        processed_docs = set([e for e in self.vibes.distinct("molecule_id")])
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
        Gets all items to process into vibration documents.
        This does no datetime checking; relying on on whether
        task_ids are included in the vibes Store

        Returns:
            generator or list relevant tasks and molecules to process into documents
        """

        self.logger.info("Vibration builder started")
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

        processed_docs = set([e for e in self.vibes.distinct("molecule_id")])
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
        Process the tasks into VibrationDocs

        Args:
            items List[Dict] : a list of MoleculeDocs in dict form

        Returns:
            [dict] : a list of new vibration docs
        """

        mols = [MoleculeDoc(**item) for item in items]
        formula = mols[0].formula_alphabetical
        mol_ids = [m.molecule_id for m in mols]
        self.logger.debug(f"Processing {formula} : {mol_ids}")

        vibe_docs = list()

        for mol in mols:
            vibe_entries = [
                e
                for e in mol.entries
                if e["charge"] == mol.charge
                and e["spin_multiplicity"] == mol.spin_multiplicity
                and e["output"].get("frequencies") is not None
            ]

            # Organize by solvent environment
            by_solvent = defaultdict(list)
            for entry in vibe_entries:
                by_solvent[entry["solvent"]].append(entry)

            for solvent, entries in by_solvent.items():

                # No documents with enthalpy and entropy
                if len(entries) == 0:
                    continue
                else:
                    best = sorted(
                        entries,
                        key=lambda x: (
                            sum(evaluate_lot(x["level_of_theory"])),
                            x["energy"],
                        ),
                    )[0]
                    task = best["task_id"]

                task_doc = TaskDocument(
                        **self.tasks.query_one({"task_id": int(task),
                                                "formula_alphabetical": formula,
                                                "orig": {"$exists": True}})
                )

                if task_doc is None:
                    continue

                vibe_doc = VibrationDoc.from_task(
                    task_doc, molecule_id=mol.molecule_id, deprecated=False
                )
                vibe_docs.append(vibe_doc)

        self.logger.debug(f"Produced {len(vibe_docs)} vibration docs for {formula}")

        return jsanitize([doc.dict() for doc in vibe_docs], allow_bson=True)

    def update_targets(self, items: List[List[Dict]]):
        """
        Inserts the new vibration docs into the vibes collection

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
            self.logger.info(f"Updating {len(docs)} vibration documents")
            self.vibes.remove_docs({self.vibes.key: {"$in": molecule_ids}})
            self.vibes.update(
                docs=docs,
                key=["molecule_id"],
            )
        else:
            self.logger.info("No items to update")
