from collections import defaultdict
from datetime import datetime
from itertools import chain
from math import ceil

from maggma.builders import Builder
from maggma.core import Store
from maggma.utils import grouper

from emmet.builders.settings import EmmetBuildSettings
from emmet.core.molecules.atomic import (
    CHARGES_METHODS,
    SPINS_METHODS,
    PartialChargesDoc,
    PartialSpinsDoc,
)
from emmet.core.qchem.molecule import MoleculeDoc, evaluate_lot
from emmet.core.qchem.task import TaskDocument
from emmet.core.utils import jsanitize

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator

__author__ = "Evan Spotte-Smith"

SETTINGS = EmmetBuildSettings()


class PartialChargesBuilder(Builder):
    """
    The PartialChargesBuilder extracts partial charges data from a MoleculeDoc.

    Various methods can be used to define partial charges, including:
        - Mulliken
        - Restrained Electrostatic Potential (RESP)
        - Critic2
        - Natural Bonding Orbital (NBO) population analysis

    This builder will attempt to build documents for each molecule, in each solvent,
    with each method. For each molecule-solvent-method combination, the
    highest-quality data available (based on level of theory and electronic
    energy) will be used.

    The process is as follows:
        1. Gather MoleculeDocs by species hash
        2. For each molecule, group all tasks by solvent.
        3. For each solvent, sort tasks by level of theory and electronic energy
        4. For each method:
            4.1. Find task docs with necessary data to calculate partial charges by that method
            4.2. Take best (defined by level of theory and electronic energy) task
            4.3. Convert TaskDoc to PartialChargesDoc
    """

    def __init__(
        self,
        tasks: Store,
        molecules: Store,
        charges: Store,
        query: dict | None = None,
        methods: list | None = None,
        settings: EmmetBuildSettings | None = None,
        **kwargs,
    ):
        self.tasks = tasks
        self.molecules = molecules
        self.charges = charges
        self.query = query if query else dict()
        self.methods = methods if methods else CHARGES_METHODS
        self.settings = EmmetBuildSettings.autoload(settings)
        self.kwargs = kwargs

        super().__init__(sources=[tasks, molecules], targets=[charges], **kwargs)
        # Uncomment in case of issue with mrun not connecting automatically to collections
        # for i in [self.tasks, self.molecules, self.charges]:
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

        # Search index for charges
        self.charges.ensure_index("molecule_id")
        self.charges.ensure_index("task_id")
        self.charges.ensure_index("method")
        self.charges.ensure_index("solvent")
        self.charges.ensure_index("lot_solvent")
        self.charges.ensure_index("property_id")
        self.charges.ensure_index("last_updated")
        self.charges.ensure_index("formula_alphabetical")

    def prechunk(self, number_splits: int) -> Iterable[dict]:  # pragma: no cover
        """Prechunk the builder for distributed computation"""

        temp_query = dict(self.query)
        temp_query["deprecated"] = False

        self.logger.info("Finding documents to process")
        all_mols = list(
            self.molecules.query(temp_query, [self.molecules.key, "species_hash"])
        )

        processed_docs = set([e for e in self.charges.distinct("molecule_id")])
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

    def get_items(self) -> Iterator[list[dict]]:
        """
        Gets all items to process into partial charges documents.
        This does no datetime checking; relying on on whether
        task_ids are included in the charges Store

        Returns:
            generator or list relevant tasks and molecules to process into documents
        """

        self.logger.info("Partial charges builder started")
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

        processed_docs = set([e for e in self.charges.distinct("molecule_id")])
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

    def process_item(self, items: list[dict]) -> list[dict]:
        """
        Process the tasks into PartialChargesDocs

        Args:
            tasks list[dict] : a list of MoleculeDocs in dict form

        Returns:
            [dict] : a list of new partial charges docs
        """

        mols = [MoleculeDoc(**item) for item in items]
        shash = mols[0].species_hash
        mol_ids = [m.molecule_id for m in mols]
        self.logger.debug(f"Processing {shash} : {mol_ids}")

        charges_docs = list()

        for mol in mols:
            correct_charge_spin = [
                e
                for e in mol.entries
                if e["charge"] == mol.charge
                and e["spin_multiplicity"] == mol.spin_multiplicity
            ]

            # Organize by solvent environment
            by_solvent = defaultdict(list)
            for entry in correct_charge_spin:
                by_solvent[entry["solvent"]].append(entry)

            for solvent, entries in by_solvent.items():
                sorted_entries = sorted(
                    entries,
                    key=lambda x: (
                        sum(evaluate_lot(x["level_of_theory"])),
                        x["energy"],
                    ),
                )

                for method in self.methods:
                    # For each method, grab entries that have the relevant data
                    relevant_entries = [
                        e
                        for e in sorted_entries
                        if e.get(method) is not None
                        or e["output"].get(method) is not None
                    ]

                    if len(relevant_entries) == 0:
                        continue

                    # Grab task document of best entry
                    best_entry = relevant_entries[0]
                    task = best_entry["task_id"]

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

                    doc = PartialChargesDoc.from_task(
                        task_doc,
                        molecule_id=mol.molecule_id,
                        preferred_methods=[method],
                        deprecated=False,
                    )

                    charges_docs.append(doc)

        self.logger.debug(f"Produced {len(charges_docs)} charges docs for {shash}")

        return jsanitize([doc.model_dump() for doc in charges_docs], allow_bson=True)

    def update_targets(self, items: list[list[dict]]):
        """
        Inserts the new documents into the charges collection

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
            self.logger.info(f"Updating {len(docs)} partial charges documents")
            self.charges.remove_docs({self.charges.key: {"$in": molecule_ids}})
            # Neither molecule_id nor method need to be unique, but the combination must be
            self.charges.update(
                docs=docs,
                key=["molecule_id", "method", "solvent"],
            )
        else:
            self.logger.info("No items to update")


class PartialSpinsBuilder(Builder):
    """
    The PartialSpinsBuilder extracts partial spin data from a MoleculeDoc.

    Various methods can be used to define partial atomic spins, including:
        - Mulliken
        - Natural Bonding Orbital (NBO) population analysis

    This builder will attempt to build documents for each molecule, in each solvent,
    with each method. For each molecule-method combination, the highest-quality
    data available (based on level of theory and electronic energy) will be used.

    The process is as follows:
        1. Gather MoleculeDocs by species_hash
        2. For each molecule, group all tasks by solvent.
        3. For each solvent, sort tasks by level of theory and electronic energy
        4. For each method:
            4.1. Find task docs with necessary data to calculate partial charges by that method
            4.2. Take best (defined by level of theory and electronic energy) task
            4.3. Convert TaskDoc to PartialSpinsDoc
    """

    def __init__(
        self,
        tasks: Store,
        molecules: Store,
        spins: Store,
        query: dict | None = None,
        methods: list | None = None,
        settings: EmmetBuildSettings | None = None,
        **kwargs,
    ):
        self.tasks = tasks
        self.molecules = molecules
        self.spins = spins
        self.query = query if query else dict()
        self.methods = methods if methods else SPINS_METHODS
        self.settings = EmmetBuildSettings.autoload(settings)
        self.kwargs = kwargs

        super().__init__(sources=[tasks, molecules], targets=[spins], **kwargs)
        # Uncomment in case of issue with mrun not connecting automatically to collections
        # for i in [self.tasks, self.molecules, self.spins]:
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

        # Search index for spins
        self.spins.ensure_index("molecule_id")
        self.spins.ensure_index("task_id")
        self.spins.ensure_index("method")
        self.spins.ensure_index("solvent")
        self.spins.ensure_index("lot_solvent")
        self.spins.ensure_index("property_id")
        self.spins.ensure_index("last_updated")
        self.spins.ensure_index("formula_alphabetical")

    def prechunk(self, number_splits: int) -> Iterable[dict]:  # pragma: no cover
        """Prechunk the builder for distributed computation"""

        temp_query = dict(self.query)
        temp_query["deprecated"] = False

        self.logger.info("Finding documents to process")
        all_mols = list(
            self.molecules.query(temp_query, [self.molecules.key, "species_hash"])
        )

        processed_docs = set([e for e in self.spins.distinct("molecule_id")])
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

    def get_items(self) -> Iterator[list[dict]]:
        """
        Gets all items to process into partial spins documents.
        This does no datetime checking; relying on on whether
        task_ids are included in the spins Store

        Returns:
            generator or list relevant tasks and molecules to process into documents
        """

        self.logger.info("Partial spins builder started")
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

        processed_docs = set([e for e in self.spins.distinct("molecule_id")])
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

    def process_item(self, items: list[dict]) -> list[dict]:
        """
        Process the tasks into PartialSpinsDocs

        Args:
            tasks list[dict] : a list of MoleculeDocs in dict form

        Returns:
            [dict] : a list of new partial spins docs
        """

        mols = [MoleculeDoc(**item) for item in items]
        shash = mols[0].species_hash
        mol_ids = [m.molecule_id for m in mols]
        self.logger.debug(f"Processing {shash} : {mol_ids}")

        spins_docs = list()

        for mol in mols:
            # Molecule with spin multiplicity 1 has no partial spins
            if mol.spin_multiplicity == 1:
                continue

            correct_charge_spin = [
                e
                for e in mol.entries
                if e["charge"] == mol.charge
                and e["spin_multiplicity"] == mol.spin_multiplicity
            ]

            # Organize by solvent environment
            by_solvent = defaultdict(list)
            for entry in correct_charge_spin:
                by_solvent[entry["solvent"]].append(entry)

            for solvent, entries in by_solvent.items():
                sorted_entries = sorted(
                    entries,
                    key=lambda x: (
                        sum(evaluate_lot(x["level_of_theory"])),
                        x["energy"],
                    ),
                )

                for method in self.methods:
                    # For each method, grab entries that have the relevant data
                    relevant_entries = [
                        e
                        for e in sorted_entries
                        if e.get(method) is not None
                        or e["output"].get(method) is not None
                    ]

                    if len(relevant_entries) == 0:
                        continue

                    # Grab task document of best entry
                    best_entry = relevant_entries[0]
                    task = best_entry["task_id"]

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

                    doc = PartialSpinsDoc.from_task(
                        task_doc,
                        molecule_id=mol.molecule_id,
                        preferred_methods=[method],
                        deprecated=False,
                    )

                    spins_docs.append(doc)

        self.logger.debug(f"Produced {len(spins_docs)} partial spins docs for {shash}")

        return jsanitize([doc.model_dump() for doc in spins_docs], allow_bson=True)

    def update_targets(self, items: list[list[dict]]):
        """
        Inserts the new documents into the spins collection

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
            self.logger.info(f"Updating {len(docs)} partial spins documents")
            self.spins.remove_docs({self.spins.key: {"$in": molecule_ids}})
            # Neither molecule_id nor method need to be unique, but the combination must be
            self.spins.update(
                docs=docs,
                key=["molecule_id", "method", "solvent"],
            )
        else:
            self.logger.info("No items to update")
