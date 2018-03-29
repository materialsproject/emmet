import os
import unittest
from maggma.stores import MemoryStore
from maggma.runner import Runner
from emmet.materials.property_workflows import PropertyWorkflowBuilder,\
    get_elastic_builder
from pymatgen.util.testing import PymatgenTest
from atomate.vasp.workflows.presets.core import wf_elastic_constant
from atomate.vasp.powerups import add_tags
from fireworks import LaunchPad, Workflow

__author__ = "Joseph Montoya"
__email__ = "montoyjh@lbl.gov"

module_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)))

class TestPropertyWorkflowBuilder(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        materials = MemoryStore("materials")
        materials.connect()
        docs = []
        for n, mat_string in enumerate(["Si", "Sn", "TiO2", "VO2"]):
            docs.append({"material_id": "mp-{}".format(n),
                         "structure": PymatgenTest.get_structure(mat_string).as_dict()})
        docs[0].update({"elasticity": 10})
        materials.update(docs, key='material_id')
        cls.materials = materials

    def setUp(self):
        lpad = LaunchPad(name="test_emmet")
        lpad.reset('', require_password=False)
        self.lpad = lpad

        self.nofilter = PropertyWorkflowBuilder(self.materials, wf_elastic_constant,
                                                filter=None, lpad=self.lpad)
        self.nofilter.connect()
        self.filter = PropertyWorkflowBuilder(self.materials, wf_elastic_constant,
                                              filter={"elasticity": {"$exists": False}},
                                              lpad=self.lpad)
        self.filter.connect()

    def test_get_items(self):
        # No filter
        self.assertEqual(len(list(self.nofilter.get_items())), 4)

        # elasticity filter
        self.assertEqual(len(list(self.filter.get_items())), 3)

    def test_process_items(self):
        for item in self.nofilter.get_items():
            processed = self.nofilter.process_item(item)
            self.assertTrue(isinstance(processed, Workflow))
            self.assertTrue(item[0]['material_id'] in processed.metadata['tags'])

    def test_update_targets(self):
        processed = [self.nofilter.process_item(item)
                     for item in self.nofilter.get_items()]
        self.nofilter.update_targets(processed)
        self.assertEqual(self.lpad.workflows.count(), 4)

    def test_runner_pipeline(self):
        runner = Runner([self.nofilter])
        runner.run()
        self.assertEqual(self.lpad.workflows.count(), 4)

        # Ensure no further updates
        runner.run()
        self.assertEqual(self.lpad.workflows.count(), 4)

if __name__ == "__main__":
    unittest.main()