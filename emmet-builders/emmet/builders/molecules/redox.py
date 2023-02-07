from collections import defaultdict
import copy
from datetime import datetime
from itertools import chain, groupby
from math import ceil
from typing import Any, Dict, Iterable, Iterator, List, Optional, Union

from pymatgen.analysis.graphs import MoleculeGraph
from pymatgen.analysis.local_env import OpenBabelNN

from maggma.builders import Builder
from maggma.core import Store
from maggma.utils import grouper

from emmet.core.qchem.task import TaskDocument
from emmet.core.qchem.molecule import MoleculeDoc
from emmet.core.molecules.bonds import metals
from emmet.core.molecules.thermo import ThermoDoc
from emmet.core.molecules.redox import RedoxDoc
from emmet.core.utils import confirm_molecule, jsanitize
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
        2. Further group based on (covalent) isomorphism and charge
        3. For each MoleculeDoc:
            3a. Identify relevant ThermoDocs
            3b. Look for single-point energy calculations conducted at the
            molecule's charge +- 1. These will be used to calculation
            vertical electron affinities and ionization energies
            3c. Group ThermoDocs and single-point calculations based on solvent
            and level of theory
        4. Construct RedoxDocs by looking for molecules (with associated
            calculations) that:
            - Have charges that differ by +- 1
            - Use the same solvent and level of theory
    """

    def __init__(
        self,
        tasks: Store,
        molecules: Store,
        thermo: Store,
        redox: Store,
        query: Optional[Dict] = None,
        settings: Optional[EmmetBuildSettings] = None,
        **kwargs,
    ):

        self.tasks = tasks
        self.molecules = molecules
        self.thermo = thermo
        self.redox = redox
        self.query = query if query else dict()
        self.settings = EmmetBuildSettings.autoload(settings)
        self.kwargs = kwargs

        super().__init__(sources=[tasks, molecules, thermo], targets=[redox])

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

        # Search index for orbitals
        self.redox.ensure_index("molecule_id")
        self.redox.ensure_index("task_id")
        self.redox.ensure_index("solvent")
        self.redox.ensure_index("lot_solvent")
        self.redox.ensure_index("property_id")
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
        Gets all items to process into redox documents.
        This does no datetime checking; relying on on whether
        task_ids are included in the orbitals Store

        Returns:
            generator or list relevant tasks and molecules to process into documents
        """

        self.logger.info("Redox builder started")
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
        Process the tasks into a RedoxDoc

        Args:
            tasks List[Dict] : a list of MoleculeDocs in dict form

        Returns:
            [dict] : a list of new redox docs
        """

        mols = [MoleculeDoc(**item) for item in items]
        formula = mols[0].formula_alphabetical
        mol_ids = [m.molecule_id for m in mols]
        self.logger.debug(f"Processing {formula} : {mol_ids}")

        redox_docs = list()

        # Group by (covalent) molecular graph connectivity
        group_by_graph = self._group_by_graph(mols)

        for graph_group in group_by_graph.values():
            # Molecule docs will be grouped by charge
            charges: Dict[int, Any] = dict()

            for gg in graph_group:
                # First, grab relevant ThermoDocs and identify possible IE/EA single-points
                thermo_docs = [ThermoDoc(**e) for e in self.thermo.query({"molecule_id": gg.molecule_id})]

                if len(thermo_docs) == 0:
                    # Current building scheme requires a ThermoDoc
                    continue

                ie_sp_task_ids = [
                    int(e["task_id"]) for e in gg.entries
                    if e["charge"] == gg.charge + 1
                    and e["task_type"] == "Single Point"
                    and e["output"].get("final_energy")
                ]
                ie_tasks = [TaskDocument(**e) for e in self.tasks.query({"task_id": {"$in": ie_sp_task_ids},
                                                                         "formula_alphabetical": formula,
                                                                         "orig": {"$exists": True}
                                                                         })]

                ea_sp_task_ids = [
                    int(e["task_id"]) for e in gg.entries
                    if e["charge"] == gg.charge - 1
                    and e["task_type"] == "Single Point"
                    and e["output"].get("final_energy")
                ]
                ea_tasks = [TaskDocument(**e) for e in self.tasks.query({"task_id": {"$in": ea_sp_task_ids},
                                                                         "formula_alphabetical": formula,
                                                                         "orig": {"$exists": True}
                                                                         })]

                grouped_docs = self._collect_by_lot_solvent(thermo_docs, ie_tasks, ea_tasks)
                if gg.charge in charges:
                    charges[gg.charge].append((gg, grouped_docs))
                else:
                    charges[gg.charge] = [(gg, grouped_docs)]

            for charge, collection in charges.items():
                for mol, docs in collection:
                    # Get all possible molecules for adiabatic oxidation and reduction
                    red_coll = charges.get(charge - 1, list())
                    ox_coll = charges.get(charge + 1, list())

                    for lot_solv, docset in docs.items():
                        # Collect other molecules that have ThermoDocs at the
                        # exact same level of theory

                        combined = docset["thermo_doc"].combined_lot_solvent

                        relevant_red = list()
                        relevant_ox = list()

                        for rmol, rdocs in red_coll:
                            if lot_solv in rdocs:
                                if rdocs[lot_solv]["thermo_doc"].combined_lot_solvent == combined:
                                    relevant_red.append(rdocs[lot_solv])

                        for omol, odocs in ox_coll:
                            if lot_solv in odocs:
                                if odocs[lot_solv]["thermo_doc"].combined_lot_solvent == combined:
                                    relevant_ox.append(odocs[lot_solv])

                        # Take best options (based on electronic energy), where available
                        if len(relevant_red) == 0:
                            red_doc = None
                        else:
                            red_doc = sorted(
                                relevant_red,
                                key=lambda x: x["thermo_doc"].electronic_energy
                            )[0]["thermo_doc"]

                        if len(relevant_ox) == 0:
                            ox_doc = None
                        else:
                            ox_doc = sorted(
                                relevant_ox,
                                key=lambda x: x["thermo_doc"].electronic_energy
                            )[0]["thermo_doc"]

                        ea_doc = docset.get("ea_doc")
                        ie_doc = docset.get("ie_doc")

                        redox_docs.append(
                            RedoxDoc.from_docs(
                                base_molecule_doc=mol,
                                base_thermo_doc=docset["thermo_doc"],
                                red_doc=red_doc,
                                ox_doc=ox_doc,
                                ea_doc=ea_doc,
                                ie_doc=ie_doc
                            )
                        )

        self.logger.debug(f"Produced {len(redox_docs)} redox docs for {formula}")

        return jsanitize([doc.dict() for doc in redox_docs if doc is not None], allow_bson=True)

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

    @staticmethod
    def _group_by_graph(mol_docs: List[MoleculeDoc]) -> Dict[int, List[MoleculeDoc]]:
        """
        Group molecule docs by molecular graph connectivity

        :param entries: List of entries (dicts derived from TaskDocuments)
        :return: Grouped molecule entries
        """

        mol_graphs_nometal: List[MoleculeGraph] = list()
        results = defaultdict(list)

        # Within each group, group by the covalent molecular graph
        for t in mol_docs:
            mol = confirm_molecule(t.molecule)

            mol_nometal = copy.deepcopy(mol)

            if mol.composition.alphabetical_formula not in [m + "1" for m in metals]:
                mol_nometal.remove_species(metals)

            mol_nometal.set_charge_and_spin(0)
            mg_nometal = MoleculeGraph.with_local_env_strategy(
                mol_nometal, OpenBabelNN()
            )

            match = None
            for i, mg in enumerate(mol_graphs_nometal):
                if mg_nometal.isomorphic_to(mg):
                    match = i
                    break

            if match is None:
                results[len(mol_graphs_nometal)].append(t)
                mol_graphs_nometal.append(mg_nometal)
            else:
                results[match].append(t)

        return results

    @staticmethod
    def _collect_by_lot_solvent(thermo_docs: List[ThermoDoc],
                                ie_docs: List[TaskDocument],
                                ea_docs: List[TaskDocument]) -> Dict[str, Any]:
        """
        For a given MoleculeDoc, group potential ThermoDocs and TaskDocs for
        IE/EA calculations based on level of theory and solvent.

        Args:
            thermo_docs (list of ThermoDocs): List of ThermoDocs for this MoleculeDoc
            ie_docs (list of TaskDocuments): List of TaskDocs which could be used
                to calculate vertical ionization energies for this MoleculeDoc
            ea_docs (list of TaskDocuments): List of TaskDocs which could be used
                to calculate vertical electron affinities for this MoleculeDoc:

        Returns:
            dict {<lot_solvent>: {
                        "thermo_doc": ThermoDoc, "ie_doc": TaskDocument, "ea_doc": TaskDocument
                    }
                 }
        """

        def _lot_solv(doc: Union[ThermoDoc, TaskDocument]):
            if isinstance(doc, ThermoDoc):
                if doc.correction:
                    return doc.correction_lot_solvent
            return doc.lot_solvent

        thermo_grouped = groupby(
            sorted(thermo_docs, key=_lot_solv), key=_lot_solv
        )
        ie_grouped = groupby(
            sorted(ie_docs, key=_lot_solv), key=_lot_solv
        )
        ea_grouped = groupby(
            sorted(ea_docs, key=_lot_solv), key=_lot_solv
        )

        groups = dict()

        for k, g in thermo_grouped:
            g_list = list(g)

            # Should never be more than one ThermoDoc per MoleculeDoc
            # Just for safety...
            if len(g_list) > 1:
                g_list_sorted = sorted(g_list, key=lambda x: x.electronic_energy)
                this_thermo_doc = g_list_sorted[0]
            else:
                this_thermo_doc = g_list[0]

            groups[k] = {"thermo_doc": this_thermo_doc}

        for k, g in ie_grouped:
            # Must be a ThermoDoc to make a RedoxDoc
            if k not in groups:
                continue

            this_ie_doc = sorted(list(g), key=lambda x: x.output.final_energy)[0]
            groups[k]["ie_doc"] = this_ie_doc

        for k, g in ea_grouped:
            # Must be a ThermoDoc to make a RedoxDoc
            if k not in groups:
                continue

            this_ea_doc = sorted(list(g), key=lambda x: x.output.final_energy)[0]
            groups[k]["ea_doc"] = this_ea_doc

        return groups
