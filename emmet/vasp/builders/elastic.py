import numpy as np
from datetime import datetime
from itertools import chain

from monty.json import jsanitize

from pymatgen import Structure
from pymatgen.analysis.elasticity.elastic import ElasticTensor
from pymatgen.analysis.elasticity.strain import Strain, Deformation
from pymatgen.analysis.elasticity.stress import Stress
from pymatgen.analysis.structure_matcher import StructureMatcher, ElementComparator

from maggma.builder import Builder

from emmet.vasp.builders.task_tagger import TaskTagger

__author__ = "Shyam Dwaraknath <shyamd@lbl.gov>"


class ElasticBuilder(Builder):
    def __init__(self, tasks, elasticity, query={}, **kwargs):
        """
        Creates a elastic collection for materials

        Args:
            tasks (Store): Store of task documents
            elastic (Store): Store of elastic properties
            query (dict): dictionary to limit materials to be analyzed
        """

        self.tasks = tasks
        self.elasticity = elasticity
        self.query = query
        self.kwargs = kwargs

        super().__init__(sources=[tasks],
                         targets=[elasticity],
                         **kwargs)

    def get_items(self):
        """
        Gets all items to process into materials documents

        Returns:
            generator or list relevant tasks and materials to process into materials documents
        """

        self.logger.info("Elastic Builder Started")

        # Get only successfull tasks
        q = dict(self.query)
        q["state"] = "successful"

        # only consider tasks that have been updated since materials was last updated
        q.update(self.tasks.lu_filter(self.elasticity))

        tasks_to_update = self.tasks().find(q, {"formula_pretty": 1}).count()
        self.logger.info("Found {} new/updated tasks to process".format(tasks_to_update))

        formulas_reduced = self.tasks().find(q).distinct("formula_pretty")

        for formula in formulas_reduced:
            tasks_q = dict(q)
            tasks_q["formula_pretty"] = formula
            tasks = list(self.tasks().find(tasks_q))

            self.logger.debug("Processing {} : {}".format(formula, len(tasks)))
            yield tasks

    def process_item(self, item):
        """
        Process the tasks and materials into a dielectrics collection

        Args:
            item dict: a dict of material_id, structure, and tasks

        Returns:
            dict: a dieletrics dictionary
        """
        root_tasks = [task for task in item if "optimization" in TaskTagger.task_type(task)]
        deform_tasks = [task for task in item if "deformation" in TaskTagger.task_type(task)]
        docs = []

        # TODO: What structure matcher parameters to use?
        # TODO: Should SM parameters be configurable?
        sm = StructureMatcher(ltol=0.001, stol=0.001, angle_tol=0.1,
                              primitive_cell=False, scale=False,
                              attempt_supercell=False, allow_subset=False,
                              comparator=ElementComparator())

        self.logger.debug("Found {} root tasks and {} deformation tasks".format(len(root_tasks), len(deform_tasks)))
        for r_task in root_tasks:

            # Enumerate over all deformations
            r_struc = Structure.from_dict(r_task['output']['structure'])

            deformations = []
            stresses = []
            strains = []
            task_ids = []

            for d_task in deform_tasks:
                if d_task["calcs_reversed"][0]['input']['kpoints'] != r_task["calcs_reversed"][0]['input']['kpoints']:
                    pass
                # Find deformation matrix
                d_struc = Structure.from_dict(d_task['input']["structure"])
                transform_matrix = np.transpose(np.linalg.solve(r_struc.lattice.matrix,
                                                                d_struc.lattice.matrix))
                # apply deformation matrix to root_mat and check if the two structures match
                dfm = Deformation(transform_matrix)
                dfm_struc = dfm.apply_to_structure(r_struc)

                # if match store stress and strain matrix
                if sm.fit(dfm_struc, d_struc):
                    # This is a deformtion of the root struc
                    deformations.append(dfm)
                    stresses.append(-0.1 * Stress(d_task["calcs_reversed"][0] \
                                                      ["output"]["ionic_steps"][-1]["stress"]))
                    strains.append(dfm.green_lagrange_strain)
                    task_ids.append(d_task['task_id'])

            self.logger.info("Analyzing stress/strain data for {} tasks".format(len(task_ids)))
            # Determine if we have 6 unique deformations
            if np.linalg.matrix_rank(np.array([s.voigt for s in strains])) == 6:
                # Perform Elastic tensor fitting and analysis
                pk_stresses = [stress.piola_kirchoff_2(deformation)
                               for stress, deformation in zip(stresses, deformations)]
                result = ElasticTensor.from_pseudoinverse(strains, pk_stresses)

                d = {"material_id": r_task["task_id"],
                     "elasticity": {
                         "elastic_tensor": result.voigt.tolist(),
                         "task_ids": task_ids}
                     }
                d['elasticity'].update({'fitting_data': {'strains': strains, 'pk_stresses': pk_stresses,
                                                         'deformations': deformations}})

                d["elasticity"].update(result.property_dict)

                docs.append(d)
            else:
                self.logger.warning("Only found {} unique deformations, 6 needed for {}".format(
                    np.linalg.matrix_rank(np.array([s.voigt for s in strains])),
                    r_task["task_id"]))

        return docs

    def update_targets(self, items):
        """
        Inserts the new task_types into the task_types collection

        Args:
            items ([([dict],[int])]): A list of tuples of materials to update and the corresponding processed task_ids
        """
        self.logger.info("Updating {} elastic documents".format(len(items)))

        for doc in chain(*items):
            doc[self.elasticity.lu_field] = datetime.utcnow()
            doc = jsanitize(doc)
            self.elasticity().replace_one({"material_id": doc['material_id']}, doc, upsert=True)
