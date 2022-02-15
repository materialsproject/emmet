from datetime import datetime
from itertools import chain
from math import ceil
from typing import Dict, Iterable, Iterator, List, Optional

from maggma.builders import Builder
from maggma.stores import Store
from maggma.utils import grouper

from emmet.builders.settings import EmmetBuildSettings
from emmet.core.utils import group_molecules, jsanitize
from emmet.core.qchem.molecule import evaluate_lot, MoleculeDoc
from emmet.core.qchem.task import TaskDocument
from emmet.core.molecules.bonds import make_mol_graph


__author__ = "Evan Spotte-Smith <ewcspottesmith@lbl.gov>"


SETTINGS = EmmetBuildSettings()


def evaluate_molecule(
        mol_doc: MoleculeDoc,
        funct_scores: Dict[str, int] = SETTINGS.QCHEM_FUNCTIONAL_QUALITY_SCORES,
        basis_scores: Dict[str, int] = SETTINGS.QCHEM_BASIS_QUALITY_SCORES,
        solvent_scores: Dict[str, int] = SETTINGS.QCHEM_SOLVENT_MODEL_QUALITY_SCORES):
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

    best_lot = sorted(
        mol_doc.best_entries.keys(),
        key=lambda x: evaluate_lot(x, funct_scores, basis_scores, solvent_scores)
    )[0]

    lot_eval = evaluate_lot(best_lot, funct_scores, basis_scores, solvent_scores)

    return (
        -1 * int(mol_doc.deprecated),
        lot_eval[0],
        lot_eval[1],
        lot_eval[2],
        mol_doc.best_entries[best_lot]["energy"],
    )


class MoleculesAssociationBuilder(Builder):
    """
    The MoleculesBuilder matches Q-Chem task documents by composition
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

        super().__init__(sources=[tasks], targets=[assoc])

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
        self.assoc.ensure_index("molecule_id")
        self.assoc.ensure_index("last_updated")
        self.assoc.ensure_index("task_ids")
        self.tasks.ensure_index("formula_alphabetical")

    def prechunk(self, number_splits: int) -> Iterable[Dict]:  # pragma: no cover
        """Prechunk the molecule builder for distributed computation"""

        temp_query = dict(self.query)
        temp_query["state"] = "successful"

        self.logger.info("Finding tasks to process")
        all_tasks = list(
            self.tasks.query(temp_query, [self.tasks.key, "formula_alphabetical"])
        )

        processed_tasks = set(self.assoc.distinct("task_ids"))
        to_process_tasks = {d[self.tasks.key] for d in all_tasks} - processed_tasks
        to_process_forms = {
            d["formula_alphabetical"]
            for d in all_tasks
            if d[self.tasks.key] in to_process_tasks
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

        self.logger.info("Molecule association builder started")
        self.logger.info(
            f"Allowed task types: {[task_type.value for task_type in self.settings.QCHEM_ALLOWED_TASK_TYPES]}"
        )

        self.logger.info("Setting indexes")
        self.ensure_indexes()

        # Save timestamp to mark buildtime for material documents
        self.timestamp = datetime.utcnow()

        # Get all processed tasks:
        temp_query = dict(self.query)
        temp_query["state"] = "successful"

        self.logger.info("Finding tasks to process")
        all_tasks = list(
            self.tasks.query(temp_query, [self.tasks.key, "formula_alphabetical"])
        )

        processed_tasks = set(self.assoc.distinct("task_ids"))
        to_process_tasks = {d[self.tasks.key] for d in all_tasks} - processed_tasks
        to_process_forms = {
            d["formula_alphabetical"]
            for d in all_tasks
            if d[self.tasks.key] in to_process_tasks
        }

        self.logger.info(f"Found {len(to_process_tasks)} unprocessed tasks")
        self.logger.info(f"Found {len(to_process_forms)} unprocessed formulas")

        # Set total for builder bars to have a total
        self.total = len(to_process_forms)

        projected_fields = [
            "last_updated",
            "task_id",
            "formula_alphabetical",
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

        for formula in to_process_forms:
            tasks_query = dict(temp_query)
            tasks_query["formula_alphabetical"] = formula
            tasks = list(
                self.tasks.query(criteria=tasks_query, properties=projected_fields)
            )
            for t in tasks:
                # TODO: Validation
                t["is_valid"] = True

            yield tasks

    def process_item(self, items: List[Dict]) -> List[Dict]:
        """
        Process the tasks into a MoleculeDoc

        Args:
            tasks [dict] : a list of task docs

        Returns:
            [dict] : a list of new molecule docs
        """

        tasks = [TaskDocument(**task) for task in items]
        formula = tasks[0].formula_alphabetical
        task_ids = [task.task_id for task in tasks]
        self.logger.debug(f"Processing {formula} : {task_ids}")
        molecules = list()

        for group in self.filter_and_group_tasks(tasks):
            try:
                molecules.append(
                    MoleculeDoc.from_tasks(group)
                )
            except Exception as e:
                failed_ids = list({t_.task_id for t_ in group})
                doc = MoleculeDoc.construct_deprecated_molecule(tasks)
                doc.warnings.append(str(e))
                molecules.append(doc)
                self.logger.warn(
                    f"Failed making material for {failed_ids}."
                    f" Inserted as deprecated molecule: {doc.molecule_id}"
                )

        self.logger.debug(f"Produced {len(molecules)} materials for {formula}")

        return jsanitize([mol.dict() for mol in molecules], allow_bson=True)

    def update_targets(self, items: List[Dict]):
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
                docs=docs, key=["molecule_id"],
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
        lots = list()

        for idx, task in enumerate(filtered_tasks):
            if task.output.optimized_molecule:
                m = task.output.optimized_molecule
            else:
                m = task.output.initial_molecule
            m.index: int = idx  # type: ignore
            molecules.append(m)
            lots.append(task.level_of_theory.value)

        grouped_molecules = group_molecules(
            molecules,
            lots
        )
        for group in grouped_molecules:
            grouped_tasks = [filtered_tasks[mol.index] for mol in group]  # type: ignore
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
        prefix: Optional[str] = None,
        **kwargs,
    ):
        """
        Args:
            assoc:  Store of associated molecules documents, created by MoleculesAssociationBuilder
            molecules: Store of processed molecules documents
            query: dictionary to limit tasks to be analyzed
            settings: EmmetSettings to use in the build process
            prefix: String prefix for MPIDs of processed MoleculeDocs. For instance, for the
                Lithium-Ion Battery Electrolyte (LIBE) dataset, the prefix would be "libe".
                Default is None
        """

        self.assoc = assoc
        self.molecules = molecules
        self.query = query if query else dict()
        self.settings = EmmetBuildSettings.autoload(settings)
        self.prefix = prefix
        self.kwargs = kwargs

        super().__init__(sources=[assoc], targets=[molecules])

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
            self.assoc.query(temp_query, [self.assoc.key, "formula_alphabetical"])
        )

        # int and split manipulation necessary because of MPID prefixing done during building
        processed_docs = set([int(e.split("-")[-1]) for e in self.molecules.distinct("molecule_id")])
        to_process_docs = {d[self.assoc.key] for d in all_assoc} - processed_docs
        to_process_forms = {
            d["formula_alphabetical"]
            for d in all_assoc
            if d[self.assoc.key] in to_process_docs
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

        # Save timestamp to mark buildtime for material documents
        self.timestamp = datetime.utcnow()

        # Get all processed tasks:
        temp_query = dict(self.query)
        temp_query["deprecated"] = False

        self.logger.info("Finding documents to process")
        all_assoc = list(
            self.assoc.query(temp_query, [self.assoc.key, "formula_alphabetical"])
        )

        processed_docs = set([int(e.split("-")[-1]) for e in self.molecules.distinct("molecule_id")])
        to_process_docs = {d[self.assoc.key] for d in all_assoc} - processed_docs
        to_process_forms = {
            d["formula_alphabetical"]
            for d in all_assoc
            if d[self.assoc.key] in to_process_docs
        }

        self.logger.info(f"Found {len(to_process_docs)} unprocessed documents")
        self.logger.info(f"Found {len(to_process_forms)} unprocessed formulas")

        # Set total for builder bars to have a total
        self.total = len(to_process_forms)

        for formula in to_process_forms:
            assoc_query = dict(temp_query)
            assoc_query["formula_alphabetical"] = formula
            assoc = list(
                self.assoc.query(criteria=assoc_query)
            )

            yield assoc

    def process_item(self, items: List[Dict]) -> List[Dict]:
        """
        Process the tasks into a MoleculeDoc

        Args:
            tasks [dict] : a list of task docs

        Returns:
            [dict] : a list of new molecule docs
        """

        assoc = [MoleculeDoc(**item) for item in items]
        formula = assoc[0].formula_alphabetical
        mol_ids = [a.molecule_id for a in assoc]
        self.logger.debug(f"Processing {formula} : {mol_ids}")

        grouped_mols = self.group_molecules(assoc)
        molecules = list()

        for group in grouped_mols:
            try:
                molecules.append(
                    MoleculeDoc.from_tasks(group)
                )
            except Exception as e:
                failed_ids = list({t_.task_id for t_ in group})
                doc = MoleculeDoc.construct_deprecated_molecule(tasks)
                doc.warnings.append(str(e))
                molecules.append(doc)
                self.logger.warn(
                    f"Failed making material for {failed_ids}."
                    f" Inserted as deprecated molecule: {doc.molecule_id}"
                )

        self.logger.debug(f"Produced {len(molecules)} materials for {formula}")

        return jsanitize([mat.dict() for mat in molecules], allow_bson=True)

    def update_targets(self, items: List[Dict]):
        """
        Inserts the new molecules into the molecules collection

        Args:
            items [[dict]]: A list of molecules to update
        """

        docs = list(chain.from_iterable(items))  # type: ignore

        # Add timestamp, add prefix to molecule id
        for item in docs:
            item.update({"_bt": self.timestamp, "molecule_id": "-".join(self.prefix, str(item["molecule_id"]))})

        molecule_ids = list({item["molecule_id"] for item in docs})

        if len(items) > 0:
            self.logger.info(f"Updating {len(docs)} molecules")
            self.molecules.remove_docs({self.molecules.key: {"$in": molecule_ids}})
            self.molecules.update(
                docs=docs, key=["molecule_id"],
            )
        else:
            self.logger.info("No items to update")

    def group_mol_docs(
        self, assoc: List[MoleculeDoc]
    ) -> Iterator[List[MoleculeDoc]]:
        """
        Groups molecules by:
            - highest level of theory
            - charge
            - spin multiplicity
            - bonding (molecule graph isomorphism)
        """

        # First, group by charge, spin multiplicity, and solvent environment
        # Then group by graph isomorphism, using OpenBabelNN + metal_edge_extender
        # Then, use evaluate_molecule to select best molecule based on
        #   level of theory and electronic energy

        def form_charge_spin_solv(molecule, lot):
            lot_comp = lot.value.split("/")
            if lot_comp[2].upper == "VACUUM":
                env = "VACUUM"
            else:
                env = lot_comp[2].split("(")[1].replace(")", "")

            key = molecule.composition.alphabetical_formula
            key += " " + str(molecule.charge)
            key += " " + str(molecule.spin_multiplicity)
            key += " " + env

            return key



        for idx, doc in enumerate(assoc):
            if task.output.optimized_molecule:
                m = task.output.optimized_molecule
            else:
                m = task.output.initial_molecule
            m.index: int = idx  # type: ignore
            molecules.append(m)
            lots.append(task.level_of_theory.value)

        grouped_molecules = group_molecules(
            molecules,
            lots
        )
        for group in grouped_molecules:
            grouped_tasks = [filtered_tasks[mol.index] for mol in group]  # type: ignore
            yield grouped_tasks


def group(
        molecules: List[Molecule],
        lots: List[str]
):
    """
    Groups molecules according to composition, charge, environment, and equality

    Args:
        molecules (List[Molecule])
        lots (List[str]): string representations of Q-Chem levels of theory
    """

    def get_mol_key(mol_lot):
        molecule, lot = mol_lot
        key = molecule.composition.alphabetical_formula
        key += " " + lot
        return key

    for mol_key, pregroup in groupby(sorted(zip(molecules, lots),key=get_mol_key),key=get_mol_key):
        subgroups = list()
        for mol, _ in pregroup:
            mol_0 = copy.deepcopy(mol)
            mol_0.set_charge_and_spin(0)
            matched = False
            for subgroup in subgroups:
                if mol_0 == subgroup["mol"]:
                    subgroup["mol_list"].append(mol)
                    matched = True
                    break
            if not matched:
                subgroups.append({"mol":mol_0,"mol_list":[mol]})
        for group in subgroups:
            yield group["mol_list"]