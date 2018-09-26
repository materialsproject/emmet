
from itertools import chain
from pymatgen import Structure
from pymatgen.entries.computed_entries import ComputedStructureEntry
from emmet.vasp.task_tagger import task_type
from maggma.examples.builders import MapBuilder
from pydash.objects import get

__author__ = "Shyam Dwaraknath <shyamd@lbl.gov>"


class MLStructuresBuilder(MapBuilder):

    def __init__(self, tasks, ml_strucs, task_types= ("Structure Optimization"), **kwargs):
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
        super().__init__(source=tasks,
                         target=ml_strucs,
                         ufn=self.calc,
                         projection=["orig_inputs","input","calcs_reversed"]
                         query=query,
                         **kwargs)

    def calc(self, task):
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

        # Get some calculation properties
        is_hubbard = get(task, "input.is_hubbard", False)
        hubbards = get(task, "input.hubbards", [])
        
        # Global iterator to label entry_id's with a sub-step_id
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
