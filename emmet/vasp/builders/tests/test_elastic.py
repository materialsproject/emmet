import unittest
import os
import itertools

from emmet.vasp.builders.elastic import *
from maggma.stores import JSONStore, MemoryStore, MongoStore
from maggma.runner import Runner
from monty.json import MontyEncoder, MontyDecoder

__author__ = "Joseph Montoya"
__email__ = "montoyjh@lbl.gov"

module_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)))
test_tasks = os.path.join(module_dir, "..","..","..", "..", "test_files",
                          "elastic_tasks.json")

class ElasticBuilderTest(unittest.TestCase):
    def setUp(self):
        # Set up test db, set up mpsft, etc.
        self.test_tasks = JSONStore(test_tasks, lu_field="last_updated")
        self.test_tasks.connect()
        self.test_elasticity = MemoryStore("elasticity")

        # Generate test materials collection
        self.test_materials = MemoryStore("materials")
        opt_docs = self.test_tasks.query(
            ["structure"], {"task_label": "structure optimization"})
        for n, opt_doc in enumerate(opt_docs):
            self.materials.update({"material_id": "mp-{}".format(n),
                                   "structure": opt_doc['structure']})


    def test_builder(self):
        ec_builder = ElasticBuilder(self.test_tasks, self.test_elasticity,
                                     self.test_materials)
        ec_builder.connect()
        for t in ec_builder.get_items():
            processed = ec_builder.process_item(t)
            if processed:
                pass
        runner = Runner([ec_builder])
        runner.run()

    def test_grouping_functions(self):
        docs1 = list(self.test_tasks.query(criteria={"formula_pretty": "NaN3"}))
        docs_grouped1 = group_by_parent_lattice(docs1)
        self.assertEqual(len(docs_grouped1), 1)
        grouped_by_opt = group_deformations_by_optimization_task(docs1)
        self.assertEqual(len(grouped_by_opt), 1)

        materials_dict = generate_formula_dict(self.test_materials)
        grouped_by_mpid = group_by_material_id(materials_dict['NaN3'], docs1)
        self.assertEqual(len(grouped_by_mpid), 1)

        docs2 = self.test_tasks.query(criteria={"task_label": "elastic deformation"})
        sgroup2 = group_by_parent_lattice(docs2)

    def test_materials_aggregator(self):
        materials_dict = generate_formula_dict(self.test_materials)


if __name__ == "__main__":
    unittest.main()
