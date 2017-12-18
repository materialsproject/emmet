import unittest
import os

from emmet.vasp.builders.elastic import ElasticBuilder, group_by_structure
from maggma.stores import JSONStore, MemoryStore, MongoStore
from maggma.runner import Runner
from monty.json import MontyEncoder, MontyDecoder
from pymatgen.analysis.structure_matcher import StructureMatcher

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
        self.local_tasks.connect()
        self.test_tasks.connect()
        self.elasticity.connect()

    def test_builder(self):
        """
        ec_builder = ElasticBuilder(self.test_tasks, self.elasticity)
        for t in ec_builder.get_items():
            processed = ec_builder.process_item(t)
            if processed:
                pass
                """
        ec_builder2 = ElasticBuilder(self.local_tasks, self.local_elasticity)
        items = list(ec_builder2.get_items())
        for t in items[:1]:
            processed = ec_builder2.process_item(t)
            if processed:
                pass
        runner = Runner([ec_builder2])
        runner.run()


    def test_group_by_structure(self):
        # TODO: should add some tests beyond "does it work"
        # crit = {"formula_pretty": "NaN3", "task_label":"elastic deformation"}
        docs1 = self.local_tasks.query(criteria={"formula_pretty": "NaN3"})
        structures_grouped1 = group_by_structure(docs1)

        sm = StructureMatcher(1e-10, 1e-10, 1e-10)
        docs2 = self.local_tasks.query(criteria={"task_label": "elastic deformation"})
        sgroup2 = group_by_structure(docs2, sm=sm)

if __name__ == "__main__":
    unittest.main()
