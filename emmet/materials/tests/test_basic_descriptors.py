import unittest
import os

from pymatgen import Structure
from emmet.materials.basic_descriptors import BasicDescriptorsBuilder
from maggma.stores import MemoryStore

from monty.serialization import loadfn

__author__ = "Nils E. R. Zimmermann"
__email__ = "nerz@lbl.gov"

module_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)))
test_structs = os.path.join(
    module_dir, "..", "..", "..", "test_files", "simple_structs.json")
test_meta_comp_descr = os.path.join(
    module_dir, "..", "..", "..", "test_files", "meta_comp_descr.json")


class BasicDescriptorsBuilderTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Set up test db, etc.
        cls.test_materials = MemoryStore("mat_descriptors")

        cls.test_materials.connect()
        struct_docs = loadfn(test_structs, cls=None)
        cls.test_materials.update(struct_docs)

    def test_builder(self):
        test_basic_descriptors = MemoryStore("test_basic_descriptors")
        sd_builder = BasicDescriptorsBuilder(
            self.test_materials, test_basic_descriptors)
        sd_builder.connect()
        meta_comp_descr = loadfn(test_meta_comp_descr, cls=None)

        for t in sd_builder.get_items():
            processed = sd_builder.process_item(t)
            if processed:
                sd_builder.update_targets([processed])
            else:
                import nose
                nose.tools.set_trace()
            for md in ['nsites', 'formula_pretty', 'nelements']:
                self.assertEqual(processed['meta']['atomate'][md],
                                 meta_comp_descr['meta'][t['task_id']][md])
            for k, v in meta_comp_descr['comp_descr'][t['task_id']][0].items():
                if k != 'name':
                    self.assertAlmostEqual(
                        processed['composition_descriptors'][0][k], v)
        self.assertEqual(len([t for t in sd_builder.get_items()]), 0)

    def test_get_all_basic_descriptors(self):
        test_basic_descriptors = MemoryStore("test_basic_descriptors")
        sd_builder = BasicDescriptorsBuilder(
            self.test_materials, test_basic_descriptors)

        C = self.test_materials.query_one(criteria={"task_id": "mp-66"})
        NaCl = self.test_materials.query_one(criteria={"task_id": "mp-22862"})
        Fe = self.test_materials.query_one(criteria={"task_id": "mp-13"})

        # Diamond.
        d = sd_builder.get_site_descriptors_from_struct(
            Structure.from_dict(C["structure"]))
        for di in d.values():
            self.assertEqual(len(di), 2)
        self.assertEqual(d['cn_VoronoiNN'][0]['CN_VoronoiNN'], 20)
        self.assertAlmostEqual(
            d['cn_wt_VoronoiNN'][0]['CN_VoronoiNN'], 4.5381162)
        self.assertEqual(d['cn_JmolNN'][0]['CN_JmolNN'], 4)
        self.assertAlmostEqual(d['cn_wt_JmolNN'][0]['CN_JmolNN'], 4.9617398)
        self.assertEqual(
            d['cn_MinimumDistanceNN'][0]['CN_MinimumDistanceNN'], 4)
        self.assertAlmostEqual(
            d['cn_wt_MinimumDistanceNN'][0]['CN_MinimumDistanceNN'], 4)
        self.assertEqual(d['cn_MinimumOKeeffeNN'][0]['CN_MinimumOKeeffeNN'], 4)
        self.assertAlmostEqual(
            d['cn_wt_MinimumOKeeffeNN'][0]['CN_MinimumOKeeffeNN'], 4)
        self.assertEqual(d['cn_MinimumVIRENN'][0]['CN_MinimumVIRENN'], 4)
        self.assertAlmostEqual(
            d['cn_wt_MinimumVIRENN'][0]['CN_MinimumVIRENN'], 4)
        self.assertEqual(
            d['cn_BrunnerNN_reciprocal'][0]['CN_BrunnerNN_reciprocal'], 4)
        self.assertAlmostEqual(
            d['cn_wt_BrunnerNN_reciprocal'][0]['CN_BrunnerNN_reciprocal'], 4)
        # Current value for the below quantity is 0.9618085
        self.assertTrue(0.95 <= d['csf'][0]['tetrahedral CN_4'] <= 1)
        ds = sd_builder.get_statistics(d)
        self.assertTrue('csf' in list(ds.keys()))
        for k, dsk in ds.items():
            for di in dsk:
                self.assertEqual(len(list(di.keys())), 3)

        def get_index(li, optype):
            try:
                return next(i for i, d in enumerate(li) if d['name'] == optype)
            except StopIteration:
                raise RuntimeError('did not find optype {}'.format(optype))

        # Current value for the three below quantities is 0.9618085
        self.assertTrue(
            0.95 <= ds['csf'][get_index(ds['csf'], 'tetrahedral CN_4')]['mean']
            <= 1)

        self.assertAlmostEqual(
            ds['csf'][get_index(ds['csf'], 'tetrahedral CN_4')]['std'], 0)
        self.assertAlmostEqual(
            ds['csf'][get_index(ds['csf'], 'octahedral CN_6')]['mean'], 0)

        # NaCl.
        d = sd_builder.get_site_descriptors_from_struct(
            Structure.from_dict(NaCl["structure"]))
        self.assertAlmostEqual(d['csf'][0]['octahedral CN_6'], 1)
        ds = sd_builder.get_statistics(d)
        self.assertAlmostEqual(
            ds['csf'][get_index(ds['csf'], 'octahedral CN_6')]['mean'], 1)
        self.assertAlmostEqual(
            ds['csf'][get_index(ds['csf'], 'octahedral CN_6')]['std'], 0)

        # Iron.
        d = sd_builder.get_site_descriptors_from_struct(
            Structure.from_dict(Fe["structure"]))
        self.assertAlmostEqual(
            d['csf'][0]['body-centered cubic CN_8'], 0.57918, 4)
        ds = sd_builder.get_statistics(d)
        self.assertAlmostEqual(
            ds['csf'][get_index(ds['csf'], 'body-centered cubic CN_8')]['mean'],
            0.57918, 4)
        self.assertAlmostEqual(
            ds['csf'][get_index(ds['csf'], 'body-centered cubic CN_8')]['std'],
            0)


if __name__ == "__main__":
    unittest.main()
