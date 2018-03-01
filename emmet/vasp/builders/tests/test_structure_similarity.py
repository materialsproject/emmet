import unittest
import os

from emmet.vasp.builders.structure_similarity import *
from maggma.stores import MongoStore

from monty.serialization import loadfn

__author__ = "Nils E. R. Zimmermann"
__email__ = "nerz@lbl.gov"

module_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)))
test_site_fp_stats = os.path.join(module_dir, "..","..","..", "..", "test_files",
                                  "site_fingerprint_stats.json")

class StructureSimilarityBuilderTest(unittest.TestCase):
    def setUp(self):
        # Set up test db, etc.
        self.test_site_descriptors = MongoStore("test_emmet", 
                                                "struct_sim_site_fp",
                                                key="task_id")
        self.test_site_descriptors.connect()
        self.site_fp_docs = loadfn(test_site_fp_stats, cls=None)
        self.test_site_descriptors.update(self.site_fp_docs)
        self.test_structure_similarity = MongoStore("test_emmet",
                                                    "struct_sim_struct_sim",
                                                    "task_ids")

    def test_builder(self):
        sim_builder = StructureSimilarityBuilder(
                self.test_site_descriptors,
                self.test_structure_similarity)
        sim_builder.connect()
        for t in sim_builder.get_items():
            processed = sim_builder.process_item(t)
            if processed:
                pass
            else:
                import nose; nose.tools.set_trace()

    def test_get_all_site_descriptors(self):
        sim_builder = StructureSimilarityBuilder(
                self.test_site_descriptors,
                self.test_structure_similarity)
        for i in range(3):
            d = sim_builder.get_similarities(
                    self.site_fp_docs[i],
                    self.site_fp_docs[i])
            self.assertAlmostEqual(d['cos'], 1)
            self.assertAlmostEqual(d['dist'], 0)
        d = sim_builder.get_similarities(
                self.site_fp_docs[0],
                self.site_fp_docs[1])
        self.assertAlmostEqual(d['cos'], 0.0013649)
        self.assertAlmostEqual(d['dist'], 2.6866749)
        d = sim_builder.get_similarities(
                self.site_fp_docs[0],
                self.site_fp_docs[2])
        self.assertAlmostEqual(d['cos'], 0.0013069)
        self.assertAlmostEqual(d['dist'], 2.6293889)
        d = sim_builder.get_similarities(
                self.site_fp_docs[1],
                self.site_fp_docs[2])
        self.assertAlmostEqual(d['cos'], 0.0012729)
        self.assertAlmostEqual(d['dist'], 2.7235044)

if __name__ == "__main__":
    unittest.main()
