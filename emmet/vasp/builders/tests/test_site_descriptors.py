import unittest
import os

from emmet.vasp.builders.site_descriptors import *
from maggma.stores import MongoStore
from maggma.runner import Runner

from monty.serialization import loadfn

__author__ = "Nils E. R. Zimmermann"
__email__ = "nerz@lbl.gov"

module_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)))
test_structs = os.path.join(module_dir, "..","..","..", "..", "test_files",
                            "simple_structs.json")

class SiteDescriptorsBuilderTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Set up test db, etc.
        cls.test_materials = MongoStore("test_emmet", "materials")
        cls.test_materials.connect()
        docs = loadfn(test_structs, cls=None)
        cls.test_materials.update(docs, key='material_id', update_lu=False)
        cls.test_site_descriptors = MongoStore("test_emmet", "site_descriptors")

    def test_builder(self):
        sd_builder = SiteDescriptorsBuilder(self.test_materials,
                                            self.test_site_descriptors)
        sd_builder.connect()
        for t in sd_builder.get_items():
            processed = sd_builder.process_item(t)
            if processed:
                pass
            else:
                import nose; nose.tools.set_trace()
        runner = Runner([sd_builder])
        runner.run()

    #TODO
    def get_site_descriptors_from_struct(self):
        pass

if __name__ == "__main__":
    unittest.main()
