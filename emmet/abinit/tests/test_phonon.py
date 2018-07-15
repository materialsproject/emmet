import unittest
import os
import logging
import sys
import glob
import json
import numpy as np

from monty.io import zopen
from emmet.abinit.phonon import PhononBuilder, get_warnings
from maggma.stores import MongoStore, GridFSStore
from pymatgen.io.abinit.tasks import TaskManager


module_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)))
test_files_dir = os.path.join(module_dir, "..", "..", "..", "test_files", "abinit")


class PhononBuilderTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):

        root = logging.getLogger()
        root.setLevel(logging.DEBUG)

        ch = logging.StreamHandler(sys.stdout)
        ch.setLevel(logging.DEBUG)
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        ch.setFormatter(formatter)
        root.addHandler(ch)

        cls.phonons_results_store = MongoStore("emmet_test", "phonon_results", lu_field="last_updated", key="mp_id")
        cls.phonons_results_store.connect()
        cls.ddb_in_gridfs = GridFSStore("emmet_test", "ddb_fs")
        cls.ddb_in_gridfs.connect()

        cleardb(cls.phonons_results_store.collection.database)

        docs = []
        for result in glob.glob(os.path.join(test_files_dir, "builders", "phonon_results", "*_phonon_out.json.gz")):
            mp_id = os.path.basename(result).split("_")[0]
            ddb_path = os.path.join(test_files_dir, "builders", "ddb_files", "{}_DDB.gz".format(mp_id))
            with zopen(ddb_path) as ddb_f:
                ddb_id = cls.ddb_in_gridfs.collection.put(ddb_f.read())
            with zopen(result) as f:
                data = f.read().decode()
                r = json.loads(data)
                r['abinit_output']['ddb_id'] = ddb_id
                docs.append(r)

        cls.num_items = len(docs)
        cls.phonons_results_store.update(docs)

        item_path = os.path.join(test_files_dir, "builders", "phonon_items", "mp-1565_phonon_item.json.gz")
        with zopen(item_path) as item_f:
            cls.item = json.loads(item_f.read().decode())

    @classmethod
    def tearDownClass(cls):
        cleardb(cls.phonons_results_store.collection.database)

    def setUp(self):
        self.phonon_store = MongoStore("emmet_test", "phonon", lu_field="last_updated", key="task_id")
        self.phonon_bs_store = GridFSStore("emmet_test", "phonon_bs", lu_field="last_updated", key="task_id")
        self.phonon_dos_store = GridFSStore("emmet_test", "phonon_dos", lu_field="last_updated", key="task_id")
        self.ddb_out_store = GridFSStore("emmet_test", "ddb_out", lu_field="last_updated", key="task_id")

        # Since the tests do not call anaddb (no integration tests) the manager is never used,
        # but should be created. If not available in the system define the simple one used for travis.
        try:
            manager = TaskManager.from_user_config()
        except RuntimeError:
            manager = TaskManager.from_file(os.path.join(test_files_dir, "manager", "travis_manager.yml"))

        self.builder = PhononBuilder(self.phonons_results_store, self.phonon_store, self.phonon_bs_store,
                                     self.phonon_dos_store, self.ddb_out_store, manager=manager)
        self.builder.connect()

    def test_get_items(self):
        items = list(self.builder.get_items())

        self.assertEqual(self.num_items, len(items))
        for item in items:
            self.assertIn("ddb_str", item)
            self.assertIsNotNone(item["ddb_str"])

    def test_get_properties_anaddb_input(self):
        inp, labels_list = self.builder.get_properties_anaddb_input(self.item, dos="tetra")
        self.assertEqual(inp["prtdos"], 2)
        self.assertEqual(inp["dieflag"], 1)
        self.assertEqual(inp["nph1l"], 157)
        self.assertEqual(labels_list[-1], 'X')

        inp, labels_list = self.builder.get_properties_anaddb_input(self.item, bs=False, dos="gauss")
        self.assertEqual(inp["prtdos"], 1)
        self.assertNotIn("nph1l", inp)

    def test_abinit_input_vars(self):
        data = self.builder.abinit_input_vars(self.item)
        self.assertEqual(data['ngqpt'], self.item["abinit_input"]["ngqpt"])
        self.assertEqual(data['ngkpt'], self.item["abinit_input"]["ngkpt"])
        self.assertEqual(data['shiftk'], self.item["abinit_input"]["shiftk"])
        self.assertEqual(data['ecut'], self.item["abinit_input"]["ecut"])
        self.assertEqual(data['occopt'], self.item["abinit_input"]["occopt"])
        self.assertEqual(data['tsmear'], 0)

        self.assertEqual(data['gs_input']['ecut'], self.item["abinit_input"]["ecut"])
        self.assertEqual(data['dde_input']['ecut'], self.item["abinit_input"]["ecut"])
        self.assertEqual(data['ddk_input']['ecut'], self.item["abinit_input"]["ecut"])
        self.assertEqual(data['phonon_input']['ecut'], self.item["abinit_input"]["ecut"])
        self.assertEqual(len(data['wfq_input']), 0)

        self.assertEqual(len(data['pseudopotentials']['md5']), 2)

    def test_get_warnings(self):
        qpoints = np.array([[0., 0., 0.], [0.0001, 0., 0.], [0.3, 0, 0]])

        # in pymatgen Phonon BS the shape is (nqpts, nmodes)
        bands = np.array([np.linspace(0, 10, 20), np.linspace(1, 11, 20), np.linspace(10, 20, 20)]).T

        # all frequencies are positive
        ph_bs = dict(bands=bands, qpoints=qpoints)
        w = get_warnings(1, 0.01, ph_bs)
        self.assertDictEqual(w, dict(has_neg_fr=False, small_q_neg_fr=False, large_asr_break=False,
                                     large_cnsr_break=False))

        # small only close to gamma
        ph_bs["bands"] -= 3
        w = get_warnings(100, 0.5, ph_bs)
        self.assertDictEqual(w, dict(has_neg_fr=True, small_q_neg_fr=True, large_asr_break=True,
                                     large_cnsr_break=True))

        # small everywhere
        ph_bs["bands"] -= 10
        w = get_warnings(100, 0.5, ph_bs)
        self.assertDictEqual(w, dict(has_neg_fr=True, small_q_neg_fr=False, large_asr_break=True,
                                     large_cnsr_break=True))


def cleardb(db):
    for coll in db.collection_names():
        if coll != "system.indexes":
            db[coll].drop()

if __name__ == "__main__":
    unittest.main()

