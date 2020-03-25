import os
import unittest
from maggma.stores import JSONStore, MemoryStore
from pymatgen import Composition
from numpy import unique
from emmet.materials.electrodes import ElectrodesBuilder, mat_props, generic_groupby
from emmet.materials.thermo import chemsys_permutations
from pymatgen.analysis.phase_diagram import PhaseDiagram
__author__ = "Jimmy Shen"
__email__ = "jmmshn@lbl.gov"

module_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)))
test_mats = os.path.join(module_dir, "..", "..", "..", "test_files", "insert_electrode.json")


def get_no_li_comp(comp, return_str=True):
    # get the reduced composition without Li
    dd = comp.as_dict()
    if "Li" in dd:
        dd.pop('Li')
    if return_str:
        return Composition(dd).reduced_formula
    else:
        return Composition(dd)


class TestElectroInsert(unittest.TestCase):
    def setUp(self):
        self.materials = JSONStore(test_mats)
        self.materials.connect()
        self.insert_electrode = MemoryStore("insert_electrode")
        self.insert_electrode.connect()
        self.builder = ElectrodesBuilder(materials=self.materials, electro=self.insert_electrode,working_ion='Li')

    def test_gneric_groupby(self):
        self.assertEqual(generic_groupby([1,2,3,4]), [0,1,2,3])
        self.assertEqual(generic_groupby([1,1,1,1]), [0,0,0,0])

    def test_mat_doc2comp_entry(self):
        mat_docs = [*self.materials.query({}, properties=mat_props)]
        self.assertEqual(len(self.builder._mat_doc2comp_entry(mat_docs)), 168)  # documents in the json file

    def test_get_hashed_entries_from_chemsys(self):
        seen_comps = []
        hashed_entries = [*self.builder.get_hashed_entries_from_chemsys('Bi-Li-O')]
        EXPECTED_UNIQUE_FORMULAE  = 9
        self.assertEqual(len(hashed_entries), EXPECTED_UNIQUE_FORMULAE)
        for ii in hashed_entries:
            all_comps = [get_no_li_comp(ient.composition) for ient in ii['elec_entries']]
            self.assertEqual(len(unique(all_comps)), 1)
            seen_comps.append(all_comps[0])
        self.assertEqual(len(unique(seen_comps)), len(seen_comps))

    def test_group_entries(self):
        for ii in self.builder.get_hashed_entries_from_chemsys('Bi-Li-O'):
            groups = self.builder.group_entries(ii['elec_entries'])
            for ig in groups:
                structs_in_group = [ient.structure.copy() for ient in ig]
                for istruct in structs_in_group:
                    istruct.remove_species(['Li'])
                self.assertEqual(max(generic_groupby(structs_in_group, self.builder.sm.fit)), 0)

    def test_get_items(self):
        for item in self.builder.get_items():
            # check that all the structures have similar delithiated forumlae
            ref_comp = get_no_li_comp(item['elec_entries'][0].composition)
            for ient in item['elec_entries']:
                self.assertEqual(ref_comp, get_no_li_comp(ient.composition))

            # check that all the chemsys is in represented the entries of the phase diagram
            all_chemsys = chemsys_permutations(item['chemsys'])
            pd_chemsys = ['-'.join(sorted(ient.composition.as_dict().keys())) for ient in item['pd_entries']]
            for ichemsys in all_chemsys:
                self.assertEqual(ichemsys in pd_chemsys, True)


    def test_get_competing_conversion_electrode(self):
        for item in self.builder.get_items():
            ents = sorted(item['elec_entries'], key=lambda x : x.composition.get_atomic_fraction(self.builder.working_ion))
            pd = PhaseDiagram(item['pd_entries'])
            comp = ents[-1].composition
            f, v = self.builder.get_competing_conversion_electrode_profile(comp, pd)
            self.assertEqual(len(f), len(v))

    def test_process_items(self):
        items = [*self.builder.get_items()]
        sbxn_set = {'shyamd', 'mkhorton', 'vw', 'basf', 'core', 'jcesr'}
        expected_charged = ['Bi', 'Li7BiO6']
        for ii in items:
            result = self.builder.process_item(ii)
            if result != []:
                self.assertEqual({ires['_sbxn'][0] for ires in result}, sbxn_set)
                expected_charged.remove(result[0]['formula_charge'])
        self.assertEqual(expected_charged, [])


    def test_update_targets(self):
        items = [[{"battid": 1, "_sbxn": ["core"]}] * 3, [{"battid": 2, "_sbxn": ["core"]}] * 4, [{"battid": 3 ,"_sbxn": ["core"]}] * 4]
        tbuilder = ElectrodesBuilder(materials=self.materials, electro=self.insert_electrode,working_ion='Li')
        tbuilder.update_targets(items)
        self.assertEqual(len(self.insert_electrode.distinct("battid")), 3)

    def test_run(self):
        self.builder.run()
        all_elec_docs = [*self.builder.electro.query()]
        self.assertEqual(len(all_elec_docs), 12)

if __name__ == "__main__":
    unittest.main()
