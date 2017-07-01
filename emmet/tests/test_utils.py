import unittest
from emmet.utils import get_mongolike, make_mongolike, recursive_update



class UtilsTests(unittest.TestCase):

    def test_get_mongolike(self):
        d = {"a": [{"b": 1}, {"c": {"d": 2}}], "e": {"f": {"g": 3}}, "g": 4, "h":[5, 6]}

        self.assertEqual(get_mongolike(d, "g"), 4)
        self.assertEqual(get_mongolike(d, "e.f.g"), 3)
        self.assertEqual(get_mongolike(d, "a.0.b"), 1)
        self.assertEqual(get_mongolike(d, "a.1.c.d"), 2)
        self.assertEqual(get_mongolike(d, "h.-1"), 6)


    def test_make_mongolike(self):
        d = {"a": [{"b": 1}, {"c": {"d": 2}}], "e": {"f": {"g": 3}}, "g": 4, "h": [5, 6]}

        self.assertEqual(make_mongolike(d, "e.f.g","a"), {"a":3})
        self.assertEqual(make_mongolike(d, "e.f.g", "a.b"), {"a":{"b":3}})
        self.assertEqual(make_mongolike(d, "a.0.b","e.f"), {"e":{"f":1}})

    def test_recursiveupdate(self):

        d = {"a": {"b":3}, "c": [4]}

        recursive_update(d, {"c": [5]})
        self.assertEqual(d["c"],[4,5])

        recursive_update(d,{"a":{"b":5}})
        self.assertEqual(d["a"]["b"],5)

        recursive_update(d, {"a": {"b": [6]}})
        self.assertEqual(d["a"]["b"], [6])

        recursive_update(d, {"a": {"b": [7]}})
        self.assertEqual(d["a"]["b"], [6,7])