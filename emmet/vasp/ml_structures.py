from itertools import chain
from pymatgen import Structure
from pymatgen.entries.computed_entries import ComputedStructureEntry
from emmet.vasp.task_tagger import task_type
from maggma.builders import Builder
from pydash.objects import get

__author__ = "Shyam Dwaraknath <shyamd@lbl.gov>"


class MLStructuresBuilder(Builder):

    def __init__(self, tasks, ml_strucs, task_types= ("Structure Optimization",),query=None, **kwargs):
        """
        Creates a collection of structures, energies, forces, and stresses for machine learning efforts
        Args:
            tasks (Store): Store of task documents
            ml_strucs (Store): Store of materials documents to generate
            tasK_types (list): list of substrings for task_types to process
        """

        self.tasks = tasks
        self.ml_strucs = ml_strucs
        self.task_types = task_types
        self.query = query if query else None
        super().__init__(sources=[tasks],
                         targets=[ml_strucs],
                         **kwargs)

    def get_items(self):
        """
        Gets all items to process into materials documents
        Returns:
            generator or list relevant tasks and materials to process into materials documents
        """

        self.logger.info("Machine Learning Structure Database Builder Started")
        self.logger.info("Setting indexes")
        self.ensure_indexes()

        # Get all processed tasks:
        q = dict(self.query)
        q["state"] = "successful"
        q["calcs_reversed"] = {"$exists": 1}

        all_tasks = set(self.tasks.distinct("task_id", q))
        processed_tasks = set(self.ml_strucs.distinct("task_id"))
        to_process_tasks = all_tasks - processed_tasks

        self.logger.info(
            "Found {} tasks to extract information from".format(len(to_process_tasks)))
        self.total = len(to_process_tasks)

        for t_id in to_process_tasks:
            task = self.tasks.query_one(properties=["task_id","orig_inputs","calcs_reversed"],criteria={"task_id": t_id})
            yield task

    def process_item(self, task):
        """
        Process the tasks into a list of materials
        Args:
            task [dict] : a task doc
        Returns:
            list of C
        """

        t_type = task_type(get(task, 'orig_inputs'))
        entries = []

        if not any([t in t_type for t in self.task_types]):
            return []

        is_hubbard = get(task, "input.is_hubbard", False)
        hubbards = get(task, "input.hubbards", [])
        i = 0

        for calc in task.get("calcs_reversed", []):

            parameters = {"is_hubbard": is_hubbard,
                          "hubbards": hubbards,
                          "potcar_spec": get(calc, "input.potcar_spec", []),
                          "run_type": calc.get("run_type", "GGA")
                          }

            for step_num, step in enumerate(get(calc, "output.ionic_steps")):
                struc = Structure.from_dict(step.get("structure"))
                forces = calc.get("forces", [])
                if forces:
                    struc.add_site_property("forces", forces)
                stress = calc.get("stress", None)
                data = {"stress": stress} if stress else {}
                data["step"] =step_num
                c = ComputedStructureEntry(structure=struc,
                                           correction=0,
                                           energy=step.get("e_wo_entrp"),
                                           parameters=parameters,
                                           entry_id="{}-{}".format(task[self.tasks.key],i),
                                           data=data)
                i += 1

                d = c.as_dict()
                d["chemsys"] = '-'.join(
                    sorted(set([e.symbol for e in struc.composition.elements])))
                d["task_type"] = task_type(get(calc, 'input'))
                d["calc_name"] = get(calc, "task.name")
                d["task_id"] = task[self.tasks.key]

                entries.append(d)

        return entries

    def update_targets(self, items):
        """
        Inserts the new entires into the task_types collection
        Args:
            items ([([dict],[int])]): A list of tuples of materials to update and the corresponding processed task_ids
        """
        items = [i for i in filter(None, chain.from_iterable(items))]

        if len(items) > 0:
            self.logger.info("Updating {} entries".format(len(items)))
            self.ml_strucs.update(docs=items)
        else:
            self.logger.info("No items to update")

    def ensure_indexes(self):
        """
        Ensures indexes on the tasks and materials collections
        :return:
        """

        # Basic search index for tasks
        self.ml_strucs.ensure_index("entry_id")
        self.ml_strucs.ensure_index("chemsys")
        self.ml_strucs.ensure_index(self.ml_strucs.lu_field)
