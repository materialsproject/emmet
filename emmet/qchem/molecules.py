import os
from datetime import datetime
from itertools import chain, groupby
import numpy as np

from pymatgen import Molecule
from pymatgen.analysis.graphs import MoleculeGraph, isomorphic
from pymatgen.analysis.local_env import OpenBabelNN

from maggma.builders import Builder

from emmet.qchem.task_tagger import task_type
from emmet.common.utils import load_settings
from pydash.objects import get, set_, has

__author__ = "Sam Blau, Shyam Dwaraknath"

module_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)))
default_mol_settings = os.path.join(module_dir, "settings", "molecules_settings.json")


class MoleculesBuilder(Builder):
    def __init__(self,
                 tasks,
                 molecules,
                 mol_prefix="",
                 molecules_settings=None,
                 query=None,
                 **kwargs):
        """
        Creates a molecules collection from tasks and tags

        Args:
            tasks (Store): Store of task documents
            molecules (Store): Store of molecules documents to generate
            mol_prefix (str): prefix for all molecules ids
            molecules_settings (Path): Path to settings files
            query (dict): dictionary to limit tasks to be analyzed
        """

        self.tasks = tasks
        self.molecules_settings = molecules_settings
        self.molecules = molecules
        self.mol_prefix = mol_prefix
        self.query = query if query else {}

        self.__settings = load_settings(self.molecules_settings, default_mol_settings)

        self.allowed_tasks = {t_type for d in self.__settings for t_type in d["quality_score"]}

        super().__init__(sources=[tasks], targets=[molecules], **kwargs)

    def get_items(self):
        """
        Gets all items to process into molecules documents

        Returns:
            generator or list relevant tasks and molecules to process into molecules documents
        """

        self.logger.info("Molecules builder started")
        self.logger.info("Allowed task types: {}".format(self.allowed_tasks))

        self.logger.info("Setting indexes")
        self.ensure_indexes()

        # Save timestamp for update operation
        self.timestamp = datetime.utcnow()

        # Get all processed tasks:
        q = dict(self.query)
        q["state"] = "successful"

        self.logger.info("Finding tasks to process")
        all_tasks = set(self.tasks.distinct("task_id", q))
        processed_tasks = set(self.molecules.distinct("task_ids"))
        to_process_tasks = all_tasks - processed_tasks
        to_process_forms = self.tasks.distinct("formula_pretty", {"task_id": {"$in": list(to_process_tasks)}})
        self.logger.info("Found {} unprocessed tasks".format(len(to_process_tasks)))
        self.logger.info("Found {} unprocessed formulas".format(len(to_process_forms)))

        # Tasks that have been updated since we last viewed them
        update_q = dict(q)
        update_q.update(self.tasks.lu_filter(self.molecules))
        updated_forms = self.tasks.distinct("formula_pretty", update_q)
        self.logger.info("Found {} updated systems to process".format(len(updated_forms)))

        forms_to_update = set(updated_forms) | set(to_process_forms)
        self.logger.info("Processing {} total systems".format(len(forms_to_update)))
        self.total = len(forms_to_update)

        for formula in forms_to_update:
            tasks_q = dict(q)
            tasks_q["formula_pretty"] = formula
            tasks = list(self.tasks.query(criteria=tasks_q))
            yield tasks

    def process_item(self, tasks):
        """
        Process the tasks into a list of molecules

        Args:
            tasks [dict] : a list of task docs

        Returns:
            ([dict],list) : a list of new molecules docs and a list of task_ids that were processsed
        """

        formula = tasks[0]["formula_pretty"]
        # print(formula)
        t_ids = [t["task_id"] for t in tasks]
        self.logger.debug("Processing {} : {}".format(formula, t_ids))

        molecules = []
        grouped_tasks = self.filter_and_group_tasks(tasks)

        for group in grouped_tasks:
            molecules.append(self.make_mol(group))

        self.logger.debug("Produced {} molecules for {}".format(len(molecules), tasks[0]["formula_pretty"]))

        return molecules

    def update_targets(self, items):
        """
        Inserts the new task_types into the task_types collection

        Args:
            items ([([dict],[int])]): A list of tuples of molecules to update and the corresponding processed task_ids
        """

        items = [i for i in filter(None, chain.from_iterable(items)) if self.valid(i)]

        for item in items:
            item.update({"_bt": self.timestamp})

        if len(items) > 0:
            self.logger.info("Updating {} molecules".format(len(items)))
            self.molecules.update(docs=items, update_lu=False)
        else:
            self.logger.info("No items to update")

    def make_mol(self, task_group):
        """
        Converts a group of tasks into one molecule
        """

        # Convert the task to properties and flatten
        all_props = list(chain.from_iterable([self.task_to_prop_list(t) for t in task_group]))

        # Figure out molecule ID
        possible_mol_ids = [prop[self.tasks.key] for prop in sorted(all_props, key=lambda x: ID_to_int(x["task_id"]))]
        mol_id = possible_mol_ids[0]

        # Sort and group based on molecules key
        sorted_props = sorted(all_props, key=lambda x: x["molecules_key"])
        grouped_props = groupby(sorted_props, lambda x: x["molecules_key"])

        # Choose the best prop for each molecules key: highest quality score and lowest energy calculation
        best_props = []
        for _, props in grouped_props:
            # Sort for highest quality score and lowest energy
            sorted_props = sorted(props, key=lambda x: (x["quality_score"], x["accuracy_score"], -1.0 * x["energy"]), reverse=True)
            if sorted_props[0].get("aggregate", False):
                vals = [prop["value"] for prop in sorted_props]
                prop = sorted_props[0]
                prop["value"] = vals
                # Can"t track an aggregated property
                prop["track"] = False
                best_props.append(prop)
            else:
                best_props.append(sorted_props[0])

        # Add in the provenance for the properties
        origins = [{k: prop[k]
                    for k in ["molecules_key", "task_type", "task_id", "last_updated"]} for prop in best_props
                   if prop.get("track", False)]

        # Store all the task_ids
        task_ids = list(set([t["task_id"] for t in task_group]))

        # Store task_types
        task_types = {t["task_id"]: t["task_type"] for t in all_props}

        mol = {
            self.molecules.lu_field: max([prop["last_updated"] for prop in all_props]),
            "created_at": min([prop["last_updated"] for prop in all_props]),
            "task_ids": task_ids,
            self.molecules.key: mol_id,
            "origins": origins,
            "task_types": task_types
        }

        for prop in best_props:
            set_(mol, prop["molecules_key"], prop["value"])

        return mol

    def filter_and_group_tasks(self, tasks):
        """
        Groups tasks by molecule matching
        """

        filtered_tasks = [t for t in tasks if task_type(t["orig"],t["output"]) in self.allowed_tasks]

        molecules = []

        for idx, t in enumerate(filtered_tasks):
            s = Molecule.from_dict(t["output"]["initial_molecule"])
            s.myindex = idx
            molecules.append(s)

        grouped_molecules = group_molecules(molecules)

        for group in grouped_molecules:
            yield [filtered_tasks[mol.myindex] for mol in group]

    def task_to_prop_list(self, task):
        """
        Converts a task into a list of properties with associated metadata
        """
        t_type = task_type(task["orig"],task["output"])
        t_id = task["task_id"]

        # Convert the task doc into a series of properties in the molecules
        # doc with the right document structure
        props = []
        for prop in self.__settings:
            if t_type in prop["quality_score"].keys():
                if has(task, prop["tasks_key"]):
                    props.append({
                        "value": get(task, prop["tasks_key"]),
                        "task_type": t_type,
                        "task_id": t_id,
                        "quality_score": prop["quality_score"][t_type],
                        "accuracy_score": calc_accuracy_score(task["orig"]),
                        "track": prop.get("track", False),
                        "aggregate": prop.get("aggregate", False),
                        "last_updated": task[self.tasks.lu_field],
                        "energy": get(task, "output.final_energy", 0.0),
                        "molecules_key": prop["molecules_key"]
                    })
                elif not prop.get("optional", False):
                    self.logger.error("Failed getting {} for task: {}".format(prop["tasks_key"], t_id))
        return props

    def valid(self, doc):
        """
        Determines if the resulting molecule document is valid
        """
        return "molecule" in doc

    def ensure_indexes(self):
        """
        Ensures indicies on the tasks and molecules collections
        """

        # Basic search index for tasks
        self.tasks.ensure_index(self.tasks.key, unique=True)
        self.tasks.ensure_index("state")
        self.tasks.ensure_index("formula_pretty")
        self.tasks.ensure_index(self.tasks.lu_field)

        # Search index for molecules
        self.molecules.ensure_index(self.molecules.key, unique=True)
        self.molecules.ensure_index("task_ids")
        self.molecules.ensure_index(self.molecules.lu_field)


def molecule_metadata(molecule):
    """
    Generates metadata based on a molecule
    """
    comp = molecule.composition
    elsyms = sorted(set([e.symbol for e in comp.elements]))
    meta = {
        "nsites": molecule.num_sites,
        "elements": elsyms,
        "nelements": len(elsyms),
        "composition": comp.as_dict(),
        "composition_reduced": comp.reduced_composition.as_dict(),
        "formula_pretty": comp.reduced_formula,
        "formula_anonymous": comp.anonymized_formula,
        "chemsys": "-".join(elsyms)
    }

    return meta


def group_molecules(molecules):
    """
    Groups molecules according to composition, charge, and connectivity
    """

    def get_mol_key(mol):
        return mol.composition.alphabetical_formula+" "+str(mol.charge)

    for mol_key, pregroup in groupby(sorted(molecules,key=get_mol_key),key=get_mol_key):
        subgroups = []
        for mol in pregroup:
            mol_graph = MoleculeGraph.with_local_env_strategy(mol,
                                                              OpenBabelNN(),
                                                              reorder=False,
                                                              extend_structure=False)
            matched = False
            for subgroup in subgroups:
                if isomorphic(mol_graph.graph,subgroup["mol_graph"].graph,True):
                    subgroup["mol_list"].append(mol)
                    matched = True
                    break
            if not matched:
                subgroups.append({"mol_graph":mol_graph,"mol_list":[mol]})
        for group in subgroups:
            yield group["mol_list"]


def ID_to_int(s_id):
    """
    Converts a string id to tuple
    falls back to assuming ID is an Int if it can't process
    Assumes string IDs are of form "[chars]-[int]" such as mp-234
    """
    if isinstance(s_id, str):
        return (s_id.split("-")[0], int(str(s_id).split("-")[-1]))
    elif isinstance(s_id, (int, float)):
        return s_id
    else:
        raise Exception("Could not parse {} into a number".format(s_id))

def calc_accuracy_score(inputs):
    accuracy_score = 0

    # Basis:
    if "6-31" in inputs["rem"]["basis"]:
        accuracy_score += inputs["rem"]["basis"].count("1")
        accuracy_score += inputs["rem"]["basis"].count("+")
        accuracy_score += inputs["rem"]["basis"].count("*")
        accuracy_score += inputs["rem"]["basis"].count("d")
        accuracy_score += inputs["rem"]["basis"].count("p")
    elif "def2-tzv" in inputs["rem"]["basis"]:
        accuracy_score += 3
        accuracy_score += inputs["rem"]["basis"].count("p")
        accuracy_score += inputs["rem"]["basis"].count("d")
    else:
        raise Exception("Basis " + inputs["rem"]["basis"] + " cannot be assigned an accuracy score")

    # Method:
    score4_functionals = ["wb97xd","wb97x-d","cam-b3lyp","lrc-wpbe"]
    if inputs["rem"]["method"] == "pbe":
        accuracy_score += 1
    elif inputs["rem"]["method"] == "b3lyp" or inputs["rem"]["method"] == "pbe0":
        accuracy_score += 2
    elif inputs["rem"]["method"] == "m06-2x":
        accuracy_score += 3
    elif inputs["rem"]["method"] in score4_functionals:
        accuracy_score += 4
    elif inputs["rem"]["method"] == "wb97xv" or inputs["rem"]["method"] == "wb97x-v":
        accuracy_score += 5
    elif inputs["rem"]["method"] == "wb97mv" or inputs["rem"]["method"] == "wb97m-v":
        accuracy_score += 6
    elif inputs["rem"]["method"] == "mp2":
        accuracy_score += 7
    elif "ccsd" in inputs["rem"]["method"]:
        accuracy_score += 8
    else:
        raise Exception("Method " + inputs["rem"]["method"] + " cannot be assigned an accuracy score")

    return accuracy_score

