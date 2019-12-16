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
        # print(len(self.input_tasks),"input tasks")

        # Get all processed tasks:
        q = dict(self.query)
        q["state"] = "successful"

        self.logger.info("Finding tasks to process")
        to_process_tasks = set(self.input_tasks.distinct("task_id", q))
        to_process_forms = self.input_tasks.distinct(
            "formula_alphabetical", {"task_id": {"$in": list(to_process_tasks)}}
        )
        self.logger.info("Found {} tasks".format(len(to_process_tasks)))
        print(len(to_process_tasks),"tasks to process")
        self.logger.info("Found {} formulas".format(len(to_process_forms)))

        if self.task_types:
            invalid_ids = set(
                self.task_types.distinct(self.task_types.key, {"is_valid": False})
            )
        else:
            invalid_ids = set()

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

        formula = tasks[0]["formula_pretty"]
        # print(formula)
        t_ids = [t["task_id"] for t in tasks]
        self.logger.debug("Processing {} : {}".format(formula, t_ids))

        output_tasks = []
        grouped_tasks = self.filter_and_group_tasks(tasks)

        for group in grouped_tasks:
            if len(group) == 1:
                output_tasks.append(group[0])
            elif len(group) == 2:
                associated_task = self.associate_tasks(group)
                output_tasks.append(associated_task)
            else:
                raise RuntimeError("ERROR: shouldn't ever have groups of more than two tasks! Exiting...")

        self.logger.debug(
            "Produced {} output tasks for {}".format(
                len(output_tasks), tasks[0]["formula_pretty"]
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

        associated_task = copy.deepcopy(opt_task)
        associated_task["critic2"] = critic_task["critic2"]
        associated_task["task_ids"] = list(set([t["task_id"] for t in task_group]))

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
                s = Molecule.from_dict(t["output"]["optimized_molecule"])
            else:
                s = Molecule.from_dict(t["output"]["initial_molecule"])
            s.myindex = idx
            molecules.append(s)

        grouped_molecules = group_molecules(molecules)

        for group in grouped_molecules:
            group_list = [filtered_tasks[mol.myindex] for mol in group]
            FF_found = False
            C_found = False
            new_list = []
            num_extra_FF = 0
            num_extra_C = 0
            for task in group_list:
                if "special_run_type" in task:
                    if task["special_run_type"] == "frequency_flattener":
                        if not FF_found:
                            new_list.append(task)
                            FF_found = True
                        else:
                            num_extra_FF += 1
                if "critic2" in task:
                    if not C_found:
                        new_list.append(task)
                        C_found = True
                    else:
                        num_extra_C += 1
            #             print([t["task_id"] for t in new_list])
            #             print(task["task_id"])
            # print(num_extra_FF+1,num_extra_C+1)
            # if num_extra_C > 0:
            #     print(num_extra_C,"extra Critic task(s) found")
            # if num_extra_FF > 0:
            #     print(num_extra_FF,"extra FF task(s) found")
            yield new_list


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
    Groups molecules according to composition, charge, and equality
    """

    def get_mol_key(mol):
        return mol.composition.alphabetical_formula+" "+str(mol.charge)

    for mol_key, pregroup in groupby(sorted(molecules,key=get_mol_key),key=get_mol_key):
        subgroups = []
        for mol in pregroup:
            matched = False
            for subgroup in subgroups:
                if mol == subgroup["mol"]: # This is going to need to be extended with m3 for inexact matches
                    subgroup["mol_list"].append(mol)
                    matched = True
                    break
            if not matched:
                subgroups.append({"mol":mol,"mol_list":[mol]})
        for group in subgroups:
            yield group["mol_list"]
