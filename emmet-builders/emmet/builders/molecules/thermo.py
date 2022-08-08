import os

from datetime import datetime
from itertools import chain
from math import ceil
from typing import Optional, Iterable, Iterator, List, Dict

from monty.serialization import loadfn

from maggma.builders import Builder
from maggma.core import Store
from maggma.utils import grouper

from emmet.core.qchem.task import TaskDocument
from emmet.core.qchem.molecule import MoleculeDoc, best_lot, evaluate_lot
from emmet.core.molecules.thermo import get_free_energy, ThermoDoc
from emmet.core.utils import jsanitize
from emmet.builders.settings import EmmetBuildSettings


__author__ = "Evan Spotte-Smith"

SETTINGS = EmmetBuildSettings()

single_mol_thermo = {
    'Zn': {'enthalpy': 1.481, 'entropy': 38.384},
    'Xe': {'enthalpy': 1.481, 'entropy': 40.543},
    'Tl': {'enthalpy': 1.481, 'entropy': 41.857},
    'Ti': {'enthalpy': 1.481, 'entropy': 37.524},
    'Te': {'enthalpy': 1.481, 'entropy': 40.498},
    'Sr': {'enthalpy': 1.481, 'entropy': 39.334},
    'Sn': {'enthalpy': 1.481, 'entropy': 40.229},
    'Si': {'enthalpy': 1.481, 'entropy': 35.921},
    'Sb': {'enthalpy': 1.481, 'entropy': 40.284},
    'Se': {'enthalpy': 1.481, 'entropy': 39.05},
    'S': {'enthalpy': 1.481, 'entropy': 36.319},
    'Rn': {'enthalpy': 1.481, 'entropy': 42.095},
    'Pt': {'enthalpy': 1.481, 'entropy': 41.708},
    'Rb': {'enthalpy': 1.481, 'entropy': 39.23},
    'Po': {'enthalpy': 1.481, 'entropy': 41.915},
    'Pb': {'enthalpy': 1.481, 'entropy': 41.901},
    'P': {'enthalpy': 1.481, 'entropy': 36.224},
    'O': {'enthalpy': 1.481, 'entropy': 34.254},
    'Ne': {'enthalpy': 1.481, 'entropy': 34.919},
    'N': {'enthalpy': 1.481, 'entropy': 33.858},
    'Na': {'enthalpy': 1.481, 'entropy': 35.336},
    'Mg': {'enthalpy': 1.481, 'entropy': 35.462},
    'Li': {'enthalpy': 1.481, 'entropy': 31.798},
    'Kr': {'enthalpy': 1.481, 'entropy': 39.191},
    'K': {'enthalpy': 1.481, 'entropy': 36.908},
    'In': {'enthalpy': 1.481, 'entropy': 40.132},
    'I': {'enthalpy': 1.481, 'entropy': 40.428},
    'H': {'enthalpy': 1.481, 'entropy': 26.014},
    'He': {'enthalpy': 1.481, 'entropy': 30.125},
    'Ge': {'enthalpy': 1.481, 'entropy': 38.817},
    'Ga': {'enthalpy': 1.481, 'entropy': 38.609},
    'F': {'enthalpy': 1.481, 'entropy': 34.767},
    'Cu': {'enthalpy': 1.481, 'entropy': 38.337},
    'Cl': {'enthalpy': 1.481, 'entropy': 36.586},
    'Ca': {'enthalpy': 1.481, 'entropy': 36.984},
    'C': {'enthalpy': 1.481, 'entropy': 33.398},
    'Br': {'enthalpy': 1.481, 'entropy': 39.012},
    'Bi': {'enthalpy': 1.481, 'entropy': 41.915},
    'Be': {'enthalpy': 1.481, 'entropy': 32.544},
    'Ba': {'enthalpy': 1.481, 'entropy': 40.676},
    'B': {'enthalpy': 1.481, 'entropy': 33.141},
    'Au': {'enthalpy': 1.481, 'entropy': 41.738},
    'At': {'enthalpy': 1.481, 'entropy': 41.929},
    'As': {'enthalpy': 1.481, 'entropy': 38.857},
    'Ar': {'enthalpy': 1.481, 'entropy': 36.983},
    'Al': {'enthalpy': 1.481, 'entropy': 35.813},
    'Ag': {'enthalpy': 1.481, 'entropy': 39.917}
}


class ThermoBuilder(Builder):
    """
    The ThermoBuilder extracts the highest-quality thermodynamic data from a
    MoleculeDoc (lowest electronic energy, highest level of theory).

    The process is as follows:
        1. Gather MoleculeDocs by formula
        2. For each doc, grab the best TaskDoc (doc with as much thermodynamic
            information as possible using the highest level of theory with
            lowest electronic energy for the molecule)
        3. Convert TaskDoc to ThermoDoc
    """

    def __init__(
        self,
        tasks: Store,
        molecules: Store,
        thermo: Store,
        query: Optional[Dict] = None,
        settings: Optional[EmmetBuildSettings] = None,
        **kwargs,
    ):

        self.tasks = tasks
        self.molecules = molecules
        self.thermo = thermo
        self.query = query if query else dict()
        self.settings = EmmetBuildSettings.autoload(settings)
        self.kwargs = kwargs

        super().__init__(sources=[tasks, molecules], targets=[thermo])

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

        # Search index for thermo
        self.thermo.ensure_index("molecule_id")
        self.thermo.ensure_index("task_id")
        self.thermo.ensure_index("last_updated")
        self.thermo.ensure_index("formula_alphabetical")

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

        processed_docs = set([e for e in self.thermo.distinct("molecule_id")])
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
        Gets all items to process into thermo documents.
        This does no datetime checking; relying on on whether
        task_ids are included in the thermo Store

        Returns:
            generator or list relevant tasks and molecules to process into documents
        """

        self.logger.info("Thermo builder started")
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

        processed_docs = set([e for e in self.thermo.distinct("molecule_id")])
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
        Process the tasks into a ThermoDoc

        Args:
            items List[dict] : a list of MoleculeDocs in dict form

        Returns:
            [dict] : a list of new thermo docs
        """

        mols = [MoleculeDoc(**item) for item in items]
        formula = mols[0].formula_alphabetical
        mol_ids = [m.molecule_id for m in mols]
        self.logger.debug(f"Processing {formula} : {mol_ids}")

        thermo_docs = list()

        for mol in mols:
            thermo_entries = [
                e
                for e in mol.entries
                if e["output"]["enthalpy"] is not None
                and e["output"]["entropy"] is not None
            ]

            # No documents with enthalpy and entropy
            if len(thermo_entries) == 0:
                best = mol.best_entries[best_lot(mol)]
                task = best["task_id"]
            else:
                best = sorted(
                    thermo_entries,
                    key=lambda x: (
                        sum(evaluate_lot(x["level_of_theory"])),
                        x["energy"],
                    ),
                )[0]
                task = best["task_id"]

            task_doc = TaskDocument(**self.tasks.query_one({"task_id": int(task)}))

            thermo_doc = ThermoDoc.from_task(
                task_doc, molecule_id=mol.molecule_id, deprecated=False
            )

            initial_mol = task_doc.output.initial_molecule
            # If single atom, try to add enthalpy and entropy
            if len(initial_mol) == 1:
                if (
                    thermo_doc.total_enthalpy is None
                    or thermo_doc.total_entropy is None
                ):
                    formula = initial_mol.composition.alphabetical_formula
                    if formula in single_mol_thermo:
                        vals = single_mol_thermo[formula]
                        thermo_doc.total_enthalpy = vals["enthalpy"] * 0.043363
                        thermo_doc.total_entropy = vals["entropy"] * 0.000043363
                        thermo_doc.translational_enthalpy = vals["enthalpy"] * 0.043363
                        thermo_doc.translational_entropy = vals["entropy"] * 0.000043363
                        thermo_doc.free_energy = get_free_energy(
                            thermo_doc.electronic_energy,
                            vals["enthalpy"],
                            vals["entropy"],
                        )

            thermo_docs.append(thermo_doc)

        self.logger.debug(f"Produced {len(thermo_docs)} thermo docs for {formula}")

        return jsanitize([doc.dict() for doc in thermo_docs], allow_bson=True)

    def update_targets(self, items: List[List[Dict]]):
        """
        Inserts the new thermo docs into the thermo collection

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
            self.logger.info(f"Updating {len(docs)} thermo documents")
            self.thermo.remove_docs({self.thermo.key: {"$in": molecule_ids}})
            self.thermo.update(
                docs=docs,
                key=["molecule_id"],
            )
        else:
            self.logger.info("No items to update")
