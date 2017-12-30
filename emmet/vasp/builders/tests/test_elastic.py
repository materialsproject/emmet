import unittest
import os

from emmet.vasp.builders.elastic import *
from maggma.stores import JSONStore, MemoryStore, MongoStore
from maggma.runner import Runner
from monty.json import MontyEncoder, MontyDecoder

__author__ = "Joseph Montoya"
__email__ = "montoyjh@lbl.gov"

module_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)))
test_tasks = os.path.join(module_dir, "..","..","..", "..", "test_files", "elastic_tasks.json")

class ElasticBuilderTest(unittest.TestCase):
    def setUp(self):
        # Set up test db, set up mpsft, etc.
        me, md = MontyEncoder(), MontyDecoder()
        self.test_tasks = JSONStore(test_tasks, lu_field="last_updated",
                                    lu_key=(me.encode, md.decode))
        self.elasticity = MemoryStore("elasticity")
        self.local_tasks = MongoStore(database="test_emmet",
                                      collection_name="test_atomate_tasks")
        self.local_elasticity = MongoStore(database="test_emmet",
                                           collection_name="test_elasticity")
        self.local_materials = MongoStore(database="test_emmet",
                                          collection_name="test_materials")
        self.local_materials.connect()
        self.local_tasks.connect()

    def test_builder(self):
        """
        ec_builder = ElasticBuilder(self.test_tasks, self.elasticity)
        for t in ec_builder.get_items():
            processed = ec_builder.process_item(t)
            if processed:
                pass
                """
        ec_builder2 = ElasticBuilder(self.local_tasks, self.local_elasticity,
                                     self.local_materials, incremental=False)
        ec_builder2.connect()
        items = list(ec_builder2.get_items())
        for t in items[:5]:
            processed = ec_builder2.process_item(t)
            if processed:
                pass
        runner = Runner([ec_builder2])
        runner.run()

    def test_grouping_functions(self):
        # TODO: should add some tests beyond "does it work"
        docs1 = list(self.local_tasks.query(criteria={"formula_pretty": "NaN3"}))
        docs_grouped1 = group_by_parent_lattice(docs1)
        self.assertEqual(len(docs_grouped1), 1)
        grouped_by_opt = group_deformations_by_optimization_task(docs1)
        self.assertEqual(len(grouped_by_opt), 1)

        materials_dict = generate_formula_dict(self.local_materials)
        grouped_by_mpid = group_by_material_id(materials_dict['NaN3'], docs1)
        self.assertEqual(len(grouped_by_mpid), 1)

        docs2 = self.local_tasks.query(criteria={"task_label": "elastic deformation"})
        sgroup2 = group_by_parent_lattice(docs2)
        # import nose; nose.tools.set_trace()

    def test_materials_aggregator(self):
        materials_dict = generate_formula_dict(self.local_materials)


if __name__ == "__main__":
    unittest.main()
