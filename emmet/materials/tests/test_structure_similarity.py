import unittest
import os

from emmet.materials.structure_similarity import *
from maggma.stores import MemoryStore, JSONStore

from monty.serialization import loadfn

__author__ = "Nils E. R. Zimmermann"
__email__ = "nerz@lbl.gov"

module_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)))
test_site_fp_stats = os.path.join(module_dir, "..", "..", "..", "test_files", "site_fingerprint_stats.json")


class StructureSimilarityBuilderTest(unittest.TestCase):
    @classmethod
    def setUpClass(self):
        # Set up test db, etc.
        self.test_site_descriptors = MemoryStore("struct_sim_site_fp")
        self.test_site_descriptors.connect()
        site_fp_docs = loadfn(test_site_fp_stats, cls=None)
        self.test_site_descriptors.update(site_fp_docs)

    def test_get_items(self):
        test_structure_similarity = MemoryStore("struct_sim_struct_sim")
        test_structure_similarity.connect()
        sim_builder = StructureSimilarityBuilder(self.test_site_descriptors, test_structure_similarity)

        items = list(sim_builder.get_items())
        self.assertEqual(len(items), 3)
        for i in items:
            d1 = i[0]
            d2 = i[1]
            self.assertIn("opsf_statistics", d1)
            self.assertIn("opsf_statistics", d2)

            self.assertIn("task_id", d1)
            self.assertIn("task_id", d2)

            processed = sim_builder.process_item(i)
            if processed:
                pass
            else:
                import nose
                nose.tools.set_trace()

    def test_get_all_site_descriptors(self):
        sim_builder = StructureSimilarityBuilder(self.test_site_descriptors, None)
        for d in self.test_site_descriptors.query():
            d = sim_builder.get_similarities(d, d)
            self.assertAlmostEqual(d['cos'], 1)
            self.assertAlmostEqual(d['dist'], 0)

        C = self.test_site_descriptors.query_one(criteria={"task_id": "mp-66"})
        NaCl = self.test_site_descriptors.query_one(criteria={"task_id": "mp-22862"})
        Fe = self.test_site_descriptors.query_one(criteria={"task_id": "mp-13"})

        d = sim_builder.get_similarities(C, NaCl)
        self.assertAlmostEqual(d['cos'], 0.0013649)
        self.assertAlmostEqual(d['dist'], 2.6866749)
        d = sim_builder.get_similarities(C, Fe)
        self.assertAlmostEqual(d['cos'], 0.0013069)
        self.assertAlmostEqual(d['dist'], 2.6293889)
        d = sim_builder.get_similarities(NaCl, Fe)
        self.assertAlmostEqual(d['cos'], 0.0012729)
        self.assertAlmostEqual(d['dist'], 2.7235044)


if __name__ == "__main__":
    unittest.main()
