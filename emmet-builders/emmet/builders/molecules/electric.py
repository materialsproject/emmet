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
from emmet.core.molecules.electric import ElectricMultipoleDoc
from emmet.core.utils import jsanitize
from emmet.builders.settings import EmmetBuildSettings


__author__ = "Evan Spotte-Smith"

SETTINGS = EmmetBuildSettings()


class ElectricMultipoleBuilder(Builder):
    """
    The ElectricMultipoleBuilder defines the electric multipole properties of a MoleculeDoc.

    This builder will attempt to build documents for each molecule, in each solvent.
    For each molecule-solvent combination, the highest-quality
    data available (based on level of theory and electronic energy) will be used.

    The process is as follows:
        1. Gather MoleculeDocs by species hash
        2. For each molecule, group all tasks by solvent.
        3. For each solvent, grab the best TaskDoc (doc with elecrtric dipole/multipole information
        that has the highest level of theory with the lowest electronic energy) for the molecule
        4. Convert TaskDoc to ElectricMultipoleDoc
    """

    def __init__(
        self,
        tasks: Store,
        molecules: Store,
        multipoles: Store,
        query: Optional[Dict] = None,
        settings: Optional[EmmetBuildSettings] = None,
        **kwargs,
    ):
        self.tasks = tasks
        self.molecules = molecules
        self.multipoles = multipoles
        self.query = query if query else dict()
        self.settings = EmmetBuildSettings.autoload(settings)
        self.kwargs = kwargs

        super().__init__(sources=[tasks, molecules], targets=[multipoles], **kwargs)
        # Uncomment in case of issue with mrun not connecting automatically to collections
        # for i in [self.tasks, self.molecules, self.multipoles]:
        #     try:
        #         i.connect()
        #     except Exception as e:
        #         print("Could not connect,", e)

    def ensure_indexes(self):
        """
        Ensures indices on the collections needed for building
        """

        # Basic search index for tasks
        self.tasks.ensure_index("task_id")
        self.tasks.ensure_index("last_updated")
        self.tasks.ensure_index("state")
        self.tasks.ensure_index("formula_alphabetical")
        self.tasks.ensure_index("species_hash")

        # Search index for molecules
        self.molecules.ensure_index("molecule_id")
        self.molecules.ensure_index("last_updated")
        self.molecules.ensure_index("task_ids")
        self.molecules.ensure_index("formula_alphabetical")
        self.molecules.ensure_index("species_hash")

        # Search index for electric
        self.multipoles.ensure_index("method")
        self.multipoles.ensure_index("molecule_id")
        self.multipoles.ensure_index("task_id")
        self.multipoles.ensure_index("solvent")
        self.multipoles.ensure_index("lot_solvent")
        self.multipoles.ensure_index("property_id")
        self.multipoles.ensure_index("last_updated")
        self.multipoles.ensure_index("formula_alphabetical")

    def prechunk(self, number_splits: int) -> Iterable[Dict]:  # pragma: no cover
        """Prechunk the builder for distributed computation"""

        temp_query = dict(self.query)
        temp_query["deprecated"] = False

        self.logger.info("Finding documents to process")
        all_mols = list(
            self.molecules.query(temp_query, [self.molecules.key, "species_hash"])
        )

        processed_docs = set([e for e in self.multipoles.distinct("molecule_id")])
        to_process_docs = {d[self.molecules.key] for d in all_mols} - processed_docs
        to_process_hashes = {
            d["species_hash"]
            for d in all_mols
            if d[self.molecules.key] in to_process_docs
        }

        N = ceil(len(to_process_hashes) / number_splits)

        for hash_chunk in grouper(to_process_hashes, N):
            query = dict(temp_query)
            query["species_hash"] = {"$in": list(hash_chunk)}
            yield {"query": query}

    def get_items(self) -> Iterator[List[Dict]]:
        """
        Gets all items to process into multipole documents.
        This does no datetime checking; relying on on whether
        task_ids are included in the multipoles Store

        Returns:
            generator or list relevant tasks and molecules to process into documents
        """

        self.logger.info("Electric multipoles builder started")
        self.logger.info("Setting indexes")
        self.ensure_indexes()

        # Save timestamp to mark buildtime
        self.timestamp = datetime.utcnow()

        # Get all processed molecules
        temp_query = dict(self.query)
        temp_query["deprecated"] = False

        self.logger.info("Finding documents to process")
        all_mols = list(
            self.molecules.query(temp_query, [self.molecules.key, "species_hash"])
        )

        processed_docs = set([e for e in self.multipoles.distinct("molecule_id")])
        to_process_docs = {d[self.molecules.key] for d in all_mols} - processed_docs
        to_process_hashes = {
            d["species_hash"]
            for d in all_mols
            if d[self.molecules.key] in to_process_docs
        }

        self.logger.info(f"Found {len(to_process_docs)} unprocessed documents")
        self.logger.info(f"Found {len(to_process_hashes)} unprocessed hashes")

        # Set total for builder bars to have a total
        self.total = len(to_process_hashes)

        for shash in to_process_hashes:
            mol_query = dict(temp_query)
            mol_query["species_hash"] = shash
            molecules = list(self.molecules.query(criteria=mol_query))

            yield molecules

    def process_item(self, items: List[Dict]) -> List[Dict]:
        """
        Process the tasks into ElectricMultipoleDocs

        Args:
            tasks List[Dict] : a list of MoleculeDocs in dict form

        Returns:
            [dict] : a list of new electric multipole docs
        """

        mols = [MoleculeDoc(**item) for item in items]
        shash = mols[0].species_hash
        mol_ids = [m.molecule_id for m in mols]
        self.logger.debug(f"Processing {shash} : {mol_ids}")

        multipole_docs = list()

        for mol in mols:
            # Relevant tasks are those with the correct charge and spin
            # for which there are AT LEAST electric dipoles present
            # (ideally, multipole information would also be present)
            multip_entries = [
                e
                for e in mol.entries
                if e["charge"] == mol.charge
                and e["spin_multiplicity"] == mol.spin_multiplicity
                and (e["output"].get("dipoles") is not None)
            ]

            # Organize by solvent environment
            by_solvent = defaultdict(list)
            for entry in multip_entries:
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

                tdoc = self.tasks.query_one(
                    {
                        "task_id": task,
                        "species_hash": shash,
                        "orig": {"$exists": True},
                    }
                )

                if tdoc is None:
                    try:
                        tdoc = self.tasks.query_one(
                            {
                                "task_id": int(task),
                                "species_hash": shash,
                                "orig": {"$exists": True},
                            }
                        )
                    except ValueError:
                        tdoc = None

                if tdoc is None:
                    continue

                task_doc = TaskDocument(**tdoc)

                if task_doc is None:
                    continue

                multipole_doc = ElectricMultipoleDoc.from_task(
                    task_doc, molecule_id=mol.molecule_id, deprecated=False
                )
                multipole_docs.append(multipole_doc)

        self.logger.debug(
            f"Produced {len(multipole_docs)} electric multipole docs for {shash}"
        )

        return jsanitize([doc.model_dump() for doc in multipole_docs], allow_bson=True)

    def update_targets(self, items: List[List[Dict]]):
        """
        Inserts the new documents into the multipoles collection

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
            self.logger.info(f"Updating {len(docs)} electric multipole documents")
            self.multipoles.remove_docs({self.multipoles.key: {"$in": molecule_ids}})
            # Neither molecule_id nor method need to be unique, but the combination must be
            self.multipoles.update(
                docs=docs,
                key=["molecule_id", "solvent"],
            )
        else:
            self.logger.info("No items to update")
