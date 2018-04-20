from datetime import datetime, timedelta
from unittest import TestCase
from uuid import uuid4

from maggma.stores import MongoStore
from maggma.runner import Runner
from emmet.common.copybuilder import CopyBuilder


class TestCopyBuilder(TestCase):
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
        tic = datetime.now()
        toc = tic + timedelta(seconds=1)
        keys = list(range(20))
        self.old_docs = [{"lu": tic, "k": k, "v": "old"}
                         for k in keys]
        self.new_docs = [{"lu": toc, "k": k, "v": "new"}
                         for k in keys[:10]]
        kwargs = dict(key="k", lu_field="lu")
        self.source = MongoStore(self.dbname, "source", **kwargs)
        self.target = MongoStore(self.dbname, "target", **kwargs)
        self.builder = CopyBuilder(self.source, self.target)
        self.source.connect()
        self.source.collection.create_index("lu")
        self.target.connect()
        self.target.collection.create_index("k")

    def tearDown(self):
        self.source.collection.drop()
        self.target.collection.drop()

    def test_get_items(self):
        self.source.collection.insert_many(self.old_docs)
        self.assertEqual(len(list(self.builder.get_items())),
                         len(self.old_docs))
        self.target.collection.insert_many(self.old_docs)
        self.assertEqual(len(list(self.builder.get_items())), 0)
        self.source.update(self.new_docs, update_lu=False)
        self.assertEqual(len(list(self.builder.get_items())),
                         len(self.new_docs))

    def test_process_item(self):
        self.source.collection.insert_many(self.old_docs)
        items = list(self.builder.get_items())
        self.assertCountEqual(items, map(self.builder.process_item, items))

    def test_update_targets(self):
        self.source.collection.insert_many(self.old_docs)
        self.source.update(self.new_docs, update_lu=False)
        self.target.collection.insert_many(self.old_docs)
        items = list(map(self.builder.process_item, self.builder.get_items()))
        self.builder.update_targets(items)
        self.assertTrue(self.target.query_one(criteria={"k": 0})["v"], "new")
        self.assertTrue(self.target.query_one(criteria={"k": 10})["v"], "old")

    def test_confirm_lu_field_index(self):
        self.source.collection.drop_index("lu_1")
        with self.assertRaises(Exception) as cm:
            self.builder.get_items()
        self.assertTrue(cm.exception.args[0].startswith("Need index"))
        self.source.collection.create_index("lu")

    def test_runner(self):
        self.source.update(self.old_docs)
        runner = Runner([self.builder])
        runner.run()
        self.assertTrue(self.target.query_one(criteria={"k": 0})["v"], "new")
        self.assertTrue(self.target.query_one(criteria={"k": 10})["v"], "old")
