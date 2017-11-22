import numpy as np
from datetime import datetime
from itertools import chain

from monty.json import jsanitize

from pymatgen import Structure
from pymatgen.analysis.elasticity.elastic import ElasticTensor
from pymatgen.analysis.elasticity.strain import Strain, Deformation
from pymatgen.analysis.elasticity.stress import Stress
from pymatgen.analysis.structure_matcher import StructureMatcher, ElementComparator
from pymatgen.symmetry.analyzer import SpacegroupAnalyzer

from maggma.builder import Builder

from atomate.utils.utils import get_mongolike, get_structure_metadata

from emmet.vasp.builders.task_tagger import TaskTagger

__author__ = "Joseph Montoya, Shyam Dwaraknath <shyamd@lbl.gov>"


class ElasticBuilder(Builder):
    def __init__(self, tasks, elasticity, materials=None,
                 query={}, **kwargs):
        """
        Creates a elastic collection for materials

        Args:
            tasks (Store): Store of task documents
            elastic (Store): Store of elastic properties
            materials (Store): Store of materials properties
            query (dict): dictionary to limit materials to be analyzed
        """

        self.tasks = tasks
        self.elasticity = elasticity
        self.materials = materials
        self.query = query
        self.kwargs = kwargs

        super().__init__(sources=[tasks],
                         targets=[elasticity],
                         **kwargs)

    def connect(self):
        self.tasks.connect()
        self.elasticity.connect()
        if self.materials:
            self.materials.connect()

    def get_items(self):
        """
        Gets all items to process into materials documents

        Returns:
            generator or list relevant tasks and materials to process into materials documents
        """

        self.logger.info("Elastic Builder Started")
        self.logger.debug("Adding indices")
        self.tasks.ensure_index("parent_structure.spacegroup.number")
        self.tasks.ensure_index("formula_pretty")

        # Get only successful elastic deformation tasks with parent structure
        q = dict(self.query)
        q["state"] = "successful"
        q["task_label"] = "elastic deformation"
        q["parent_structure"] = {"$exists": True}

        # only consider tasks that have been updated since materials was last updated
        # q.update(self.tasks.lu_filter(self.elasticity))

        sm = StructureMatcher(ltol=1e-10, stol=1e-10, angle_tol=1e-10,
                              primitive_cell=False, scale=False,
                              attempt_supercell=False, allow_subset=False,
                              comparator=ElementComparator())
        # TODO: Ensure appropriately selective DFT params - input.incar.GGA, input.incar.ENCUT
        #       for kpoints, designate some cutoff for number
        # TODO: mpworks discrepancy in original input, probably going to just have to
        #       let it lie as a distinguisher between atomate/mpworks
        mutually_exclusive_params = ["formula_pretty", "parent_structure.spacegroup.number"]
        return_props = ['calcs_reversed', 'output', 'input', 'transmuter',
                        'task_id', 'parent_structure']
        self.logger.debug("Getting criteria")
        criterias = self.tasks.distinct(
            ["formula_pretty", "parent_structure.spacegroup.number"], criteria=q)
        self.logger.debug("Found {} unique spacegroup-formula combinations".format(len(criterias)))
        import pdb; pdb.set_trace()
        for n, crit in enumerate(criterias):
            crit.update(q)
            tasks = self.tasks.query(criteria=crit, properties=return_props)

            # Group by parent structure
            task_sets = group_by_structure(tasks, sm=sm)
            for task_set in task_sets:
                if self.materials:
                    struct = task_set[0]
                    mp_id = self._find_mp_id(struct)
                else:
                    mp_id = None
                self.logger.debug("Processing {} : {} of {}".format(
                    crit['formula_pretty'], n, len(criterias)))
                yield task_set

    def process_item(self, item):
        """
        Process the tasks and materials into a dielectrics collection

        Args:
            item: list of deformation tasks

        Returns:
            an elasticity document
        """
        elastic_doc = {"warnings": []}
        parent_structure, task_docs = item
        parent_lattice = parent_structure.lattice.matrix
        def_structures = [Structure.from_dict(d['output']['structure']) for d in task_docs]
        defos = [np.transpose(np.dot(np.linalg.inv(parent_lattice), s.lattice.matrix))
                 for s in def_structures]

        # Issue warnings if deformation is not equivalent to stored deformation
        stored_defos = [d['transmuter']['transformation_params'][0]['deformation'] for d in task_docs]
        defos, stored_defos = np.array(defos), np.array(stored_defos)
        if (np.abs(defos - stored_defos) > 1e-5).any():
            self.logger.warn("Deformations not equivalent to stored deformations.")
            elastic_doc["warnings"].append("inequivalent lattices and stored deformations")
        defos = [Deformation(d) for d in defos]
        strains = [d.green_lagrange_strain for d in defos]
        stresses = [d['calcs_reversed'][0]['output']['ionic_steps'][-1]['stress'] for d in task_docs]
        stresses = [-0.1*Stress(s) for s in stresses]
        pk_stresses = [Stress(s.piola_kirchoff_2(d)) for s, d in zip(stresses, defos)]
        task_ids = [d['task_id'] for d in task_docs]

        # Determine whether data is sufficient to fit tensor
        # If raw data is insufficient but can be symmetrically transformed
        # to provide a sufficient set, use the expanded set with appropriate
        # symmetry transformations, fstresses/strains are "fitting
        # strains" below.
        vstrains = [s.voigt for s in strains]
        if np.linalg.matrix_rank(vstrains) < 6:
            symmops = SpacegroupAnalyzer(parent_structure).get_symmetry_operations()
            fstrains = [[s.transform(symmop) for symmop in symmops] for s in strains]
            fstrains = list(chain.from_iterable(fstrains))
            vfstrains = [s.voigt for s in fstrains]
            if not np.linalg.matrix_rank(vfstrains) == 6:
                self.logger.warn("Insufficient data to form SOEC")
                elastic_doc['warnings'].append("insufficient strains")
                return None
            else:
                fstresses = [[s.transform(symmop) for symmop in symmops] for s in pk_stresses]
                fstresses = list(chain.from_iterable(fstresses))
        else:
            fstrains = strains
            fstresses = pk_stresses

        et_raw = ElasticTensor.from_pseudoinverse(fstrains, fstresses)
        et = et_raw.convert_to_ieee(parent_structure)

        elastic_doc.update({"task_ids": task_ids,
                            "pk_stresses": pk_stresses,
                            "cauchy_stresses": stresses,
                            "strains": strains,
                            "deformations": defos,
                            "elastic_tensor": et,
                            "elastic_tensor_raw": et_raw,
                            "parent_structure": get_structure_metadata(parent_structure)})
        # TODO: process advanced warnings
        # TODO: process MPWorks metadata?
        # TODO: higher order?
        # TODO: fitting method?
        elastic_doc['state'] = "filter_failed" if elastic_doc['warnings'] else "successful"
        return elastic_doc

    def update_targets(self, items):
        """
        Inserts the new elasticity documents into the elasticity collection

        Args:
            items ([dict]): list of elasticity docs
        """
        self.logger.info("Updating {} elastic documents".format(len(items)))


        # self.elasticity.collection.insert_many(items)
        # TODO: group more loosely by material
        for doc in items:
            if doc:
                doc[self.elasticity.lu_field] = datetime.utcnow()
                doc = jsanitize(doc)
                self.elasticity.collection.insert(doc)
                #self.elasticity().replace_one({"material_id": doc['material_id']}, doc, upsert=True)

    """
    def finalize(self):
        # TODO: likely want to group everything by structure here?
        pass
    """
    def _find_mp_id(self, structure, structure_matcher=None):
        sm = structure_matcher or StructureMatcher()
        sga = SpacegroupAnalyzer(structure)
        candidates = self.materials.query(
                ['structure', 'material_id'],
                {"formula_pretty": structure.composition.formula_reduced,
                 "spacegroup.number": sga.space_group.number})
        for candidate in candidates:
            c_structure = Structure.from_dict(candidate['structure'])
            if sm.fit(c_structure, structure):
                return candidate['material_id']

def group_by_structure(docs, sm=None):
    """
    Groups a set of documents by structural equivalence

    Args:
        docs ([{}]): list of documents e. g. dictionaries or cursor
        sm (StructureMatcher): structure matcher to determine structural equivalence
        key (str): key for which to find structures
    """
    sm = sm if sm else StructureMatcher()
    unique_structures = []
    for doc in docs:
        if "parent_structure" in doc:
            structure = Structure.from_dict(get_mongolike(doc, "parent_structure.structure"))
        else:
            structure = Structure.from_dict(get_mongolike(doc, "output.structure"))
        match = False
        for unique_structure in unique_structures:
            if sm.fit(unique_structure[0], structure):
                match = True
                unique_structure[1].append(doc)
                break
        if not match:
            unique_structures.append([structure, [doc]])
    return unique_structures
