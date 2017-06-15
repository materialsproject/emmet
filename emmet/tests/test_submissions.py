import unittest
import os

from pymongo import MongoClient
from monty.serialization import loadfn
from emmet.submissions import MPSubmissionFilter

__author__ = "Joseph Montoya"
__email__ = "montoyjh@lbl.gov"

module_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)))
db_cred = loadfn(os.path.join(module_dir, "..", "..", "test_files", "db.json"))

class MpSubmissionFilterTest(unittest.TestCase):
    
    def setUp(self):
        # Set up test db, set up mpsft, etc.
        conn = MongoClient(db_cred["host"], db_cred["port"])
        db = conn[db_cred["database"]]
        self.submissions_coll = db.submissions
        self.materials_coll = db.materials
        self.mpsft = MPSubmissionFilter(self.submissions_coll, self.materials_coll)

    def test_init(self):
        mpsft = MPSubmissionFilter(self.submissions_coll)
        self.assertEqual(mpsft.materials_coll, None)
        self.assertEqual(self.mpsft.materials_coll, self.materials_coll)

    def test_check_for_duplicates(self):
        pass

    def test_submit(self):
        pass

    def test_add_snl_to_submissions(self):
        pass

if __name__ == "__main__":
    unittest.main()
