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
        self.test_materials = MongoStore("test_emmet", "materials", key="material_id")
        self.test_materials.connect()
        self.struct_docs = loadfn(test_structs, cls=None)
        self.test_materials.update(self.struct_docs)
        self.test_site_descriptors = MongoStore("test_emmet", "site_descriptors")

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
        opsf = OPSiteFingerprint()
        itet = opsf.feature_labels().index('tetrahedral CN_4')
        ioct = opsf.feature_labels().index('octahedral CN_6')
        ibcc = opsf.feature_labels().index('body-centered cubic CN_8')
        csf = CrystalSiteFingerprint.from_preset('ops')
        itet_csf = csf.feature_labels().index('tetrahedral CN_4')
        ioct_csf = csf.feature_labels().index('octahedral CN_6')
        ibcc_csf = csf.feature_labels().index('body-centered cubic CN_8')

        # Diamond.
        d = sd_builder.get_site_descriptors_from_struct(
            Structure.from_dict(self.struct_docs[0]["structure"]))
        for di in d.values():
            self.assertEqual(len([k for k in di.keys()]), 2)
        self.assertEqual(d['cn_vnn'][0][0], 18)
        self.assertAlmostEqual(d['cn_wt_vnn'][0][0], 4.5381162)
        self.assertEqual(d['cn_jmnn'][0][0], 4)
        self.assertAlmostEqual(d['cn_wt_jmnn'][0][0], 4.9617398)
        self.assertEqual(d['cn_mdnn'][0][0], 4)
        self.assertAlmostEqual(d['cn_wt_mdnn'][0][0], 4)
        self.assertEqual(d['cn_moknn'][0][0], 4)
        self.assertAlmostEqual(d['cn_wt_moknn'][0][0], 4)
        self.assertEqual(d['cn_mvirenn'][0][0], 4)
        self.assertAlmostEqual(d['cn_wt_mvirenn'][0][0], 4)
        self.assertEqual(d['cn_bnn'][0][0], 4)
        self.assertAlmostEqual(d['cn_wt_bnn'][0][0], 4)
        self.assertAlmostEqual(d['opsf'][0][itet], 0.9995)
        self.assertAlmostEqual(d['csf'][0][itet_csf], 0.9886777)
        ds = sd_builder.get_opsf_statistics(d)
        for di in ds.values():
            self.assertEqual(len(list(di.keys())), 4)
        self.assertAlmostEqual(ds[itet]['max'], 0.9995)
        self.assertAlmostEqual(ds[itet]['min'], 0.9995)
        self.assertAlmostEqual(ds[itet]['mean'], 0.9995)
        self.assertAlmostEqual(ds[itet]['std'], 0)
        self.assertAlmostEqual(ds[ioct]['mean'], 0.0005)

        # NaCl.
        d = sd_builder.get_site_descriptors_from_struct(Structure.from_dict(
            self.struct_docs[1]["structure"]))
        self.assertAlmostEqual(d['opsf'][0][ioct], 0.9995)
        self.assertAlmostEqual(d['csf'][0][ioct_csf], 1)
        ds = sd_builder.get_opsf_statistics(d)
        self.assertAlmostEqual(ds[ioct]['max'], 0.9995)
        self.assertAlmostEqual(ds[ioct]['min'], 0.9995)
        self.assertAlmostEqual(ds[ioct]['mean'], 0.9995)
        self.assertAlmostEqual(ds[ioct]['std'], 0)

        # Iron.
        d = sd_builder.get_site_descriptors_from_struct(Structure.from_dict(
            self.struct_docs[2]["structure"]))
        self.assertAlmostEqual(d['opsf'][0][ibcc], 0.9995)
        self.assertAlmostEqual(d['csf'][0][ibcc_csf], 0.755096)
        ds = sd_builder.get_opsf_statistics(d)
        self.assertAlmostEqual(ds[ibcc]['max'], 0.9995)
        self.assertAlmostEqual(ds[ibcc]['min'], 0.9995)
        self.assertAlmostEqual(ds[ibcc]['mean'], 0.9995)
        self.assertAlmostEqual(ds[ibcc]['std'], 0)

if __name__ == "__main__":
    unittest.main()
