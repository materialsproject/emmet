from collections import defaultdict
from datetime import datetime
from itertools import chain
from math import ceil
from typing import Optional, Iterable, Iterator, List, Dict

from pymatgen.core.structure import Molecule
from pymatgen.analysis.molecule_matcher import MoleculeMatcher

from maggma.builders import Builder
from maggma.core import Store
from maggma.utils import grouper

from emmet.core.qchem.task import TaskDocument
from emmet.core.qchem.molecule import MoleculeDoc, evaluate_lot
from emmet.core.molecules.thermo import get_free_energy, MoleculeThermoDoc
from emmet.core.qchem.calc_types import TaskType
from emmet.core.utils import jsanitize
from emmet.builders.settings import EmmetBuildSettings


__author__ = "Evan Spotte-Smith"

SETTINGS = EmmetBuildSettings()

single_mol_thermo = {
    "Zn1": {"enthalpy": 1.481, "entropy": 38.384},
    "Xe1": {"enthalpy": 1.481, "entropy": 40.543},
    "Tl1": {"enthalpy": 1.481, "entropy": 41.857},
    "Ti1": {"enthalpy": 1.481, "entropy": 37.524},
    "Te1": {"enthalpy": 1.481, "entropy": 40.498},
    "Sr1": {"enthalpy": 1.481, "entropy": 39.334},
    "Sn1": {"enthalpy": 1.481, "entropy": 40.229},
    "Si1": {"enthalpy": 1.481, "entropy": 35.921},
    "Sb1": {"enthalpy": 1.481, "entropy": 40.284},
    "Se1": {"enthalpy": 1.481, "entropy": 39.05},
    "S1": {"enthalpy": 1.481, "entropy": 36.319},
    "Rn1": {"enthalpy": 1.481, "entropy": 42.095},
    "Pt1": {"enthalpy": 1.481, "entropy": 41.708},
    "Rb1": {"enthalpy": 1.481, "entropy": 39.23},
    "Po1": {"enthalpy": 1.481, "entropy": 41.915},
    "Pb1": {"enthalpy": 1.481, "entropy": 41.901},
    "P1": {"enthalpy": 1.481, "entropy": 36.224},
    "O1": {"enthalpy": 1.481, "entropy": 34.254},
    "Ne1": {"enthalpy": 1.481, "entropy": 34.919},
    "N1": {"enthalpy": 1.481, "entropy": 33.858},
    "Na1": {"enthalpy": 1.481, "entropy": 35.336},
    "Mg1": {"enthalpy": 1.481, "entropy": 35.462},
    "Li1": {"enthalpy": 1.481, "entropy": 31.798},
    "Kr1": {"enthalpy": 1.481, "entropy": 39.191},
    "K1": {"enthalpy": 1.481, "entropy": 36.908},
    "In1": {"enthalpy": 1.481, "entropy": 40.132},
    "I1": {"enthalpy": 1.481, "entropy": 40.428},
    "H1": {"enthalpy": 1.481, "entropy": 26.014},
    "He1": {"enthalpy": 1.481, "entropy": 30.125},
    "Ge1": {"enthalpy": 1.481, "entropy": 38.817},
    "Ga1": {"enthalpy": 1.481, "entropy": 38.609},
    "F1": {"enthalpy": 1.481, "entropy": 34.767},
    "Cu1": {"enthalpy": 1.481, "entropy": 38.337},
    "Cl1": {"enthalpy": 1.481, "entropy": 36.586},
    "Ca1": {"enthalpy": 1.481, "entropy": 36.984},
    "C1": {"enthalpy": 1.481, "entropy": 33.398},
    "Br1": {"enthalpy": 1.481, "entropy": 39.012},
    "Bi1": {"enthalpy": 1.481, "entropy": 41.915},
    "Be1": {"enthalpy": 1.481, "entropy": 32.544},
    "Ba1": {"enthalpy": 1.481, "entropy": 40.676},
    "B1": {"enthalpy": 1.481, "entropy": 33.141},
    "Au1": {"enthalpy": 1.481, "entropy": 41.738},
    "At1": {"enthalpy": 1.481, "entropy": 41.929},
    "As1": {"enthalpy": 1.481, "entropy": 38.857},
    "Ar1": {"enthalpy": 1.481, "entropy": 36.983},
    "Al1": {"enthalpy": 1.481, "entropy": 35.813},
    "Ag1": {"enthalpy": 1.481, "entropy": 39.917},
}


class ThermoBuilder(Builder):
    """
    The ThermoBuilder extracts the highest-quality thermodynamic data from a
    MoleculeDoc (lowest electronic energy, highest level of theory for each
    solvent available).

    This builder constructs MoleculeThermoDocs in two different ways: with and without
    single-point energy corrections.

    Before any documents are constructed, the following steps are taken:
        1. Gather MoleculeDocs by formula
        2. For each doc, identify tasks with thermodynamic information such as
            zero-point energy, enthalpy, and entropy. Collect these "documents
             including complete thermodynamics" (DICTs).
        3. Separately, collect single-point energy calculations (SPECs).
        4. Sort both sets of collected tasks (DICT and SPEC) by solvent

    The first type of doc - those without corrections - can be constructed in
    a straightforward fashion:
        5. For each solvent, grab the best DICT (where "best" is defined as the
            task generated using the highest level of theory with the lowest
            electronic energy)
        6. Convert this TaskDoc to MoleculeThermoDoc

    The second type - those involving single-point energy corrections - are
    generated differently and in a slightly more involved process:
        7. For each of the "best" DICT docs identified in step 5 above:
            7.1 For each solvent, grab the best SPEC
            7.2 Try to match each best SPEC with a matching DICT (meaning that
                the DICT and the SPEC have identical structure) where the DICT
                is calculated at a lower or the same level of theory than the
                SPEC
            7.3 Convert each DICT-SPEC combination to create a MoleculeThermoDoc

    In the case where there are multiple MoleculeThermoDocs made for a given solvent,
    the different MoleculeThermoDocs will be ranked, first by level of theory (for
    a doc made with an energy correction, the scores of the DICT and the SPEC
    levels of theory will be averaged) and then by electronic energy.
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

        super().__init__(sources=[tasks, molecules], targets=[thermo], **kwargs)
        # Uncomment in case of issue with mrun not connecting automatically to collections
        # for i in [self.tasks, self.molecules, self.thermo]:
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

        # Search index for molecules
        self.molecules.ensure_index("molecule_id")
        self.molecules.ensure_index("last_updated")
        self.molecules.ensure_index("task_ids")
        self.molecules.ensure_index("formula_alphabetical")

        # Search index for thermo
        self.thermo.ensure_index("molecule_id")
        self.thermo.ensure_index("task_id")
        self.thermo.ensure_index("solvent")
        self.thermo.ensure_index("lot_solvent")
        self.thermo.ensure_index("property_id")
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
        Process the tasks into a MoleculeThermoDoc

        Args:
            items List[dict] : a list of MoleculeDocs in dict form

        Returns:
            [dict] : a list of new thermo docs
        """

        def _add_single_atom_enthalpy_entropy(
            task: TaskDocument, doc: MoleculeThermoDoc
        ):
            initial_mol = task.output.initial_molecule
            # If single atom, try to add enthalpy and entropy
            if len(initial_mol) == 1:
                if doc.total_enthalpy is None or doc.total_entropy is None:
                    formula = initial_mol.composition.alphabetical_formula
                    if formula in single_mol_thermo:
                        vals = single_mol_thermo[formula]
                        doc.total_enthalpy = vals["enthalpy"] * 0.043363
                        doc.total_entropy = vals["entropy"] * 0.000043363
                        doc.translational_enthalpy = vals["enthalpy"] * 0.043363
                        doc.translational_entropy = vals["entropy"] * 0.000043363
                        doc.free_energy = get_free_energy(
                            doc.electronic_energy,
                            vals["enthalpy"],
                            vals["entropy"],
                            convert_energy=False,
                        )
            return doc

        mols = [MoleculeDoc(**item) for item in items]
        formula = mols[0].formula_alphabetical
        mol_ids = [m.molecule_id for m in mols]
        self.logger.debug(f"Processing {formula} : {mol_ids}")

        thermo_docs = list()

        mm = MoleculeMatcher(tolerance=0.000001)

        for mol in mols:
            this_thermo_docs = list()
            # Collect DICTs and SPECs
            thermo_entries = [
                e
                for e in mol.entries
                if e["output"]["enthalpy"] is not None
                and e["output"]["entropy"] is not None
                and e["charge"] == mol.charge
                and e["spin_multiplicity"] == mol.spin_multiplicity
            ]

            sp_entries = list()
            for entry in mol.entries:
                if isinstance(entry["task_type"], TaskType):
                    task_type = entry["task_type"].value
                else:
                    task_type = entry["task_type"]

                if (
                    task_type in ["Single Point", "Force"]
                    and entry["charge"] == mol.charge
                    and entry["spin_multiplicity"] == mol.spin_multiplicity
                ):
                    sp_entries.append(entry)

            # Group both DICTs and SPECs by solvent environment
            by_solvent_dict = defaultdict(list)
            by_solvent_spec = defaultdict(list)
            for entry in thermo_entries:
                by_solvent_dict[entry["solvent"]].append(entry)
            for entry in sp_entries:
                by_solvent_spec[entry["solvent"]].append(entry)

            if len(thermo_entries) == 0:
                without_corrections = by_solvent_spec
            else:
                without_corrections = by_solvent_dict

            # Construct without corrections
            for solvent, entries in without_corrections.items():
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
                        "formula_alphabetical": formula,
                        "orig": {"$exists": True},
                    }
                )

                if tdoc is None:
                    try:
                        tdoc = self.tasks.query_one(
                            {
                                "task_id": int(task),
                                "formula_alphabetical": formula,
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

                thermo_doc = MoleculeThermoDoc.from_task(
                    task_doc, molecule_id=mol.molecule_id, deprecated=False
                )
                thermo_doc = _add_single_atom_enthalpy_entropy(task_doc, thermo_doc)
                this_thermo_docs.append(thermo_doc)

            # Construct with corrections
            for solvent, entries in by_solvent_spec.items():
                spec_sorted = sorted(
                    entries,
                    key=lambda x: (
                        sum(evaluate_lot(x["level_of_theory"])),
                        x["energy"],
                    ),
                )

                for best_spec in spec_sorted:
                    task_spec = best_spec["task_id"]

                    matching_structures = list()
                    for entry in thermo_entries:
                        mol1 = Molecule.from_dict(entry["molecule"])
                        mol2 = Molecule.from_dict(best_spec["molecule"])
                        if (mm.fit(mol1, mol2) or mol1 == mol2) and (
                            sum(evaluate_lot(best_spec["level_of_theory"]))
                            < sum(evaluate_lot(entry["level_of_theory"]))
                        ):
                            matching_structures.append(entry)

                    if len(matching_structures) == 0:
                        continue

                    best_dict = sorted(
                        matching_structures,
                        key=lambda x: (
                            sum(evaluate_lot(x["level_of_theory"])),
                            x["energy"],
                        ),
                    )[0]
                    task_dict = best_dict["task_id"]

                    tdict = self.tasks.query_one({"task_id": task_dict})
                    if tdict is None:
                        try:
                            tdict = self.tasks.query_one({"task_id": int(task_dict)})
                        except ValueError:
                            tdict = None

                    tspec = self.tasks.query_one({"task_id": task_spec})
                    if tspec is None:
                        try:
                            tspec = self.tasks.query_one({"task_id": int(task_spec)})
                        except ValueError:
                            tspec = None

                    if tdict is None or tspec is None:
                        continue

                    task_doc_dict = TaskDocument(**tdict)
                    task_doc_spec = TaskDocument(**tspec)
                    thermo_doc = MoleculeThermoDoc.from_task(
                        task_doc_dict,
                        correction_task=task_doc_spec,
                        molecule_id=mol.molecule_id,
                        deprecated=False,
                    )
                    thermo_doc = _add_single_atom_enthalpy_entropy(
                        task_doc_dict, thermo_doc
                    )
                    this_thermo_docs.append(thermo_doc)
                    break

            docs_by_solvent = defaultdict(list)
            for doc in this_thermo_docs:
                if doc.correction_solvent is not None:
                    docs_by_solvent[doc.correction_solvent].append(doc)
                else:
                    docs_by_solvent[doc.solvent].append(doc)

            # If multiple documents exist for the same solvent, grab the best one
            for _, collection in docs_by_solvent.items():
                with_eval_e = list()
                for member in collection:
                    if member.correction_level_of_theory is None:
                        with_eval_e.append(
                            (
                                member,
                                sum(evaluate_lot(member.level_of_theory)),
                                member.electronic_energy,
                            )
                        )
                    else:
                        dict_lot = sum(evaluate_lot(member.level_of_theory))
                        spec_lot = sum(evaluate_lot(member.correction_level_of_theory))
                        with_eval_e.append(
                            (
                                member,
                                (dict_lot + spec_lot) / 2,
                                member.electronic_energy,
                            )
                        )

                thermo_docs.append(
                    sorted(with_eval_e, key=lambda x: (x[1], x[2]))[0][0]
                )

        self.logger.debug(f"Produced {len(thermo_docs)} thermo docs for {formula}")

        return jsanitize([doc.model_dump() for doc in thermo_docs], allow_bson=True)

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
                key=["molecule_id", "solvent"],
            )
        else:
            self.logger.info("No items to update")
