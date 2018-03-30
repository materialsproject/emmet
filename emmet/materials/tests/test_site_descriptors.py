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
        #for i in self.test_materials.query(
        #        properties=[self.test_materials.key, "structure", "last_updated"],
        #        criteria={}):
        #    print(i['last_updated'])

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
        self.assertEqual(len(items[0]['output']['statistics']), 0)
        self.assertTrue(len(items[0]['output']['site_descriptors']) > 0)
        #test_site_descriptors.collection.find_one_and_update(
        #        {'task_id': 'mp-66'}, {'statistics': {'$unset': {'opsf': 1}}})
        #items = [e for e in list(sd_builder.get_items())]
        #print(items)
# [{'input': {'task_id': 'mp-66', 'structure': {'@module': 'pymatgen.core.structure', '@class': 'Structure', 'charge': None, 'lattice': {'matrix': [[2.18898221, 0.0, 1.26380947], [0.72966074, 2.06379222, 1.26380947], [0.0, 0.0, 2.52761893]], 'a': 2.5276189372922024, 'b': 2.527618938703292, 'c': 2.52761893, 'alpha': 59.99999998302958, 'beta': 59.999999964562214, 'gamma': 59.999999919282544, 'volume': 11.418782537993515}, 'sites': [{'species': [{'element': 'C', 'occu': 1}], 'abc': [0.875, 0.875, 0.875], 'xyz': [2.55381258125, 1.8058181924999999, 4.42333313625], 'label': 'C', 'properties': {'coordination_no': 5, 'forces': [0.0, 0.0, 0.0]}}, {'species': [{'element': 'C', 'occu': 1}], 'abc': [0.125, 0.125, 0.125], 'xyz': [0.36483036874999997, 0.2579740275, 0.63190473375], 'label': 'C', 'properties': {'coordination_no': 5, 'forces': [0.0, 0.0, 0.0]}}]}, '_id': ObjectId('5abd7889f0b3c610d2f8f04a')}, 'output': {'site_descriptors': ['cn_vnn', 'cn_wt_vnn', 'cn_VoronoiNN_modified', 'cn_wt_VoronoiNN_modified', 'cn_jmnn', 'cn_wt_jmnn', 'cn_mdnn', 'cn_wt_mdnn', 'cn_moknn', 'cn_wt_moknn', 'cn_mvirenn', 'cn_wt_mvirenn', 'cn_bnn', 'cn_wt_bnn', 'cn_EconNN', 'cn_wt_EconNN'], 'statistics': []}}]

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
            raise RuntimeError('did not find optype'.format(optype))
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
