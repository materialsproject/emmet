import os
import copy
from datetime import datetime
from itertools import chain, groupby
import numpy as np
import networkx as nx

from pymatgen import Molecule
from pymatgen.analysis.graphs import MoleculeGraph
from pymatgen.analysis.local_env import OpenBabelNN

from maggma.builders import Builder

from emmet.qchem.task_tagger import task_type
from emmet.common.utils import load_settings
from pydash.objects import get, set_, has

__author__ = "Sam Blau"

module_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)))


class AssociationBuilder(Builder):
    def __init__(self,
                 input_tasks,
                 output_tasks,
                 task_types=None,
                 query=None,
                 **kwargs):
        """
        Creates an output_tasks collection from input_tasks and 

        The main purpose of this builder is to associate FF Opt and Critic task docs so that
        Critic bonding information can be used by the MoleculeBuilder.

        Args:
            input_tasks (Store): Store of task documents
            output_tasks (Store): Store of task documents to generate
            task_types
            query (dict): dictionary to limit tasks to be analyzed
        """

        self.input_tasks = input_tasks
        self.output_tasks = output_tasks
        self.task_types = task_types
        self.query = query if query else {}
        self.allowed_tasks = {"SMD Frequency Flattening Optimization", "SMD Single Point", "SMD Critic"}

        sources = [input_tasks]
        if self.task_types:
            sources.append(self.task_types)
        super().__init__(sources=[input_tasks], targets=[output_tasks], **kwargs)

    def get_items(self):
        """
        Gets all items to process into molecules documents

        Returns:
            generator or list relevant tasks and molecules to process into molecules documents
        """

        self.logger.info("Association builder started")
        self.logger.info("Allowed task types: {}".format(self.allowed_tasks))

        self.logger.info("Setting indexes")
        self.ensure_indexes()

        # Save timestamp for update operation
        self.timestamp = datetime.utcnow()

        # Get all processed tasks:
        q = dict(self.query)
        q["state"] = "successful"

        self.logger.info("Finding tasks to process")
        all_tasks = set(self.input_tasks.distinct("task_id", q))
        processed_tasks = set(self.output_tasks.distinct("task_ids"))
        to_process_tasks = all_tasks - processed_tasks
        # to_process_tasks = set(self.input_tasks.distinct("task_id", q))
        to_process_forms = self.input_tasks.distinct(
            "formula_alphabetical", {"task_id": {"$in": list(to_process_tasks)}}
        )
        self.logger.info("Found {} tasks".format(len(to_process_tasks)))
        self.logger.info("Found {} formulas".format(len(to_process_forms)))

        if self.task_types:
            invalid_ids = set(
                self.task_types.distinct(self.task_types.key, {"is_valid": False})
            )
        else:
            invalid_ids = set()

        self.total = len(to_process_forms)
        for formula in to_process_forms:
            tasks_q = dict(q)
            tasks_q["formula_alphabetical"] = formula
            tasks = list(self.input_tasks.query(criteria=tasks_q))
            for t in tasks:
                if t[self.input_tasks.key] in invalid_ids:
                    t["is_valid"] = False
                else:
                    t["is_valid"] = True
            yield tasks

    def process_item(self, tasks):
        """
        Process the input_tasks into a list of output_tasks

        Args:
            tasks [dict] : a list of task docs

        Returns:
            ([dict],list) : a list of output task docs and a list of task_ids that were processsed
        """

        formula = tasks[0]["formula_alphabetical"]
        t_ids = [t["task_id"] for t in tasks]
        self.logger.debug("Processing {} : {}".format(formula, t_ids))

        output_tasks = []
        grouped_tasks = self.filter_and_group_tasks(tasks)

        for group in grouped_tasks:
            if len(group) == 1:
                output_tasks.append(group[0])
            elif len(group) == 2:
                associated_task = self.associate_tasks(group)
                if associated_task != None:
                    output_tasks.append(associated_task)
            else:
                raise RuntimeError("ERROR: groups must contain one or two tasks! Invalid group length:", len(group))

        self.logger.debug(
            "Produced {} output tasks for {}".format(
                len(output_tasks), tasks[0]["formula_alphabetical"]
            )
        )
        return output_tasks

    def update_targets(self, items):
        """
        Inserts the task docs into the output_tasks collection

        Args:
            items ([([dict],[int])]): A list of tuples of molecules to update and the corresponding processed task_ids
        """

        items = [i for i in filter(None, chain.from_iterable(items))]

        for item in items:
            item.update({"_bt": self.timestamp})

        if len(items) > 0:
            self.logger.info("Updating {} output_tasks".format(len(items)))
            self.output_tasks.update(docs=items, update_lu=False)
        else:
            self.logger.info("No items to update")

    def associate_tasks(self, task_group):
        """
        Converts a Critic task and an Opt task into one associated task
        """

        if "critic2" in task_group[0]:
            critic_task = task_group[0]
            opt_task = task_group[1]
        elif "critic2" in task_group[1]:
            critic_task = task_group[1]
            opt_task = task_group[0]
        else:
            raise RuntimeError("ERROR: There has to be a critic task! Exiting...")

        assert "special_run_type" in opt_task
        assert opt_task["special_run_type"] == "frequency_flattener"

        num_critic_scf_iters = len(critic_task["calcs_reversed"][0]["SCF"][0])
        last_critic_scf = critic_task["calcs_reversed"][0]["SCF"][0][-1][0]
        if num_critic_scf_iters > len(opt_task["calcs_reversed"][0]["SCF"][0]):
            comparable_scf = opt_task["calcs_reversed"][0]["SCF"][0][-1][0]
        else:
            comparable_scf = opt_task["calcs_reversed"][0]["SCF"][0][num_critic_scf_iters-1][0]
        if abs(last_critic_scf - comparable_scf) > 0.001:
            # Tag inconsistent tasks to be dealt with later
            critic_task["inconsistent"] = True
            opt_task["inconsistent"] = True
            critic_task["incon_pair"] = {"opt":opt_task["task_id"], "critic":critic_task["task_id"]}
            opt_task["incon_pair"] = {"opt":opt_task["task_id"], "critic":critic_task["task_id"]}
            critic_task.pop("is_valid",None)
            opt_task.pop("is_valid",None)
            self.input_tasks.connect()
            self.input_tasks.update(docs=[critic_task,opt_task], update_lu=False)
        else:
            associated_task = copy.deepcopy(opt_task)
            associated_task["critic2"] = critic_task["critic2"]
            associated_task["task_ids"] = list(set([t["task_id"] for t in task_group]))
            if "resp" not in associated_task["output"]:
                associated_task["output"]["resp"] = critic_task["output"]["resp"]

            return associated_task

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
            group_list = [filtered_tasks[mol.myindex] for mol in group]
            found = {"SP": None, "C": None, "FF": None}
            for task in group_list:
                if "special_run_type" in task:
                    if task["special_run_type"] == "frequency_flattener":
                        if not found["FF"]:
                            found["FF"] = task
                        elif task["output"]["final_energy"] < found["FF"]["output"]["final_energy"]:
                            found["FF"] = task
                if "critic2" in task:
                    if not found["C"]:
                        found["C"] = task
                    elif task["output"]["final_energy"] < found["C"]["output"]["final_energy"]:
                        found["C"] = task
                elif task["orig"]["rem"]["job_type"] == "sp":
                    if not found["SP"]:
                        found["SP"] = task
                    elif task["output"]["final_energy"] < found["SP"]["output"]["final_energy"]:
                        found["SP"] = task
            else:
                yield [found[key] for key in found if found[key]]

    def ensure_indexes(self):
        """
        Ensures indicies on the tasks and molecules collections
        """

        # Basic search index for tasks
        self.input_tasks.ensure_index(self.input_tasks.key, unique=True)
        self.input_tasks.ensure_index("state")
        self.input_tasks.ensure_index("formula_alphabetical")
        self.input_tasks.ensure_index(self.input_tasks.lu_field)

        # Search index for molecules
        self.output_tasks.ensure_index(self.output_tasks.key, unique=True)
        self.output_tasks.ensure_index("state")
        self.output_tasks.ensure_index("formula_alphabetical")
        self.output_tasks.ensure_index(self.output_tasks.lu_field)

        if self.task_types:
            self.task_types.ensure_index(self.task_types.key)
            self.task_types.ensure_index("is_valid")


def group_molecules(molecules):
    """
    Groups molecules according to composition, charge, environment, and equality
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
            mol = mol_dict["molecule"]
            matched = False
            for subgroup in subgroups:
                if mol == subgroup["mol"]:
                    subgroup["mol_list"].append(mol)
                    matched = True
                    break
            if not matched:
                subgroups.append({"mol":mol,"mol_list":[mol]})
        for group in subgroups:
            yield group["mol_list"]
