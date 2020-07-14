import os
import copy
from datetime import datetime
from itertools import chain, groupby, combinations
import numpy as np
import networkx as nx

from pymatgen import Molecule
from pymatgen.analysis.graphs import MoleculeGraph
from pymatgen.analysis.local_env import OpenBabelNN
from pymatgen.analysis.fragmenter import metal_edge_extender
from ase import Atoms
from pymatgen.io.ase import AseAtomsAdaptor
from graphdot.experimental.metric.m3 import M3
import networkx as nx
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
                 task_types=None,
                 molecules_settings=None,
                 query=None,
                 **kwargs):
        """
        Creates a molecules collection from tasks and tags

        Args:
            tasks (Store): Store of task documents
            molecules (Store): Store of molecules documents to generate
            task_types
            molecules_settings (Path): Path to settings files
            query (dict): dictionary to limit tasks to be analyzed
        """

        self.tasks = tasks
        self.molecules_settings = molecules_settings
        self.molecules = molecules
        self.task_types = task_types
        self.query = query if query else {}

        self.__settings = load_settings(self.molecules_settings, default_mol_settings)

        self.allowed_tasks = {
            t_type for d in self.__settings for t_type in d["quality_score"]
        }

        sources = [tasks]
        if self.task_types:
            sources.append(self.task_types)
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
        to_process_forms = self.tasks.distinct(
            "formula_alphabetical", {"task_id": {"$in": list(to_process_tasks)}}
        )
        self.logger.info("Found {} unprocessed tasks".format(len(to_process_tasks)))
        self.logger.info("Found {} unprocessed formulas".format(len(to_process_forms)))

        # Tasks that have been updated since we last viewed them
        update_q = dict(q)
        update_q.update(self.tasks.lu_filter(self.molecules))
        updated_forms = self.tasks.distinct("formula_alphabetical", update_q)
        self.logger.info(
            "Found {} updated systems to process".format(len(updated_forms))
        )

        forms_to_update = set(updated_forms) | set(to_process_forms)
        self.logger.info("Processing {} total systems".format(len(forms_to_update)))
        self.total = len(forms_to_update)

        if self.task_types:
            invalid_ids = set(
                self.task_types.distinct(self.task_types.key, {"is_valid": False})
            )
        else:
            invalid_ids = set()

        for formula in forms_to_update:
            tasks_q = dict(q)
            tasks_q["formula_alphabetical"] = formula
            tasks = list(self.tasks.query(criteria=tasks_q))
            for t in tasks:
                if t[self.tasks.key] in invalid_ids:
                    t["is_valid"] = False
                else:
                    t["is_valid"] = True

            yield tasks

    def process_item(self, tasks):
        """
        Process the tasks into a list of molecules

        Args:
            tasks [dict] : a list of task docs

        Returns:
            ([dict],list) : a list of new molecules docs and a list of task_ids that were processsed
        """

        formula = tasks[0]["formula_alphabetical"]
        t_ids = [t["task_id"] for t in tasks]
        self.logger.debug("Processing {} : {}".format(formula, t_ids))

        molecules = []
        grouped_tasks = self.filter_and_group_tasks(tasks)

        for group in grouped_tasks:
            mol = self.make_mol(group)
            if mol and self.valid(mol):
                self.post_process(mol)
                molecules.append(mol)

        self.logger.debug(
            "Produced {} molecules for {}".format(
                len(molecules), tasks[0]["formula_alphabetical"]
            )
        )
        return molecules

    def update_targets(self, items):
        """
        Inserts the new task_types into the task_types collection

        Args:
            items ([([dict],[int])]): A list of tuples of molecules to update and the corresponding processed task_ids
        """

        items = [i for i in filter(None, chain.from_iterable(items))]
        items = [i for i in items if self.valid(i)]

        for item in items:
            item.update({"_bt": self.timestamp})

        if len(items) > 0:
            self.logger.info("Updating {} molecules".format(len(items)))
            # self.molecules.update(docs=items, update_lu=False)
            self.molecules.update(docs=items)
        else:
            self.logger.info("No items to update")

    def make_mol(self, task_group):
        """
        Converts a group of tasks into one molecule
        """

        # Convert the task to properties and flatten
        all_props = list(
            chain.from_iterable([self.task_to_prop_list(t) for t in task_group])
        )

        mol_id = find_mol_id(all_props)

        # Sort and group based on molecules key
        sorted_props = sorted(all_props, key=lambda prop: prop["molecules_key"])
        grouped_props = groupby(sorted_props, lambda prop: prop["molecules_key"])

        # Choose the best prop for each molecules key: highest quality score and lowest energy calculation
        best_props = [find_best_prop(props) for _, props in grouped_props]

        # Add in the provenance for the properties
        origins = [
            {
                k: prop[k]
                for k in ["molecules_key", "task_type", "task_id", "last_updated"]
            }
            for prop in best_props
            if prop.get("track", False)
        ]

        # Store any bad props
        invalid_props = [
            prop["molecules_key"] for prop in best_props if not prop["is_valid"]
        ]

        # Store all the task_ids
        task_ids = list(set([t["task_id"] for t in task_group]))
        deprecated_tasks = list(
            set([t["task_id"] for t in task_group if not t.get("is_valid", True)])
        )

        # Store task_types
        task_types = {t["task_id"]: t["task_type"] for t in all_props}

        # Store environment
        if "solvent_method" in task_group[0]["orig"]["rem"]:
            if task_group[0]["orig"]["rem"]["solvent_method"] == "smd":
                if task_group[0]["orig"]["smx"]["solvent"] == "other" or task_group[0]["orig"]["smx"]["solvent"] == "custom":
                    environment = "smd_" + task_group[0]["custom_smd"]
                else:
                    environment = "smd_" + task_group[0]["orig"]["smx"]["solvent"]
            elif task_group[0]["orig"]["rem"]["solvent_method"] == "pcm":
                environment = "pcm_" + task_group[0]["orig"]["solvent"]["dielectric"]
        else:
            environment = "vac"

        mol = {
            self.molecules.last_updated_field: max([prop["last_updated"] for prop in all_props]),
            "created_at": min([prop["last_updated"] for prop in all_props]),
            "task_ids": task_ids,
            "deprecated_tasks": deprecated_tasks,
            self.molecules.key: mol_id,
            "origins": origins,
            "task_types": task_types,
            "invalid_props": invalid_props,
            "environment": environment
        }

        for prop in best_props:
            set_(mol, prop["molecules_key"], prop["value"])

        # Store molecule graph and a list of bonds
        if "molecule" in mol:
            tmp_mol = Molecule.from_dict(mol["molecule"])
            critic_bonds = mol["critic"]["processed"]["bonds"] if "critic" in mol else None
            mol_graph = make_mol_graph(tmp_mol,critic_bonds)
            mol["mol_graph"] = mol_graph.as_dict()
            bonds = []
            for bond in mol_graph.graph.edges():
                bonds.append([bond[0],bond[1]])
            edges = {(b[0], b[1]): None for b in bonds}
            assert mol_graph == MoleculeGraph.with_edges(tmp_mol,edges)
            mol["bonds"] = bonds
            mol["edges"] = edges
        else:
            mol["molecule"] = mol["initial_molecule"]

        # Store energy and enthalpy in eV and entropy in eV/K
        mol["energy"] = mol["energy_Ha"]*27.21139
        if "enthalpy_kcal/mol" in mol:
            mol["enthalpy"] = mol["enthalpy_kcal/mol"]*0.0433641
        if "entropy_cal/molK" in mol:
            mol["entropy"] = mol["entropy_cal/molK"]*0.0000433641

        # Store free energy in eV at 298 K
        if "entropy" in mol and "enthalpy" in mol:
            mol["free_energy"] = mol["energy"]+mol["enthalpy"]-298*mol["entropy"]

        return mol

    def filter_and_group_tasks(self, tasks):
        """
        Groups tasks by molecule matching
        """

        filtered_tasks = [
            t for t in tasks if task_type(t["orig"],t["output"]) in self.allowed_tasks
        ]

        molecules = []

        for idx, t in enumerate(filtered_tasks):
            if "optimized_molecule" in t["output"]:
                mol = Molecule.from_dict(t["output"]["optimized_molecule"])
            else:
                mol = Molecule.from_dict(t["output"]["initial_molecule"])
            mol.myindex = idx
            mol_dict = {"molecule": mol}
            if "critic2" in t:
                mol_dict["critic2"] = fix_C_Li_bonds(t["critic2"])
                metal_charges = set()
                for ii,site in enumerate(mol):
                    if str(site.specie) == "Li":
                        metal_charges.add(round(t["critic2"]["processed"]["charges"][ii]))
                mol_dict["metal_charges"] = metal_charges
            if "solvent_method" in t["orig"]["rem"]:
                if t["orig"]["rem"]["solvent_method"] == "smd":
                    mol_dict["env"] = "smd"
                    if t["orig"]["smx"]["solvent"] == "other" or t["orig"]["smx"]["solvent"] == "custom":
                        mol_dict["smd"] = t["custom_smd"]
                    else:
                        mol_dict["smd"] = t["orig"]["smx"]["solvent"]
                elif t["orig"]["rem"]["solvent_method"] == "pcm":
                    mol_dict["env"] = "pcm"
                    mol_dict["pcm"] = t["orig"]["solvent"]["dielectric"]
            else:
                mol_dict["env"] = "vac"
            molecules.append(mol_dict)
        grouped_molecules = group_molecules(molecules)

        for group in grouped_molecules:
            yield [filtered_tasks[mol_dict["molecule"].myindex] for mol_dict in group]

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
                    props.append(
                        {
                            "value": get(task, prop["tasks_key"]),
                            "task_type": t_type,
                            "task_id": t_id,
                            "quality_score": prop["quality_score"][t_type],
                            "accuracy_score": calc_accuracy_score(task["orig"]),
                            "track": prop.get("track", False),
                            "aggregate": prop.get("aggregate", False),
                            "last_updated": task[self.tasks.last_updated_field],
                            "energy": get(task, "output.final_energy", 0.0),
                            "molecules_key": prop["molecules_key"],
                            "is_valid": task.get("is_valid", True)
                        }
                    )
                elif not prop.get("optional", False):
                    self.logger.error(
                        "Failed getting {} for task: {}".format(prop["tasks_key"], t_id)
                    )
        return props

    def valid(self, doc):
        """
        Determines if the resulting molecule document is valid
        """
        if doc["task_id"] == None:
            return False
        elif "energy" not in doc:
            return False
        elif "molecule" not in doc:
            return False
        elif "environment" not in doc:
            return False
        elif doc["environment"][0:3] not in ["vac","pcm","smd"]:
            return False

        return True

    def post_process(self, mol):
        """
        Any extra post-processing on a molecule doc
        """
        if "molecule" in mol:
            molecule = Molecule.from_dict(mol["molecule"])
            mol.update(molecule_metadata(molecule))
        mol.update({"deprecated": False})

    def ensure_indexes(self):
        """
        Ensures indicies on the tasks and molecules collections
        """

        # Basic search index for tasks
        self.tasks.ensure_index(self.tasks.key, unique=True)
        self.tasks.ensure_index("state")
        self.tasks.ensure_index("formula_alphabetical")
        self.tasks.ensure_index(self.tasks.last_updated_field)

        # Search index for molecules
        self.molecules.ensure_index(self.molecules.key, unique=True)
        self.molecules.ensure_index("task_ids")
        self.molecules.ensure_index("formula_alphabetical")
        self.molecules.ensure_index("environment")
        self.molecules.ensure_index(self.molecules.last_updated_field)

        if self.task_types:
            self.task_types.ensure_index(self.task_types.key)
            self.task_types.ensure_index("is_valid")


def find_mol_id(props):

    # Only consider structure optimization task_ids for molecule task_id
    possible_mol_ids = [prop for prop in props if "molecule" in prop["molecules_key"]]

    # Sort task_ids by ID
    possible_mol_ids = [
        prop["task_id"]
        for prop in sorted(possible_mol_ids, key=lambda doc: ID_to_int(doc["task_id"]))
    ]

    if len(possible_mol_ids) == 0:
        return None
    else:
        return possible_mol_ids[0]


def find_best_prop(props):
    """
    Takes a list of property docs all for the same property
    1.) Sorts according to valid tasks, highest quality score and lowest energy
    2.) Checks if this is an aggregation prop and aggregates
    3.) Returns best property
    """

    # Sort for highest quality score and lowest energy
    sorted_props = sorted(
        props,
        key=lambda doc: (
            -1 * doc["is_valid"],
            -1 * doc["quality_score"],
            -1 * doc["accuracy_score"],
            doc["energy"]
        ),
    )
    if sorted_props[0].get("aggregate", False):
        vals = [prop["value"] for prop in sorted_props]
        prop = sorted_props[0]
        prop["value"] = vals
        # Can"t track an aggregated property
        prop["track"] = False
    else:
        prop = sorted_props[0]

    return prop


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
        "formula_alphabetical": comp.alphabetical_formula,
        "chemsys": "-".join(elsyms)
    }
    return meta


def group_molecules(molecules):
    """
    Groups molecules according to composition, charge, environment, connectivity, and conformation
    """

    def get_mol_key(mol_dict):
        key = mol_dict["molecule"].composition.alphabetical_formula
        key += " " + str(mol_dict["molecule"].charge)
        key += " " + mol_dict["env"]
        if mol_dict["env"] != "vac":
            key += " " + mol_dict[mol_dict["env"]]
        return key

    for mol_key, pregroup in groupby(sorted(molecules,key=get_mol_key),key=get_mol_key):
        subgroups = []
        for mol_dict in pregroup:
            critic_bonds = mol_dict["critic2"]["processed"]["bonds"] if "critic2" in mol_dict else None
            mol_graph = make_mol_graph(mol_dict["molecule"], critic_bonds)
            if nx.is_connected(mol_graph.graph.to_undirected()):
                matched = False
                for subgroup in subgroups:
                    # Separate by metal charges:
                    if "metal_charges" in mol_dict and "metal_charges" in subgroup:
                        if mol_dict["metal_charges"] == subgroup["metal_charges"]:
                            # Separate by isomorphism:
                            if mol_graph.isomorphic_to(subgroup["mol_graph"]):
                                subgroup["mol_dict_list"].append(mol_dict)
                                matched = True
                                break
                    else:
                        # Separate by isomorphism:
                        if mol_graph.isomorphic_to(subgroup["mol_graph"]):
                            subgroup["mol_dict_list"].append(mol_dict)
                            matched = True
                            break
                if not matched:
                    if "metal_charges" in mol_dict:
                        subgroups.append({"mol_graph":mol_graph,
                                          "metal_charges":mol_dict["metal_charges"],
                                          "mol_dict_list":[mol_dict]})
                    else:
                        subgroups.append({"mol_graph":mol_graph,
                                          "mol_dict_list":[mol_dict]})

        # Separate by M3:
        final_subgroups = []
        m3 = M3()
        for subgroup in subgroups:
            if len(subgroup["mol_dict_list"]) == 1:
                final_subgroups.append(subgroup)
            else:
                adj = nx.Graph()
                tmp_ids = list(range(len(subgroup["mol_dict_list"])))
                adj.add_nodes_from(tmp_ids)
                pairs = combinations(tmp_ids,2)
                for pair in pairs:
                    atoms1 = AseAtomsAdaptor.get_atoms(subgroup["mol_dict_list"][pair[0]]["molecule"])
                    atoms2 = AseAtomsAdaptor.get_atoms(subgroup["mol_dict_list"][pair[1]]["molecule"])
                    if m3(atoms1,atoms2) < 0.1:
                        adj.add_edge(pair[0],pair[1])
                subgraphs = list(nx.connected_components(adj))
                if len(subgraphs) == 1:
                    final_subgroups.append(subgroup)
                else:
                    for subgraph in subgraphs:
                        new_subgroup = {}
                        new_subgroup["mol_graph"] = subgroup["mol_graph"]
                        new_subgroup["mol_dict_list"] = [subgroup["mol_dict_list"][ind] for ind in subgraph]
                        if "metal_charges" in subgroup:
                            new_subgroup["metal_charges"] = subgroup["metal_charges"]
                        final_subgroups.append(new_subgroup)

        for subgroup in final_subgroups:
            yield subgroup["mol_dict_list"]


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

def make_mol_graph(mol, critic_bonds=None):
    mol_graph = MoleculeGraph.with_local_env_strategy(mol,
                                                      OpenBabelNN())
    mol_graph = metal_edge_extender(mol_graph)
    if critic_bonds:
        mg_edges = mol_graph.graph.edges()
        for bond in critic_bonds:
            bond.sort()
            if bond[0] != bond[1]:
                bond = (bond[0],bond[1])
                if bond not in mg_edges:
                    mol_graph.add_edge(bond[0],bond[1])
    return mol_graph

def fix_C_Li_bonds(critic):
    for key in critic["bonding"]:
        if critic["bonding"][key]["atoms"] == ["Li","C"] or critic["bonding"][key]["atoms"] == ["C","Li"]:
            if critic["bonding"][key]["field"] <= 0.02 and critic["bonding"][key]["field"] > 0.012 and critic["bonding"][key]["distance"] < 2.5:
                critic["processed"]["bonds"].append([int(entry)-1 for entry in critic["bonding"][key]["atom_ids"]])
    return critic


