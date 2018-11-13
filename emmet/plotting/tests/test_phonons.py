import unittest
import os
import json

from monty.io import zopen
from emmet.plotting.phonon import PhononWebBuilder
from maggma.stores import MongoStore, GridFSStore


module_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)))
test_files_dir = os.path.join(module_dir, "..", "..", "..", "test_files", "abinit")


class TestPhononWebBuilder(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.phonon_bs_store = GridFSStore("emmet_test", "phonon_bs", lu_field="last_updated", key="task_id")
        cls.phonon_dos_store = GridFSStore("emmet_test", "phonon_dos", lu_field="last_updated", key="task_id")
        cls.phonon_store = MongoStore("emmet_test", "phonon", lu_field="last_updated", key="task_id")
        cls.web_store = MongoStore("emmet_test", "web", lu_field="last_updated", key="task_id")
        cls.images_store = MongoStore("emmet_test", "images", lu_field="last_updated", key="task_id")
        cls.processed_store = MongoStore("emmet_test", "processed", lu_field="last_updated", key="task_id")

        item_path = os.path.join(test_files_dir, "builders", "phonon_items", "mp-1565_phonon_plot_item.json.gz")
        with zopen(item_path) as item_f:
            cls.item = json.loads(item_f.read().decode())

    @classmethod
    def tearDownClass(cls):
        cleardb(cls.web_store.collection.database)

    def setUp(self):

        self.builder = PhononWebBuilder(self.phonon_bs_store, self.phonon_dos_store, self.phonon_store, self.web_store,
                                        self.images_store, self.processed_store)
        self.builder.connect()

    def test_process_item(self):
        
        # Disabling latex for testing.
        from matplotlib import rc
        rc('text', usetex=False)
        d = self.builder.process_item(self.item)


def cleardb(db):
    for coll in db.collection_names():
        if coll != "system.indexes":
            db[coll].drop()

if __name__ == "__main__":
    unittest.main()

