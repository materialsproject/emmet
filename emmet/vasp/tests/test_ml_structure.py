import unittest
from pymatgen.core.structure import Structure
from pymatgen.core.lattice import Lattice

from maggma.stores import MongoStore
from emmet.vasp.ml_structures import MLStructuresBuilder

__author__ = "Shyam Dwaraknath"
__email__ = "shyamd@lbl.gov"


class TestML(unittest.TestCase):
    def setUp(self):
        tasks = MongoStore("emmet_test", "tasks")
        ml_strucs = MongoStore("emmet_test", "ml_strucs")

        self.builder = MLStructuresBuilder(tasks, ml_strucs)

    def test_process_item(self):

        dummy_task = {
            "task_id": 1,
            "state": "successful",
            "orig_inputs": {
                "incar": {
                    "IBRION": 2,
                    "ISIF": 3,
                    "NSW": 99
                }
            },
            "calcs_reversed": [{
                "output": {
                    "ionic_steps": []
                }
            }]
        }

        coords = list()
        coords.append([0, 0, 0])
        coords.append([0.75, 0.5, 0.75])
        lattice = Lattice([[3.8401979337, 0.00, 0.00], [1.9200989668, 3.3257101909, 0.00],
                           [0.00, -2.2171384943, 3.1355090603]])
        structure1 = Structure(lattice, ["Si", "Si"], coords)
        coords[1][0] = 0.0
        structure2 = Structure(lattice, ["Si", "Si"], coords)

        dummy_task["calcs_reversed"][0]["input"] = {"incar": {"IBRION": 2, "ISIF": 3, "NSW": 99}}

        ionic_steps = dummy_task["calcs_reversed"][0]["output"]["ionic_steps"]
        ionic_steps.append({"structure": structure1.as_dict()})
        ionic_steps.append({"structure": structure1.as_dict()})

        ml_strucs = self.builder.process_item(dummy_task)

        self.assertEqual(len(ml_strucs), 2)


if __name__ == "__main__":
    unittest.main()
