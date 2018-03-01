import unittest
import os

from emmet.vasp.builders.site_descriptors import *
from maggma.stores import MongoStore

from monty.serialization import loadfn

from matminer.featurizers.site import OPSiteFingerprint ,\
CrystalSiteFingerprint

__author__ = "Nils E. R. Zimmermann"
__email__ = "nerz@lbl.gov"

module_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)))
test_structs = os.path.join(module_dir, "..","..","..", "..", "test_files",
                            "simple_structs.json")

class SiteDescriptorsBuilderTest(unittest.TestCase):
    def setUp(self):
        # Set up test db, etc.
        self.test_materials = MongoStore("test_emmet", 
                                         "mat_site_fingerprint",
                                         key="material_id")
        self.test_materials.connect()
        self.struct_docs = loadfn(test_structs, cls=None)
        self.test_materials.update(self.struct_docs)
        self.test_site_descriptors = MongoStore("test_emmet",
                                                "site_descriptors")

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

    def test_get_all_site_descriptors(self):
        sd_builder = SiteDescriptorsBuilder(self.test_materials,
            self.test_site_descriptors)

        # Diamond.
        d = sd_builder.get_site_descriptors_from_struct(
            Structure.from_dict(self.struct_docs[0]["structure"]))
        for di in d.values():
            self.assertEqual(len([k for k in di.keys()]), 2)
        self.assertEqual(d['cn_vnn'][0]['CN_VoronoiNN'], 18)
        self.assertAlmostEqual(d['cn_wt_vnn'][0]['CN_VoronoiNN'], 4.5381162)
        self.assertEqual(d['cn_jmnn'][0]['CN_JMolNN'], 4)
        self.assertAlmostEqual(d['cn_wt_jmnn'][0]['CN_JMolNN'], 4.9617398)
        self.assertEqual(d['cn_mdnn'][0]['CN_MinimumDistanceNN'], 4)
        self.assertAlmostEqual(d['cn_wt_mdnn'][0]['CN_MinimumDistanceNN'], 4)
        self.assertEqual(d['cn_moknn'][0]['CN_MinimumOKeeffeNN'], 4)
        self.assertAlmostEqual(d['cn_wt_moknn'][0]['CN_MinimumOKeeffeNN'], 4)
        self.assertEqual(d['cn_mvirenn'][0]['CN_MinimumVIRENN'], 4)
        self.assertAlmostEqual(d['cn_wt_mvirenn'][0]['CN_MinimumVIRENN'], 4)
        self.assertEqual(d['cn_bnn'][0]['CN_BrunnerNN'], 4)
        self.assertAlmostEqual(d['cn_wt_bnn'][0]['CN_BrunnerNN'], 4)
        self.assertAlmostEqual(d['opsf'][0]['tetrahedral CN_4'], 0.9995)
        #self.assertAlmostEqual(d['csf'][0]['tetrahedral CN_4'], 0.9886777)
        ds = sd_builder.get_opsf_statistics(d)
        for di in ds.values():
            self.assertEqual(len(list(di.keys())), 4)
        self.assertAlmostEqual(ds['tetrahedral CN_4']['max'], 0.9995)
        self.assertAlmostEqual(ds['tetrahedral CN_4']['min'], 0.9995)
        self.assertAlmostEqual(ds['tetrahedral CN_4']['mean'], 0.9995)
        self.assertAlmostEqual(ds['tetrahedral CN_4']['std'], 0)
        self.assertAlmostEqual(ds['octahedral CN_6']['mean'], 0.0005)

        # NaCl.
        d = sd_builder.get_site_descriptors_from_struct(Structure.from_dict(
            self.struct_docs[1]["structure"]))
        self.assertAlmostEqual(d['opsf'][0]['octahedral CN_6'], 0.9995)
        #self.assertAlmostEqual(d['csf'][0]['octahedral CN_6'], 1)
        ds = sd_builder.get_opsf_statistics(d)
        self.assertAlmostEqual(ds['octahedral CN_6']['max'], 0.9995)
        self.assertAlmostEqual(ds['octahedral CN_6']['min'], 0.9995)
        self.assertAlmostEqual(ds['octahedral CN_6']['mean'], 0.9995)
        self.assertAlmostEqual(ds['octahedral CN_6']['std'], 0)

        # Iron.
        d = sd_builder.get_site_descriptors_from_struct(Structure.from_dict(
            self.struct_docs[2]["structure"]))
        self.assertAlmostEqual(d['opsf'][0]['body-centered cubic CN_8'], 0.9995)
        #self.assertAlmostEqual(d['csf'][0]['body-centered cubic CN_8'], 0.755096)
        ds = sd_builder.get_opsf_statistics(d)
        self.assertAlmostEqual(ds['body-centered cubic CN_8']['max'], 0.9995)
        self.assertAlmostEqual(ds['body-centered cubic CN_8']['min'], 0.9995)
        self.assertAlmostEqual(ds['body-centered cubic CN_8']['mean'], 0.9995)
        self.assertAlmostEqual(ds['body-centered cubic CN_8']['std'], 0)

if __name__ == "__main__":
    unittest.main()
