import unittest
import os

from emmet.vasp.elastic import *
from maggma.stores import MongoStore
from maggma.runner import Runner
from pymatgen.util.testing import PymatgenTest
from pymatgen.analysis.elasticity.strain import DeformedStructureSet

from monty.serialization import loadfn

__author__ = "Joseph Montoya"
__email__ = "montoyjh@lbl.gov"

module_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)))
test_tasks = os.path.join(module_dir, "..", "..", "..", "test_files", "vasp", "elastic_tasks.json")

DEBUG_MODE = True

class ElasticAnalysisBuilderTest(unittest.TestCase):
    @classmethod
    def setUp(self):
        # Set up test db, set up mpsft, etc.
        self.test_tasks = MongoStore("test_emmet", "tasks")
        self.test_tasks.connect()
        docs = loadfn(test_tasks, cls=None)
        self.test_tasks.update(docs)
        self.test_elasticity = MongoStore("test_emmet", "elasticity")
        self.test_elasticity.connect()

    @classmethod
    def tearDown(self):
        if not DEBUG_MODE:
            self.test_elasticity.collection.drop()
            self.test_tasks.collection.drop()

    def test_builder(self):
        ec_builder = ElasticAnalysisBuilder(
            self.test_tasks, self.test_elasticity, incremental=False)
        ec_builder.connect()
        for t in ec_builder.get_items():
            processed = ec_builder.process_item(t)
            self.assertTrue(bool(processed))
        runner = Runner([ec_builder])
        runner.run()
        # Test warnings
        doc = ec_builder.elasticity.query_one(criteria={"pretty_formula": "NaN3"})
        self.assertEqual(doc['elasticity']['warnings'], None)
        self.assertAlmostEqual(doc['elasticity']['compliance_tensor'][0][0],
                               0.041576072)

    def test_grouping_functions(self):
        docs1 = list(self.test_tasks.query(criteria={"formula_pretty": "NaN3"}))
        docs_grouped1 = group_by_parent_lattice(docs1)
        self.assertEqual(len(docs_grouped1), 1)
        grouped_by_opt = group_deformations_by_optimization_task(docs1)
        self.assertEqual(len(grouped_by_opt), 1)
        docs2 = self.test_tasks.query(criteria={"task_label": "elastic deformation"})
        sgroup2 = group_by_parent_lattice(docs2)

    def test_get_distinct_rotations(self):
        struct = PymatgenTest.get_structure("Si")
        conv = SpacegroupAnalyzer(struct).get_conventional_standard_structure()
        rots = get_distinct_rotations(conv)
        ops = SpacegroupAnalyzer(conv).get_symmetry_operations()
        for op in ops:
            self.assertTrue(any([np.allclose(op.rotation_matrix, r)
                                 for r in rots]))
        self.assertEqual(len(rots), 48)

    def test_process_elastic_calcs(self):
        # docs = list(self.test_tasks.query(criteria={"formula_pretty": "NaN3"}))
        test_struct = PymatgenTest.get_structure('Sn') # use cubic test struct
        dss = DeformedStructureSet(test_struct)
        # Construct test task set
        opt_task = {"output": {"structure": test_struct.as_dict()},
                    "input": {"structure" : test_struct.as_dict()}}
        defo_tasks = []
        for n, (struct, defo) in enumerate(zip(dss, dss.deformations)):
            strain = defo.green_lagrange_strain
            defo_task = {"output": {"structure": struct.as_dict(),
                                    "stress": (strain * 5).tolist()},
                         "input": None, "task_id": n,
                         "completed_at": datetime.utcnow()}
            defo_task.update({"transmuter": {
                "transformation_params": [{"deformation": defo}]}})
            defo_tasks.append(defo_task)

        defo_tasks.pop(0)
        #opt_task['output']['structure'] = test_struct.as_dict()
        explicit, derived = process_elastic_calcs(opt_task, defo_tasks)
        self.assertEqual(len(explicit), 23)
        self.assertEqual(len(derived), 1)


class ElasticAggregateBuilder(unittest.TestCase):
    def setUp(self):
        self.test_elasticity = MongoStore("test_emmet", "elasticity")
        self.test_elasticity.connect()

        # Generate test materials collection
        self.test_materials = MongoStore("test_emmet", "materials")
        self.test_materials.connect()
        mat_docs = [{
            "task_id": "mp-{}".format(n),
            "structure": PymatgenTest.get_structure(formula),
            "pretty_formula": formula
        } for n, formula in enumerate(['Si', 'BaNiO3', 'Li2O2', 'TiO2'])]
        self.test_materials.update(mat_docs, update_lu=False)

    def tearDown(self):
        if not DEBUG_MODE:
            self.test_elasticity.collection.drop()
            self.test_materials.collection.drop()

    def test_materials_aggregator(self):
        materials_dict = generate_formula_dict(self.test_materials)
        grouped_by_mpid = group_by_task_id(
            materials_dict['NaN3'], {})
        self.assertEqual(len(grouped_by_mpid), 1)
        materials_dict = generate_formula_dict(self.test_materials)

    def test_get_items(self):
        builder = ElasticAggregateBuilder()
        cursor = builder.get_items()

    def test_process_items(self):
        builder = ElasticAggregateBuilder()
        test_doc = {"_id": {"formula_pretty": "Si", "":""}}

    def test_aggregation(self):
        pass


if __name__ == "__main__":
    unittest.main()
