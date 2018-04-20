import unittest
import os

from emmet.materials.site_descriptors import *
from maggma.stores import MemoryStore

from monty.serialization import loadfn

from matminer.featurizers.site import OPSiteFingerprint ,\
    CrystalSiteFingerprint

__author__ = "Nils E. R. Zimmermann"
__email__ = "nerz@lbl.gov"

module_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)))
test_structs = os.path.join(module_dir, "..", "..", "..", "test_files", "simple_structs.json")


class SiteDescriptorsBuilderTest(unittest.TestCase):
    @classmethod
    def setUpClass(self):
        # Set up test db, etc.
        self.test_materials = MemoryStore("mat_site_fingerprint")

        self.test_materials.connect()
        struct_docs = loadfn(test_structs, cls=None)
        self.test_materials.update(struct_docs)

    def test_builder(self):
        test_site_descriptors = MemoryStore("test_site_descriptors")
        sd_builder = SiteDescriptorsBuilder(self.test_materials, test_site_descriptors)
        sd_builder.connect()
        for t in sd_builder.get_items():
            processed = sd_builder.process_item(t)
            if processed:
                sd_builder.update_targets([processed])
            else:
                import nose
                nose.tools.set_trace()
        self.assertEqual(len([t for t in sd_builder.get_items()]), 0)

        # Remove one data piece in diamond entry and test partial update.
        test_site_descriptors.collection.find_one_and_update(
                {'task_id': 'mp-66'}, {'$unset': {'site_descriptors': 1}})
        items = [e for e in list(sd_builder.get_items())]
        self.assertEqual(len(items), 1)

    def test_get_all_site_descriptors(self):
        test_site_descriptors = MemoryStore("test_site_descriptors")
        sd_builder = SiteDescriptorsBuilder(self.test_materials, test_site_descriptors)

        C = self.test_materials.query_one(criteria={"task_id": "mp-66"})
        NaCl = self.test_materials.query_one(criteria={"task_id": "mp-22862"})
        Fe = self.test_materials.query_one(criteria={"task_id": "mp-13"})

        # Diamond.
        d = sd_builder.get_site_descriptors_from_struct(Structure.from_dict(C["structure"]))
        for di in d.values():
            self.assertEqual(len(di), 2)
        self.assertEqual(d['cn_VoronoiNN'][0]['CN_VoronoiNN'], 20)
        self.assertAlmostEqual(d['cn_wt_VoronoiNN'][0]['CN_VoronoiNN'], 4.5381162)
        self.assertEqual(d['cn_JMolNN'][0]['CN_JMolNN'], 4)
        self.assertAlmostEqual(d['cn_wt_JMolNN'][0]['CN_JMolNN'], 4.9617398)
        self.assertEqual(d['cn_MinimumDistanceNN'][0]['CN_MinimumDistanceNN'], 4)
        self.assertAlmostEqual(d['cn_wt_MinimumDistanceNN'][0]['CN_MinimumDistanceNN'], 4)
        self.assertEqual(d['cn_MinimumOKeeffeNN'][0]['CN_MinimumOKeeffeNN'], 4)
        self.assertAlmostEqual(d['cn_wt_MinimumOKeeffeNN'][0]['CN_MinimumOKeeffeNN'], 4)
        self.assertEqual(d['cn_MinimumVIRENN'][0]['CN_MinimumVIRENN'], 4)
        self.assertAlmostEqual(d['cn_wt_MinimumVIRENN'][0]['CN_MinimumVIRENN'], 4)
        self.assertEqual(d['cn_BrunnerNN_reciprocal'][0]['CN_BrunnerNN_reciprocal'], 4)
        self.assertAlmostEqual(d['cn_wt_BrunnerNN_reciprocal'][0]['CN_BrunnerNN_reciprocal'], 4)
        self.assertAlmostEqual(d['opsf'][0]['tetrahedral CN_4'], 0.9995)
        #self.assertAlmostEqual(d['csf'][0]['tetrahedral CN_4'], 0.9886777)
        ds = sd_builder.get_statistics(d)
        self.assertTrue('opsf' in list(ds.keys()))
        self.assertTrue('csf' in list(ds.keys()))
        for k, dsk in ds.items():
            for di in dsk:
                self.assertEqual(len(list(di.keys())), 5)
        def get_index(li, optype):
            for i, di in enumerate(li):
                if di['name'] == optype:
                    return i
            raise RuntimeError('did not find optype {}'.format(optype))
        self.assertAlmostEqual(ds['opsf'][get_index(ds['opsf'], 'tetrahedral CN_4')]['max'], 0.9995)
        self.assertAlmostEqual(ds['opsf'][get_index(ds['opsf'], 'tetrahedral CN_4')]['min'], 0.9995)
        self.assertAlmostEqual(ds['opsf'][get_index(ds['opsf'], 'tetrahedral CN_4')]['mean'], 0.9995)
        self.assertAlmostEqual(ds['opsf'][get_index(ds['opsf'], 'tetrahedral CN_4')]['std'], 0)
        self.assertAlmostEqual(ds['opsf'][get_index(ds['opsf'], 'octahedral CN_6')]['mean'], 0.0005)

        # NaCl.
        d = sd_builder.get_site_descriptors_from_struct(Structure.from_dict(NaCl["structure"]))
        self.assertAlmostEqual(d['opsf'][0]['octahedral CN_6'], 0.9995)
        #self.assertAlmostEqual(d['csf'][0]['octahedral CN_6'], 1)
        ds = sd_builder.get_statistics(d)
        self.assertAlmostEqual(ds['opsf'][get_index(ds['opsf'], 'octahedral CN_6')]['max'], 0.9995)
        self.assertAlmostEqual(ds['opsf'][get_index(ds['opsf'], 'octahedral CN_6')]['min'], 0.9995)
        self.assertAlmostEqual(ds['opsf'][get_index(ds['opsf'], 'octahedral CN_6')]['mean'], 0.9995)
        self.assertAlmostEqual(ds['opsf'][get_index(ds['opsf'], 'octahedral CN_6')]['std'], 0)

        # Iron.
        d = sd_builder.get_site_descriptors_from_struct(Structure.from_dict(Fe["structure"]))
        self.assertAlmostEqual(d['opsf'][0]['body-centered cubic CN_8'], 0.9995)
        #self.assertAlmostEqual(d['csf'][0]['body-centered cubic CN_8'], 0.755096)
        ds = sd_builder.get_statistics(d)
        self.assertAlmostEqual(ds['opsf'][get_index(ds['opsf'], 'body-centered cubic CN_8')]['max'], 0.9995)
        self.assertAlmostEqual(ds['opsf'][get_index(ds['opsf'], 'body-centered cubic CN_8')]['min'], 0.9995)
        self.assertAlmostEqual(ds['opsf'][get_index(ds['opsf'], 'body-centered cubic CN_8')]['mean'], 0.9995)
        self.assertAlmostEqual(ds['opsf'][get_index(ds['opsf'], 'body-centered cubic CN_8')]['std'], 0)


if __name__ == "__main__":
    unittest.main()
