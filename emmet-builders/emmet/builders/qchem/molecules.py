from datetime import datetime
from itertools import chain, groupby
from math import ceil
from typing import Any, Dict, Iterable, Iterator, List, Optional, Set, Union

import networkx as nx

from maggma.builders import Builder
from maggma.stores import Store
from maggma.utils import grouper

from emmet.builders.settings import EmmetBuildSettings
from emmet.core.utils import get_molecule_id, group_molecules, jsanitize, make_mol_graph
from emmet.core.qchem.molecule import (
    best_lot,
    evaluate_lot,
    evaluate_task_entry,
    MoleculeDoc,
)
from emmet.core.qchem.task import TaskDocument
from emmet.core.qchem.calc_types import LevelOfTheory, CalcType, TaskType


__author__ = "Evan Spotte-Smith <ewcspottesmith@lbl.gov>"


SETTINGS = EmmetBuildSettings()


def evaluate_molecule(
    mol_doc: MoleculeDoc,
    funct_scores: Dict[str, int] = SETTINGS.QCHEM_FUNCTIONAL_QUALITY_SCORES,
    basis_scores: Dict[str, int] = SETTINGS.QCHEM_BASIS_QUALITY_SCORES,
    solvent_scores: Dict[str, int] = SETTINGS.QCHEM_SOLVENT_MODEL_QUALITY_SCORES,
):
    """
    Helper function to order optimization calcs by
    - Level of theory
    - Electronic energy

    :param mol_doc: Molecule to be evaluated
    :param funct_scores: Scores for various density functionals
    :param basis_scores: Scores for various basis sets
    :param solvent_scores: Scores for various implicit solvent models
    :return:
    """

    opt_lot = None
    for origin in mol_doc.origins:
        if origin.name == "molecule":
            opt_lot = mol_doc.levels_of_theory[origin.task_id]
            if isinstance(opt_lot, LevelOfTheory):
                opt_lot = opt_lot.value

    if opt_lot is None:
        opt_eval = [0]
    else:
        opt_eval = evaluate_lot(opt_lot, funct_scores, basis_scores, solvent_scores)

    best = best_lot(mol_doc, funct_scores, basis_scores, solvent_scores)

    best_eval = evaluate_lot(best, funct_scores, basis_scores, solvent_scores)

    return (
        -1 * int(mol_doc.deprecated),
        sum(best_eval),
        sum(opt_eval),
        mol_doc.best_entries[best]["energy"],
    )


def _optimizing_solvent(mol_doc):
    """
    Returns which solvent was used to optimize this (associated) MoleculeDoc.

    Args:
        mol_doc: MoleculeDoc

    Returns:
        solvent (str)

    """

    for origin in mol_doc.origins:
        if origin.name.startswith("molecule"):
            solvent = mol_doc.solvents[origin.task_id]
            return solvent


class MoleculesAssociationBuilder(Builder):
    """
    The MoleculesAssociationBuilder matches Q-Chem task documents by composition
    and collects tasks associated with identical structures.
    The purpose of this builder is to group calculations in preparation for the
    MoleculesBuilder.

    The process is as follows:

        1.) Find all documents with the same formula
        2.) Select only task documents for the task_types we can select properties from
        3.) Aggregate task documents based on nuclear geometry
        4.) Create a MoleculeDoc from the group of task documents
    """

    def __init__(
        self,
        tasks: Store,
        assoc: Store,
        query: Optional[Dict] = None,
        settings: Optional[EmmetBuildSettings] = None,
        **kwargs,
    ):
        """
        Args:
            tasks:  Store of task documents
            assoc: Store of associated molecules documents to prepare
            query: dictionary to limit tasks to be analyzed
            settings: EmmetSettings to use in the build process
        """

        self.tasks = tasks
        self.assoc = assoc
        self.query = query if query else dict()
        self.settings = EmmetBuildSettings.autoload(settings)
        self.kwargs = kwargs

        super().__init__(sources=[tasks], targets=[assoc], **kwargs)

    def ensure_indexes(self):
        """
        Ensures indices on the collections needed for building
        """

        # Basic search index for tasks
        self.tasks.ensure_index("task_id")
        self.tasks.ensure_index("last_updated")
        self.tasks.ensure_index("state")
        self.tasks.ensure_index("formula_alphabetical")
        self.tasks.ensure_index("smiles")
        self.tasks.ensure_index("species_hash")

        # Search index for molecules
        self.assoc.ensure_index("molecule_id")
        self.assoc.ensure_index("last_updated")
        self.assoc.ensure_index("task_ids")
        self.assoc.ensure_index("formula_alphabetical")

    def prechunk(self, number_splits: int) -> Iterable[Dict]:  # pragma: no cover
        """Prechunk the molecule builder for distributed computation"""

        temp_query = dict(self.query)
        temp_query["state"] = "successful"

        self.logger.info("Finding tasks to process")
        all_tasks = list(self.tasks.query(temp_query, [self.tasks.key, "species_hash"]))

        processed_tasks = set(self.assoc.distinct("task_ids"))
        to_process_tasks = {d[self.tasks.key] for d in all_tasks} - processed_tasks
        to_process_hashes = {
            d["species_hash"]
            for d in all_tasks
            if d[self.tasks.key] in to_process_tasks
        }

        N = ceil(len(to_process_hashes) / number_splits)

        for hash_chunk in grouper(to_process_hashes, N):
            yield {"query": {"species_hash": {"$in": list(hash_chunk)}}}

    def get_items(self) -> Iterator[List[TaskDocument]]:
        """
        Gets all items to process into molecules (and other) documents.
        This does no datetime checking; relying on on whether
        task_ids are included in the molecules Store

        Returns:
            generator or list relevant tasks and molecules to process into documents
        """

        self.logger.info("Molecule association builder started")
        self.logger.info(
            f"Allowed task types: {[task_type.value for task_type in self.settings.QCHEM_ALLOWED_TASK_TYPES]}"
        )

        self.logger.info("Setting indexes")
        self.ensure_indexes()

        # Save timestamp to mark buildtime
        self.timestamp = datetime.utcnow()

        # Get all processed tasks
        temp_query = dict(self.query)
        temp_query["state"] = "successful"

        self.logger.info("Finding tasks to process")
        all_tasks = list(self.tasks.query(temp_query, [self.tasks.key, "species_hash"]))

        processed_tasks = set(self.assoc.distinct("task_ids"))
        to_process_tasks = {d[self.tasks.key] for d in all_tasks} - processed_tasks
        to_process_hashes = {
            d["species_hash"]
            for d in all_tasks
            if d[self.tasks.key] in to_process_tasks
        }

        self.logger.info(f"Found {len(to_process_tasks)} unprocessed tasks")
        self.logger.info(f"Found {len(to_process_hashes)} unprocessed hashes")

        # Set total for builder bars to have a total
        self.total = len(to_process_hashes)

        projected_fields = [
            "last_updated",
            "task_id",
            "formula_alphabetical",
            "species_hash",
            "coord_hash",
            "smiles",
            "orig",
            "tags",
            "walltime",
            "cputime",
            "output",
            "calcs_reversed",
            "special_run_type",
            "custom_smd",
            "critic2",
        ]

        for shash in to_process_hashes:
            tasks_query = dict(temp_query)
            tasks_query["species_hash"] = shash
            tasks = list(
                self.tasks.query(criteria=tasks_query, properties=projected_fields)
            )
            to_yield = list()
            for t in tasks:
                # TODO: Validation
                # basic validation here ensures that tasks with invalid levels of
                # theory don't halt the build pipeline
                try:
                    task = TaskDocument(**t)
                    to_yield.append(task)
                except Exception as e:
                    self.logger.info(
                        f"Processing task {t['task_id']} failed with Exception - {e}"
                    )
                    continue

            yield to_yield

    def process_item(self, tasks: List[TaskDocument]) -> List[Dict]:
        """
        Process the tasks into a MoleculeDoc

        Args:
            tasks [TaskDocument] : a list of task docs

        Returns:
            [dict] : a list of new molecule docs
        """

        if len(tasks) == 0:
            return list()
        shash = tasks[0].species_hash
        task_ids = [task.task_id for task in tasks]
        self.logger.debug(f"Processing {shash} : {task_ids}")
        molecules = list()

        for group in self.filter_and_group_tasks(tasks):
            try:
                doc = MoleculeDoc.from_tasks(group)
                molecules.append(doc)
            except Exception as e:
                failed_ids = list({t_.task_id for t_ in group})
                doc = MoleculeDoc.construct_deprecated_molecule(group)
                doc.warnings.append(str(e))
                molecules.append(doc)
                self.logger.warning(
                    f"Failed making molecule for {failed_ids}."
                    f" Inserted as deprecated molecule: {doc.molecule_id}"
                )

        self.logger.debug(f"Produced {len(molecules)} molecules for {shash}")

        return jsanitize([mol.model_dump() for mol in molecules], allow_bson=True)

    def update_targets(self, items: List[List[Dict]]):
        """
        Inserts the new molecules into the molecules collection

        Args:
            items [[dict]]: A list of molecules to update
        """

        docs = list(chain.from_iterable(items))  # type: ignore

        for item in docs:
            item.update({"_bt": self.timestamp})

        molecule_ids = list({item["molecule_id"] for item in docs})

        if len(items) > 0:
            self.logger.info(f"Updating {len(docs)} molecules")
            self.assoc.remove_docs({self.assoc.key: {"$in": molecule_ids}})
            self.assoc.update(
                docs=docs,
                key=["molecule_id"],
            )
        else:
            self.logger.info("No items to update")

    def filter_and_group_tasks(
        self, tasks: List[TaskDocument]
    ) -> Iterator[List[TaskDocument]]:
        """
        Groups tasks by identical structure
        """

        filtered_tasks = [
            task
            for task in tasks
            if any(
                allowed_type is task.task_type
                for allowed_type in self.settings.QCHEM_ALLOWED_TASK_TYPES
            )
        ]

        molecules = list()

        for idx, task in enumerate(filtered_tasks):
            if task.output.optimized_molecule:
                m = task.output.optimized_molecule
            else:
                m = task.output.initial_molecule
            m.ind: int = idx  # type: ignore
            molecules.append(m)

        grouped_molecules = group_molecules(molecules)
        for group in grouped_molecules:
            grouped_tasks = [filtered_tasks[mol.ind] for mol in group]  # type: ignore
            yield grouped_tasks


class MoleculesBuilder(Builder):
    """
    The MoleculesBuilder collects MoleculeDocs from the MoleculesAssociationBuilder
    and groups them by key properties (charge, spin multiplicity, bonding).
    Then, the best molecular structure is identified (based on electronic energy),
    and this document becomes the representative MoleculeDoc.

    The process is as follows:

        1.) Find all documents with the same formula
        2.) Group documents based on charge, spin, and bonding
        3.) Create a MoleculeDoc from the group of task documents
    """

    def __init__(
        self,
        assoc: Store,
        molecules: Store,
        query: Optional[Dict] = None,
        settings: Optional[EmmetBuildSettings] = None,
        **kwargs,
    ):
        """
        Args:
            assoc:  Store of associated molecules documents, created by MoleculesAssociationBuilder
            molecules: Store of processed molecules documents
            query: dictionary to limit tasks to be analyzed
            settings: EmmetSettings to use in the build process
        """

        self.assoc = assoc
        self.molecules = molecules
        self.query = query if query else dict()
        self.settings = EmmetBuildSettings.autoload(settings)
        self.kwargs = kwargs

        super().__init__(sources=[assoc], targets=[molecules], **kwargs)

    def ensure_indexes(self):
        """
        Ensures indices on the collections needed for building
        """

        # Search index for associated molecules
        self.assoc.ensure_index("molecule_id")
        self.assoc.ensure_index("last_updated")
        self.assoc.ensure_index("task_ids")
        self.assoc.ensure_index("formula_alphabetical")

        # Search index for molecules
        self.molecules.ensure_index("molecule_id")
        self.molecules.ensure_index("last_updated")
        self.molecules.ensure_index("task_ids")
        self.molecules.ensure_index("formula_alphabetical")

    def prechunk(self, number_splits: int) -> Iterable[Dict]:  # pragma: no cover
        """Prechunk the molecule builder for distributed computation"""

        temp_query = dict(self.query)
        temp_query["deprecated"] = False

        self.logger.info("Finding documents to process")
        all_assoc = list(
            self.assoc.query(
                temp_query,
                [
                    self.assoc.key,
                    "formula_alphabetical",
                    "species_hash",
                    "charge",
                    "spin_multiplicity",
                ],
            )
        )

        # Should be using species hash, rather than coord hash, at this point
        processed_docs = set(list(self.molecules.distinct("molecule_id")))
        assoc_ids = set()

        xyz_species_id_map = dict()
        for d in all_assoc:
            this_id = "{}-{}-{}-{}".format(
                d["species_hash"],
                d["formula_alphabetical"].replace(" ", ""),
                str(int(d["charge"])).replace("-", "m"),
                str(int(d["spin_multiplicity"])),
            )
            assoc_ids.add(this_id)
            xyz_species_id_map[d[self.assoc.key]] = this_id
        to_process_docs = assoc_ids - processed_docs

        to_process_forms = {
            d["formula_alphabetical"]
            for d in all_assoc
            if xyz_species_id_map[d[self.assoc.key]] in to_process_docs
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

        self.logger.info("Molecules builder started")
        self.logger.info("Setting indexes")
        self.ensure_indexes()

        # Save timestamp to mark buildtime
        self.timestamp = datetime.utcnow()

        # Get all processed molecules
        temp_query = dict(self.query)
        temp_query["deprecated"] = False

        self.logger.info("Finding documents to process")
        all_assoc = list(
            self.assoc.query(
                temp_query,
                [
                    self.assoc.key,
                    "formula_alphabetical",
                    "species_hash",
                    "charge",
                    "spin_multiplicity",
                ],
            )
        )

        # Should be using species hash, rather than coord hash, at this point
        processed_docs = set(list(self.molecules.distinct("molecule_id")))
        assoc_ids = set()

        xyz_species_id_map = dict()
        for d in all_assoc:
            this_id = "{}-{}-{}-{}".format(
                d["species_hash"],
                d["formula_alphabetical"].replace(" ", ""),
                str(int(d["charge"])).replace("-", "m"),
                str(int(d["spin_multiplicity"])),
            )
            assoc_ids.add(this_id)
            xyz_species_id_map[d[self.assoc.key]] = this_id
        to_process_docs = assoc_ids - processed_docs

        to_process_forms = {
            d["formula_alphabetical"]
            for d in all_assoc
            if xyz_species_id_map[d[self.assoc.key]] in to_process_docs
        }

        self.logger.info(f"Found {len(to_process_docs)} unprocessed documents")
        self.logger.info(f"Found {len(to_process_forms)} unprocessed formulas")

        # Set total for builder bars to have a total
        self.total = len(to_process_forms)

        for formula in to_process_forms:
            assoc_query = dict(temp_query)
            assoc_query["formula_alphabetical"] = formula
            assoc = list(self.assoc.query(criteria=assoc_query))

            yield assoc

    def process_item(self, items: List[Dict]) -> List[Dict]:
        """
        Process the tasks into a MoleculeDoc

        Args:
            tasks List[Dict] : a list of task docs

        Returns:
            [dict] : a list of new molecule docs
        """

        assoc = [MoleculeDoc(**item) for item in items]
        formula = assoc[0].formula_alphabetical
        mol_ids = [a.molecule_id for a in assoc]
        self.logger.debug(f"Processing {formula} : {mol_ids}")

        complete_mol_docs = list()

        # This is only slightly unholy
        # Need to combine many variables of the various constituent associated docs
        # into one MoleculeDoc, where the best associated doc for each solvent is taken
        for group in self.group_mol_docs(assoc):
            # Maybe all are disconnected and therefore none get grouped?
            if len(group) == 0:
                continue

            docs_by_solvent = dict()
            mols_by_solvent = dict()
            mol_lots = dict()

            task_ids = list()
            calc_types = dict()
            task_types = dict()
            levels_of_theory = dict()
            solvents = dict()
            lot_solvents = dict()
            unique_calc_types: Set[Union[str, CalcType]] = set()
            unique_task_types: Set[Union[str, TaskType]] = set()
            unique_levels_of_theory: Set[Union[str, LevelOfTheory]] = set()
            unique_solvents: Set[str] = set()
            unique_lot_solvents: Set[str] = set()
            origins = list()
            entries = list()
            best_entries: Dict[str, Any] = dict()
            constituent_molecules = list()
            similar_molecules = list()

            base_doc: Optional[MoleculeDoc] = None

            # Grab best doc for each solvent
            # A doc is given a solvent based on how the molecule was optimized
            for solv, subgroup in groupby(
                sorted(group, key=_optimizing_solvent), key=_optimizing_solvent
            ):
                sorted_docs = sorted(subgroup, key=evaluate_molecule)
                docs_by_solvent[solv] = sorted_docs[0]
                mols_by_solvent[solv] = sorted_docs[0].molecule
                mol_lots[solv] = sorted_docs[0].levels_of_theory[
                    sorted_docs[0].origins[0].task_id
                ]
                constituent_molecules.append(sorted_docs[0].molecule_id)

                if len(sorted_docs) > 1:
                    for m in sorted_docs[1:]:
                        if m.molecule_id not in constituent_molecules:
                            similar_molecules.append(m.molecule_id)

                if base_doc is None:
                    base_doc = docs_by_solvent[solv]

            if base_doc is None:
                continue

            else:
                # Compile data on each constituent doc
                for solv, doc in docs_by_solvent.items():
                    task_ids.extend(doc.task_ids)
                    calc_types.update(doc.calc_types)
                    task_types.update(doc.task_types)
                    levels_of_theory.update(doc.levels_of_theory)
                    solvents.update(doc.solvents)
                    lot_solvents.update(doc.lot_solvents)
                    unique_calc_types = unique_calc_types.union(
                        set(doc.unique_calc_types)
                    )
                    unique_task_types = unique_task_types.union(
                        set(doc.unique_task_types)
                    )
                    unique_levels_of_theory = unique_levels_of_theory.union(
                        set(doc.unique_levels_of_theory)
                    )
                    unique_solvents = unique_solvents.union(set(doc.unique_solvents))
                    unique_lot_solvents = unique_lot_solvents.union(
                        set(doc.unique_lot_solvents)
                    )
                    origins.extend(doc.origins)
                    entries.extend(doc.entries)

                    for lot_solv, entry in doc.best_entries.items():
                        if lot_solv in best_entries:
                            current_eval = evaluate_task_entry(best_entries[lot_solv])
                            this_eval = evaluate_task_entry(entry)
                            if this_eval < current_eval:
                                best_entries[lot_solv] = entry
                        else:
                            best_entries[lot_solv] = entry

                # Assign new doc info
                base_doc.molecule_id = get_molecule_id(
                    base_doc.molecule, node_attr="specie"
                )
                base_doc.molecules = mols_by_solvent
                base_doc.molecule_levels_of_theory = mol_lots
                base_doc.task_ids = task_ids
                base_doc.calc_types = calc_types
                base_doc.task_types = task_types
                base_doc.levels_of_theory = levels_of_theory
                base_doc.solvents = solvents
                base_doc.lot_solvents = lot_solvents
                base_doc.unique_calc_types = unique_calc_types
                base_doc.unique_task_types = unique_task_types
                base_doc.unique_levels_of_theory = unique_levels_of_theory
                base_doc.unique_solvents = unique_solvents
                base_doc.unique_lot_solvents = unique_lot_solvents
                base_doc.origins = origins
                base_doc.entries = entries
                base_doc.best_entries = best_entries
                base_doc.constituent_molecules = constituent_molecules
                base_doc.similar_molecules = similar_molecules

                complete_mol_docs.append(base_doc)

        self.logger.debug(f"Produced {len(complete_mol_docs)} molecules for {formula}")

        return jsanitize(
            [mol.model_dump() for mol in complete_mol_docs], allow_bson=True
        )

    def update_targets(self, items: List[List[Dict]]):
        """
        Inserts the new molecules into the molecules collection

        Args:
            items [[dict]]: A list of molecules to update
        """

        self.logger.debug(f"Updating {len(items)} molecules")

        docs = list(chain.from_iterable(items))  # type: ignore

        # Add timestamp, add prefix to molecule id
        for item in docs:
            molid = item["molecule_id"]

            item.update({"_bt": self.timestamp})

            for entry in item["entries"]:
                entry["entry_id"] = molid

        molecule_ids = list({item["molecule_id"] for item in docs})

        if len(items) > 0:
            self.logger.info(f"Updating {len(docs)} molecules")
            self.molecules.remove_docs({self.molecules.key: {"$in": molecule_ids}})
            self.molecules.update(
                docs=docs,
                key=["molecule_id"],
            )
        else:
            self.logger.info("No items to update")

    def group_mol_docs(self, assoc: List[MoleculeDoc]) -> Iterator[List[MoleculeDoc]]:
        """
        Groups molecules by:
            - highest level of theory
            - charge
            - spin multiplicity
            - bonding (molecule graph isomorphism)
            - solvent environment used for the structure
        """

        # Molecules are already grouped by formula

        # First, group by charge, spin multiplicity
        # Then group by graph isomorphism, using OpenBabelNN + metal_edge_extender

        def charge_spin(mol_doc):
            return (mol_doc.charge, mol_doc.spin_multiplicity)

        # Group by charge and spin
        for c_s, group in groupby(sorted(assoc, key=charge_spin), key=charge_spin):
            subgroups: List[Dict[str, Any]] = list()
            for mol_doc in group:
                mol_graph = make_mol_graph(mol_doc.molecule)
                mol_hash = mol_doc.species_hash

                # Finally, group by graph isomorphism
                # When bonding is defined by OpenBabelNN + metal_edge_extender
                # Unconnected molecule graphs are discarded at this step
                # TODO: What about molecules that would be connected under a different
                # TODO: bonding scheme? For now, ¯\_(ツ)_/¯
                # TODO: MAKE ClusterBuilder FOR THIS PURPOSE
                if nx.is_connected(mol_graph.graph.to_undirected()):
                    matched = False

                    for subgroup in subgroups:
                        if mol_hash == subgroup["hash"]:
                            subgroup["mol_docs"].append(mol_doc)
                            matched = True
                            break

                    if not matched:
                        subgroups.append({"hash": mol_hash, "mol_docs": [mol_doc]})

            self.logger.debug(f"Unique hashes: {[x['hash'] for x in subgroups]}")

            for subgroup in subgroups:
                yield subgroup["mol_docs"]
