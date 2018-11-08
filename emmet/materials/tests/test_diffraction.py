from maggma.stores import MongoStore
from pymatgen.util.testing import PymatgenTest
import unittest
from unittest import TestCase
from uuid import uuid4

from emmet.materials.diffraction import DiffractionBuilder


class TestDiffractionBuilder(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dbname = "test_" + uuid4().hex
        s = MongoStore(cls.dbname, "test")
        s.connect()
        cls.client = s.collection.database.client

    @classmethod
    def tearDownClass(cls):
        cls.client.drop_database(cls.dbname)

    def setUp(self):
        kwargs = dict(key="k", lu_field="lu")
        self.source = MongoStore(self.dbname, "source", **kwargs)
        self.target = MongoStore(self.dbname, "target", **kwargs)
        self.source.connect()
        self.source.collection.create_index("lu")
        self.source.collection.create_index("k", unique=True)
        self.target.connect()
        self.target.collection.create_index("lu")
        self.target.collection.create_index("k", unique=True)

    def tearDown(self):
        self.source.collection.drop()
        self.target.collection.drop()

    def test_get_xrd_from_struct(self):
        builder = DiffractionBuilder(self.source, self.target)
        structure = PymatgenTest.get_structure("Si")
        self.assertIn("Cu", builder.get_xrd_from_struct(structure))

    def test_serialization(self):
        builder = DiffractionBuilder(self.source, self.target)
        self.assertIsNone(builder.as_dict()["xrd_settings"])

if __name__ == "__main__":
    unittest.main()
