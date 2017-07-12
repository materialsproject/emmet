import logging
import numpy as np

from pymatgen import Structure
from pymatgen.analysis.elasticity.elastic import ElasticTensor
from pymatgen.analysis.elasticity.strain import IndependentStrain, Strain
from pymatgen.analysis.elasticity.stress import Stress
from pymatgen.analysis.structure_matcher import StructureMatcher, ElementComparator

from maggma.builder import Builder

__author__ = "Shyam Dwaraknath <shyamd@lbl.gov>"


class ElasticBuilder(Builder):
    def __init__(self, materials, elastic, query={}, **kwargs):
        """
        Creates a dielectric collection for materials

        Args:
            tasks (Store): Store of task documents
            materials (Store): Store of materials documents to match to
            dielectric (Store): Store of dielectric properties
            query (dict): dictionary to limit materials to be analyzed
        """

        self.tasks = tasks
        self.materials = materials
        self.elastic = elastic
        self.query = query


        self.__logger = logging.getLogger(__name__)
        self.__logger.addHandler(logging.NullHandler())

        super().__init__(sources=[materials],
                         targets=[elastic],
                         **kwargs)

    def get_items(self):
        """
        Gets all items to process into materials documents

        Returns:
            generator or list relevant tasks and materials to process into materials documents
        """

        self.__logger.info("Elastic Builder Started")
        q = dict(self.query)
        q.update(self.materials.lu_filter(self.elastic))

        # Find all materials that have changed since last run
        mats = self.materials.find(q, {"material_id": 1}).count()

        self.__logger.info("Found {} new materials for elastic calculations".format(mats))

        # Fancy MongoDB Aggregation
        # 1.) Finds all mats that have changed within our query specs
        # 2.) lookups all other materials that have the same reduced_cell_formula
        # 3.) Project the material ids for these
        mat_sets = self.materials().aggregate([{"$match": q},
                                               {"$project": {"reduced_cell_formula": 1}},
                                               {"$lookup": {"from": self.materials().name,
                                                            "localField": "reduced_cell_formula",
                                                            "foreignField": "reduced_cell_formula",
                                                            "as": "mats"}}
                                               ])

        return mat_sets

    def process_item(self, item):
        """
        Process the tasks and materials into a dielectrics collection

        Args:
            item dict: a dict of material_id, structure, and tasks

        Returns:
            dict: a dieletrics dictionary  
        """
        root_mats = [mat for mat in item["mats"] if mat.get("inputs", {}).get("structure optimization", None)]
        deform_mats = [mat for mat in item["mats"] if mat not in root_mats]
        docs = []

        # TODO: What structure matcher parameters to use?
        # TODO: Should SM parameters be configurable?
        sm = StructureMatcher(primitive_cell=True, scale=True,
                              attempt_supercell=False, allow_subset=False,
                              comparator=ElementComparator())

        for r_mat in root_mats:

            # Enumerate over all deformations
            r_struc = Structure.from_dict(r_mat['initial_structure'])

            defos = []
            stresses = []
            strains = []
            m_ids = []

            for d_mat in deform_mats:
                # Find deformation matrix
                d_struc = Structure.from_dict(d_mat["initial_structure"])
                transform_matrix = np.transpose(np.linalg.solve(r_struc.lattice.matrix,
                                                                d_struc.lattice.matrix))
                # apply deformation matrix to root_mat and check if the two structures match
                dfm = Deformation(transform_matrix)
                dfm_struc = dfm.apply_to_structure(r_struc)

                # if match store stress and strain matrix
                if sm.fit(dfm_struc, d_struc):
                    # This is a deformtion of the root struc
                    defos.append(dfm)
                    stresses.append(d_mat['stress'])
                    strains.append(dfm.green_lagrange_strain)
                    m_ids.append(d_mat['material_id'])

            stress_dict = {IndependentStrain(defo): Stress(stress) for defo, stress in zip(defos, stresses)}

            self.__logger.info("Analyzing stress/strain data")

            # Determine if we have 6 unique deformations
            if np.linalg.matrix_rank(strains) == 6:
                # Perform Elastic tensor fitting and analysis
                result = ElasticTensor.from_stress_dict(stress_dict)

                d = {"material_id": r_mat["material_id"],
                     "elasticity": {
                         "elastic_tensor": result.voigt.tolist(),
                         "material_ids": m_ids}
                     }

                d["elasticity"].update(result.property_dict)

                docs.append(d)
            else:
                self.__logger.warn("Fewer than 6 unique deformations for {}".format(r_mat["material_id"]))

        return docs

    def update_targets(self, items):
        """
        Inserts the new task_types into the task_types collection

        Args:
            items ([([dict],[int])]): A list of tuples of materials to update and the corresponding processed task_ids
        """

        self.__logger("Updating {} diffraction documents".format(len(items)))

        for doc in items:
            doc[self.elasticity.lu_field] = datetime.utcnow()
            self.elasticity().replace_one({"material_id": doc['material_id']}, doc, upsert=True)

    def finalize(self):
        pass
