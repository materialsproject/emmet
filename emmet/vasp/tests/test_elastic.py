import unittest
import os

from emmet.vasp.elastic import *
from maggma.stores import MongoStore
from maggma.runner import Runner

from monty.serialization import loadfn

__author__ = "Joseph Montoya"
__email__ = "montoyjh@lbl.gov"

module_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)))
test_tasks = os.path.join(module_dir, "..", "..", "..", "test_files", "vasp", "elastic_tasks.json")


class ElasticBuilderTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Set up test db, set up mpsft, etc.
        cls.test_tasks = MongoStore("test_emmet", "tasks")
        cls.test_tasks.connect()
        docs = loadfn(test_tasks, cls=None)
        cls.test_tasks.update(docs)
        cls.test_elasticity = MongoStore("test_emmet", "elasticity")

        # Generate test materials collection
        cls.test_materials = MongoStore("test_emmet", "materials")
        cls.test_materials.connect()
        cls.test_materials.collection.drop()
        opt_docs = cls.test_tasks.query(["output.structure", "formula_pretty"], {
            "task_label": "structure optimization"
        })
        mat_docs = [{
            "task_id": "mp-{}".format(n),
            "structure": opt_doc['output']['structure'],
            "pretty_formula": opt_doc['formula_pretty']
        } for n, opt_doc in enumerate(opt_docs)]
        cls.test_materials.update(mat_docs, update_lu=False)

    @classmethod
    def tearDownClass(cls):
        cls.test_tasks.collection.drop()
        cls.test_elasticity.collection.drop()
        cls.test_materials.collection.drop()

    def test_builder(self):
        ec_builder = ElasticBuilder(self.test_tasks, self.test_elasticity, self.test_materials, incremental=False)
        ec_builder.connect()
        for t in ec_builder.get_items():
            processed = ec_builder.process_item(t)
            self.assertTrue(bool(processed))
        runner = Runner([ec_builder])
        runner.run()
        # Test warnings
        doc = ec_builder.elasticity.query_one(criteria={"pretty_formula": "NaN3"})
        self.assertEqual(doc['elasticity']['warnings'], None)

    def test_grouping_functions(self):
        docs1 = list(self.test_tasks.query(criteria={"formula_pretty": "NaN3"}))
        docs_grouped1 = group_by_parent_lattice(docs1)
        self.assertEqual(len(docs_grouped1), 1)
        grouped_by_opt = group_deformations_by_optimization_task(docs1)
        self.assertEqual(len(grouped_by_opt), 1)

        materials_dict = generate_formula_dict(self.test_materials)
        grouped_by_mpid = group_by_task_id(materials_dict['NaN3'], docs1)
        self.assertEqual(len(grouped_by_mpid), 1)

        docs2 = self.test_tasks.query(criteria={"task_label": "elastic deformation"})
        sgroup2 = group_by_parent_lattice(docs2)

    def test_materials_aggregator(self):
        materials_dict = generate_formula_dict(self.test_materials)



if __name__ == "__main__":
    unittest.main()
