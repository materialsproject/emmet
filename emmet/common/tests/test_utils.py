from unittest import TestCase
from copy import copy
from emmet.common.utils import scrub_class_and_module


class TestUtils(TestCase):
    def test_scrub_class_and_module(self):
        doc = {"@class": 1, "@module": 1, "this": 5}
        new = scrub_class_and_module(doc)
        self.assertEqual(new, {"this": 5})

        list_of_docs = [copy(doc) for n in range(5)]
        new = scrub_class_and_module(list_of_docs)
        for new_doc in new:
            self.assertEqual(new_doc, {"this": 5})

        nested_dict = {"this": {"that": {"@class": 1, "@module": 2, "those": 3}},
                       "these": list_of_docs}
        new = scrub_class_and_module(nested_dict)
        self.assertEqual(new['this'], {"that": {"those": 3}})
        for new_doc in new['these']:
            self.assertEqual(new_doc, {"this": 5})
