import unittest
import os
from datetime import datetime
import numpy as np
from itertools import product
import cProfile
from pstats import Stats

from emmet.vasp.elastic import ElasticAnalysisBuilder, ElasticAggregateBuilder,\
    group_deformations_by_optimization_task, group_by_parent_lattice,\
    get_distinct_rotations, process_elastic_calcs, generate_formula_dict,\
    group_by_material_id
from maggma.stores import MongoStore
from maggma.runner import Runner
from pymatgen.util.testing import PymatgenTest
from pymatgen.analysis.elasticity.strain import DeformedStructureSet, Strain
from pymatgen.analysis.elasticity.elastic import ElasticTensor
from pymatgen.core.tensors import symmetry_reduce
from pymatgen.symmetry.analyzer import SpacegroupAnalyzer
from atomate.vasp.workflows.base.elastic import get_default_strain_states

from monty.serialization import loadfn

__author__ = "Joseph Montoya"
__email__ = "montoyjh@lbl.gov"

module_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)))
test_tasks = os.path.join(module_dir, "..", "..", "..", "test_files",
                          "vasp", "elastic_tasks.json")

DEBUG_MODE = False
PROFILE_MODE = False

# TODO: add TOEC functionality test
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
        if PROFILE_MODE:
            self.pr = cProfile.Profile()
            self.pr.enable()
            print("\n<<<---")

    @classmethod
    def tearDown(self):
        if not DEBUG_MODE:
            self.test_elasticity.collection.drop()
            self.test_tasks.collection.drop()
        if PROFILE_MODE:
            p = Stats(self.pr)
            p.strip_dirs()
            p.sort_stats('cumtime')
            p.print_stats()
            print("\n--->>>")

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
        self.assertEqual(doc['warnings'], None)
        self.assertAlmostEqual(doc['compliance_tensor'][0][0],
                               41.576072, 6)

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
        explicit, derived = process_elastic_calcs(opt_task, defo_tasks)
        self.assertEqual(len(explicit), 23)
        self.assertEqual(len(derived), 1)

    def test_process_elastic_calcs_toec(self):
        # Test TOEC tasks
        test_struct = PymatgenTest.get_structure('Sn') # use cubic test struct
        strain_states = get_default_strain_states(3)
        # Default stencil in atomate, this maybe shouldn't be hard-coded
        stencil = np.linspace(-0.075, 0.075, 7)
        strains = [Strain.from_voigt(s * np.array(strain_state))
                   for s, strain_state in product(stencil, strain_states)]
        strains = [s for s in strains if not np.allclose(s, 0)]
        sym_reduced = symmetry_reduce(strains, test_struct)
        opt_task = {"output": {"structure": test_struct.as_dict()},
                    "input": {"structure" : test_struct.as_dict()}}
        defo_tasks = []
        for n, strain in enumerate(sym_reduced):
            defo = strain.get_deformation_matrix()
            new_struct = defo.apply_to_structure(test_struct)
            defo_task = {"output": {"structure": new_struct.as_dict(),
                                    "stress": (strain * 5).tolist()},
                         "input": None, "task_id": n,
                         "completed_at": datetime.utcnow()}
            defo_task.update({"transmuter": {
                "transformation_params": [{"deformation": defo}]}})
            defo_tasks.append(defo_task)
        explicit, derived = process_elastic_calcs(opt_task, defo_tasks)
        self.assertEqual(len(explicit), len(sym_reduced))
        self.assertEqual(len(derived), len(strains) - len(sym_reduced))
        for calc in derived:
            self.assertTrue(np.allclose(
                calc['strain'], calc['cauchy_stress'] / -0.5))


class ElasticAggregateBuilderTest(unittest.TestCase):
    def setUp(self):
        # Empty aggregated collection
        self.test_elasticity_agg = MongoStore("test_emmet", "elasticity_agg")
        self.test_elasticity_agg.connect()

        # Generate test materials collection
        self.test_materials = MongoStore("test_emmet", "materials")
        self.test_materials.connect()
        mat_docs = []
        for n, formula in enumerate(['Si', 'BaNiO3', 'Li2O2', 'TiO2']):
            structure = PymatgenTest.get_structure(formula)
            structure.add_site_property("magmoms", [0.0] * len(structure))
            mat_docs.append({
            "task_id": "mp-{}".format(n),
            "structure": structure.as_dict(),
            "pretty_formula": formula})
        self.test_materials.update(mat_docs, update_lu=False)

        # Create elasticity collection and add docs
        self.test_elasticity = MongoStore("test_emmet", "elasticity",
                                          key="optimization_task_id")
        self.test_elasticity.connect()

        si = PymatgenTest.get_structure("Si")
        si.add_site_property("magmoms", [0.0] * len(si))
        et = ElasticTensor.from_voigt(
            [[50, 25, 25, 0, 0, 0],
             [25, 50, 25, 0, 0, 0],
             [25, 25, 50, 0, 0, 0],
             [0, 0, 0, 75, 0, 0],
             [0, 0, 0, 0, 75, 0],
             [0, 0, 0, 0, 0, 75]])
        doc = {"input_structure": si.copy().as_dict(),
               "order": 2,
               "magnetic_type": "non-magnetic",
               "optimization_task_id": "mp-1",
               "last_updated": datetime.utcnow(),
               "completed_at": datetime.utcnow(),
               "optimized_structure": si.copy().as_dict(),
               "pretty_formula": "Si", "state": "successful"}
        doc['elastic_tensor'] = et.voigt
        doc.update(et.property_dict)
        self.test_elasticity.update([doc])
        # Insert second doc with diff params
        si.perturb(0.005)
        doc.update({"optimized_structure": si.copy().as_dict(),
                    "updated_at": datetime.utcnow(),
                    "optimization_task_id": "mp-5"})
        self.test_elasticity.update([doc])
        self.builder = self.get_a_new_builder()

    def tearDown(self):
        if not DEBUG_MODE:
            self.test_elasticity.collection.drop()
            self.test_elasticity_agg.collection.drop()
            self.test_materials.collection.drop()

    def test_materials_aggregator(self):
        materials_dict = generate_formula_dict(self.test_materials)
        docs = []
        grouped_by_mpid = group_by_material_id(
            materials_dict['Si'],
            [{'structure': PymatgenTest.get_structure('Si').as_dict(),
              'magnetic_type': "non-magnetic"}])
        self.assertEqual(len(grouped_by_mpid), 1)
        materials_dict = generate_formula_dict(self.test_materials)

    def test_get_items(self):
        iterator = self.builder.get_items()
        for item in iterator:
            self.assertIsNotNone(item)

    def test_process_items(self):
        docs = list(self.test_elasticity.query(criteria={"pretty_formula": "Si"}))
        formula_dict = generate_formula_dict(self.test_materials)
        processed = self.builder.process_item((docs, formula_dict['Si']))
        self.assertEqual(len(processed), 1)
        self.assertEqual(len(processed[0]['all_elastic_fits']), 2)

    def test_update_targets(self):
        processed = [self.builder.process_item(item)
                     for item in self.builder.get_items()]
        self.builder.update_targets(processed)

    def test_aggregation(self):
        runner = Runner([self.builder])
        runner.run()
        all_agg_docs = list(self.test_elasticity_agg.query())
        self.assertTrue(bool(all_agg_docs))

    def get_a_new_builder(self):
        return ElasticAggregateBuilder(
            self.test_elasticity, self.test_materials, self.test_elasticity_agg)


if __name__ == "__main__":
    unittest.main()
