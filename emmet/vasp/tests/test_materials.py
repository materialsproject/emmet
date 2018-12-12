import unittest
from maggma.stores import MongoStore
from pymatgen.core.structure import Structure
from pymatgen.core.lattice import Lattice
from emmet.vasp.materials import MaterialsBuilder

__author__ = "Shyam Dwaraknath"
__email__ = "shyamd@lbl.gov"


class TestMaterials(unittest.TestCase):
    def setUp(self):
        coords = list()
        coords.append([0, 0, 0])
        coords.append([0.75, 0.5, 0.75])
        lattice = Lattice([[3.8401979337, 0.00, 0.00], [1.9200989668, 3.3257101909, 0.00],
                           [0.00, -2.2171384943, 3.1355090603]])
        self.structure = Structure(lattice, ["Si", "Si"], coords)

        tasks = MongoStore("emmet_test", "tasks")
        materials = MongoStore("emmet_test", "materials")

        self.mbuilder = MaterialsBuilder(tasks, materials, mat_prefix="", chunk_size=1)

    def test_make_mat(self):
        struc1 = self.structure.copy()
        struc2 = self.structure.copy()
        struc2.translate_sites(1, [0.5, 0, 0])
        tasks = [{
            "task_id": "mp-1",
            "orig_inputs": {
                "incar": {
                    "LDAU": True,
                    "ISIF": 3,
                    "IBRION": 1
                }
            },
            "output": {
                "structure": struc1.as_dict(),
                "bandgap": 1.3
            },
            "formula_anonymous": "A",
            "formula_pretty": "Cl",
            "last_updated": "Never"
        }, {
            "task_id": "mp-2",
            "orig_inputs": {
                "incar": {
                    "LDAU": True,
                    "ICHARG": 11,
                    "IBRION": 1
                }
            },
            "output": {
                "structure": struc2.as_dict(),
                "bandgap": 2
            },
            "formula_anonymous": "A",
            "formula_pretty": "Cl",
            "last_updated": "Never"
        }]

        mat = self.mbuilder.make_mat(tasks)
        self.assertEqual(set(mat["task_ids"]), {"mp-1", "mp-2"})

        for k in [
                "task_ids", "task_id", "origins", "task_types", "formula_anonymous", "bandstructure", "inputs",
                "formula_pretty", "structure"
        ]:
            self.assertIn(k, mat)
        self.assertIn(self.mbuilder.materials.lu_field, mat)

    def test_filter_and_group_tasks(self):
        si = self.structure
        si2 = si.copy()
        si2.translate_sites(1, [0.5, 0, 0])
        si3 = si.copy()
        si3.make_supercell(2)
        si4 = si.copy()
        si4.make_supercell(2)
        si4.translate_sites(1, [0.1, 0, 0])

        incar = {"incar": {"LDAU": True, "ISIF": 3, "IBRION": 1}}

        task1 = {"output": {"structure": si.as_dict()}, "task_id": "mp-1", "orig_inputs": incar}
        task2 = {"output": {"structure": si2.as_dict()}, "task_id": "mp-2", "orig_inputs": incar}
        task3 = {"output": {"structure": si3.as_dict()}, "task_id": "mp-3", "orig_inputs": incar}
        task4 = {"output": {"structure": si4.as_dict()}, "task_id": "mp-4", "orig_inputs": incar}

        grouped_tasks = list(self.mbuilder.filter_and_group_tasks([task1, task2, task3, task4]))

        self.assertEqual(len(grouped_tasks), 3)

        task_ids = [[t["task_id"] for t in tasks] for tasks in grouped_tasks]
        self.assertIn(["mp-2"], task_ids)

    def test_task_to_prop_list(self):
        task = {
            "task_id": "mp-3",
            "orig_inputs": {
                "incar": {
                    "LDAU": True,
                    "ISIF": 3,
                    "IBRION": 1
                }
            },
            "output": {
                "bandgap": 1.3,
                "structure": "What structure"
            },
            "formula_anonymous": "A",
            "formula_pretty": "Cl",
            "last_updated": "Never"
        }

        prop_list = self.mbuilder.task_to_prop_list(task)
        for p in prop_list:
            self.assertIn("value", p)
            self.assertIn("task_type", p)
            self.assertIn("quality_score", p)
            self.assertIn("track", p)
            self.assertIn("last_updated", p)
            self.assertIn("task_id", p)
            self.assertIn("materials_key", p)

        prop_names = [p["materials_key"] for p in prop_list]
        props_in = ['structure', 'inputs.structure_optimization', 'bandstructure.band_gap']
        props_not_in = [
            'formula_anonymous', 'formula_pretty', 'bandstructure.cbm', 'bandstructure.vbm',
            'chemsys', 'analysis.delta_volume', 'thermo.energy'
        ]

        for p in props_in:
            self.assertIn(p, prop_names)

        for p in props_not_in:
            self.assertNotIn(p, prop_names)


if __name__ == "__main__":
    unittest.main()
