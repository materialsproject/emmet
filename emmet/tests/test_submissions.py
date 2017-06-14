import unittest2 as unittest

__author__ = "Joey Montoya"
__email__ = "montoyjh@lbl.gov"

module_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)))
db_cred = loadfn(os.path.join(module_dir, "..", "..", "..", "test_files"))

def MpSubmissionFilterTest(unittest.TestCase):
    
    def setUp(self):
        # Set up test db, set up mpsft, etc.
        conn = MongoClient(db_cred["database"], db_cred["host"], db_cred["port"])
        submissions_coll = conn.submissions
        materials_coll = conn.materials
        self.mpsft = 

    def test_init(self):
        

    def test_check_for_duplicates(self):
        pass

    def test_submit(self):
        pass

    def test_add_snl_to_submissions(self):
        pass
