import warnings
from configparser import ConfigParser
import itertools
import logging
import os
import unittest

from mongogrant import Client
from monty.serialization import loadfn
from pymatgen import MPRester
import pymongo

from emmet.common.utils import get_chemsys_space

TESTFILES_DIR = os.path.dirname(os.path.abspath(__file__))


def get_aliases(namespace='mg_core_materials'):
    config_file = os.path.join(TESTFILES_DIR, 'field_aliases.cfg')
    config = ConfigParser()
    with open(config_file) as f:
        config.read_file(f)
    return dict(config.items(namespace))


aliases = get_aliases()
supported_fields = {
    aliases.get(field, field)
    for field in MPRester.supported_properties
}
supported_fields.discard("icsd_id")

optional_fields = set(["elasticity", "piezo", "diel"])
required_fields = supported_fields - optional_fields


@unittest.skipIf("TRAVIS" in os.environ and os.environ["TRAVIS"] == "true", "Skipping this test on Travis CI.")
class TestMaterialsDb(unittest.TestCase):
    mats_stag: pymongo.collection.Collection
    mats_prod: pymongo.collection.Collection

    @classmethod
    def setUpClass(cls):
        cls.client = Client()
        cls.db_stag = cls.client.db("ro:staging/mp_core")
        cls.db_prod = cls.client.db("ro:prod/mp_emmet_prod")
        cls.mats_stag = cls.db_stag.materials
        cls.mats_prod = cls.db_prod.materials

        idset_stag = set(cls.mats_stag.distinct("task_id"))
        idset_prod = set(cls.mats_prod.distinct("task_id"))

        n_new_ids = len(idset_stag - idset_prod)
        if n_new_ids:
            logging.info("{} new material ids".format(n_new_ids))
        n_retiring_ids = len(idset_prod - idset_stag)
        if n_retiring_ids:
            logging.warning("{} retiring material ids".format(n_retiring_ids))

    def test_nmats_nondecreasing(self):
        nmats_prod = self.mats_prod.estimated_document_count()
        nmats_stag = self.mats_stag.estimated_document_count()
        self.assertGreaterEqual(nmats_stag, nmats_prod)

    def test_hull_breaks(self):
        """Are materials on hull in prod no longer on hull in staging?"""
        onhull_prod = self.mats_prod.distinct("task_id", {"e_above_hull": 0})
        onhull_stag = self.mats_stag.distinct("task_id", {"e_above_hull": 0})
        onhull_prod_but_not_stag = set(onhull_prod) - set(onhull_stag)
        if onhull_prod_but_not_stag:
            warnings.warn(
                f"Materials on hull in prod no longer on hull in staging. "
                f"{len(onhull_prod_but_not_stag)} mats off hull. You may wish to run "
                "`python report_ehull_breaks.py` to examine hull breaks in detail."
            )
        self.assertTrue(True)

    def test_presence_of_required_fields(self):
        nmats_stag = self.mats_stag.estimated_document_count()
        for field in required_fields:
            self.assertEqual(
                self.mats_stag.count_documents({field: {"$exists": True}}),
                nmats_stag,
                msg="{}".format(field)
            )

    def test_one_mat_per_taskid(self):
        unfaithful_taskids = list(self.mats_stag.aggregate([
            {"$project": {"task_ids": 1}},
            {"$unwind": "$task_ids"},
            {"$sortByCount": "$task_ids"},
            {"$match": {"count": {"$gt": 1}}},
        ]))
        self.assertEqual(len(unfaithful_taskids), 0)

    def test_nprops_nondecreasing(self):
        for prop in self.mats_prod.distinct("has"):
            n_prod = self.mats_prod.count_documents({"has": prop})
            n_stag = self.mats_stag.count_documents({"has": prop})
            self.assertGreaterEqual(
                n_stag, n_prod, "{}: {} in prod but {} in staging".format(
                    prop, n_prod, n_stag))

    @unittest.skip("Many of these calculations need to be redone.")
    def test_piezo_og_formulae_present(self):
        base = loadfn(
            os.path.join(TESTFILES_DIR, 'piezo_formulae_dryad-2015-09-29.json'))
        upstream = self.mats_stag.distinct("pretty_formula", {"has": "piezo"})
        diff = set(base) - set(upstream)
        print(sorted(diff))
        self.assertEqual(len(diff), 0)

    def test_kpoints_serialization(self):
        count = self.mats_stag.count_documents({'input.kpoints.@module': {'$regex': '^pymatgen.io.vaspio'}})
        self.assertEqual(count, 0)

    def test_mid_in_task_ids(self):
        missing = list(self.mats_stag.find({}, ["task_id"]).where("this.task_ids.indexOf(this.task_id) == -1"))
        self.assertEqual(len(missing), 0)

    @unittest.skip("Not just due to tags:mp_scan tasks. Some old MPWorks tasks have structures that don't match.")
    def test_taskcoll_tid_in_task_ids(self):
        taskcoll_tids = set(self.db_stag.tasks.distinct("task_id"))
        matcoll_tids = set(itertools.chain.from_iterable(
            d["task_ids"] for d in self.db_stag.materials.find({}, {"task_ids": 1, "_id": 0})))
        diff = taskcoll_tids - matcoll_tids
        if diff:
            print(list(diff)[:10])
        self.assertEqual(len(diff), 0)

    def test_doi_bibtex_for_doi(self):
        cursor = self.mats_stag.find({"doi": {"$exists": True}}, ["doi", "doi_bibtex"])
        for doc in cursor:
            self.assertIn("doi_bibtex", doc)


    @classmethod
    def tearDownClass(cls):
        cls.db_stag.client.close()
        cls.db_prod.client.close()
