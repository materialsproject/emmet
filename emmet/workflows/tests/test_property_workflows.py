import os
import unittest

from maggma.stores import MemoryStore
from maggma.runner import Runner
from maggma.builders import Builder
from emmet.workflows.property_workflows import PropertyWorkflowBuilder,\
    get_elastic_wf_builder
from pymatgen.util.testing import PymatgenTest
from atomate.vasp.workflows.presets.core import wf_elastic_constant
from fireworks import LaunchPad, Workflow
from monty.tempfile import ScratchDir
from monty.serialization import dumpfn, loadfn

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
            docs.append({"task_id": n, "structure": PymatgenTest.get_structure(mat_string).as_dict()})
        materials.update(docs, key='task_id')
        elasticity = MemoryStore("elasticity")
        elasticity.connect()
        elasticity.update(docs[0:1], key="task_id")
        cls.materials = materials
        cls.elasticity = elasticity

    def setUp(self):
        lpad = LaunchPad(name="test_emmet")
        lpad.reset('', require_password=False)
        self.lpad = lpad

        self.nofilter = PropertyWorkflowBuilder(
            self.elasticity, self.materials, wf_elastic_constant, material_filter=None, lpad=self.lpad)
        self.nofilter.connect()
        self.filter = PropertyWorkflowBuilder(
            self.elasticity,
            self.materials,
            wf_elastic_constant,
            material_filter={"task_id": {
                "$lt": 3
            }},
            lpad=self.lpad)
        self.filter.connect()

    def test_serialization(self):
        # Test invocation from string method
        builder = PropertyWorkflowBuilder(
            self.elasticity,
            self.materials,
            "emmet.workflows.property_workflows.generate_elastic_workflow",
            lpad=self.lpad)
        serialized = builder.as_dict()
        new = PropertyWorkflowBuilder.from_dict(serialized)
        self.assertEqual(new._wf_function_string, "emmet.workflows.property_workflows.generate_elastic_workflow")
        with ScratchDir('.'):
            dumpfn(builder, "builder.yaml")
            new = loadfn("builder.yaml")
        self.assertTrue(isinstance(new, Builder))

    def test_get_items(self):
        # No filter
        self.assertEqual(len(list(self.nofilter.get_items())), 4)

        # elasticity filter
        self.assertEqual(len(list(self.filter.get_items())), 3)

    def test_process_items(self):
        for item in self.nofilter.get_items():
            processed = self.nofilter.process_item(item)
            if processed:
                self.assertTrue(isinstance(processed, Workflow))
                self.assertTrue(item[0]['task_id'] in processed.metadata['tags'])
            else:
                self.assertEqual(item[0]['task_id'], 0)

    def test_update_targets(self):
        processed = [self.nofilter.process_item(item) for item in self.nofilter.get_items()]
        self.nofilter.update_targets(processed)
        self.assertEqual(self.lpad.workflows.count(), 3)

    def test_runner_pipeline(self):
        runner = Runner([self.nofilter])
        runner.run()
        self.assertEqual(self.lpad.workflows.count(), 3)

        # Ensure no further updates
        runner.run()
        self.assertEqual(self.lpad.workflows.count(), 3)

    def test_elastic_wf_builder(self):
        el_wf_builder = get_elastic_wf_builder(self.elasticity, self.materials, self.lpad)
        self.assertEqual(len(list(el_wf_builder.get_items())), 4)
        # TODO: Test the functionality of this builder


if __name__ == "__main__":
    unittest.main()
