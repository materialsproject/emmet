from itertools import chain
from collections import defaultdict

from pymatgen import Structure
from pymatgen.analysis.structure_matcher import StructureMatcher, ElementComparator
from pymatgen.util.provenance import StructureNL
from maggma.builder import Builder


class SNLBuilder(Builder):
    """
    Builds SNL collection for materials

    Uses `lu_field` to get new/updated documents,
    and uses a `key` field to determine which documents to merge together

    """

    def __init__(self, materials, source_snls, snls, query={}, ltol=0.2, stol=0.3,
                 angle_tol=5, **kwargs):
        self.materials = materials
        self.snls = snls
        self.source_snls = list(source_snls)
        self.ltol = ltol
        self.stol = stol
        self.angle_tol = angle_tol
        self.query = query
        self.kwargs = kwargs

        super(SNLBuilder, self).__init__(sources=[materials, *self.source_snls], targets=[snls], **kwargs)

    def get_items(self):
        """
        Gets all materials to assocaite with SNLs

        Returns:
            generator of materials and SNLs that could match
        """
        self.logger.info("SNL Builder Started")

        self.logger.info("Setting indexes")
        self.ensure_indexes()

        # Find all formulas for materials that have been updated since this builder was last ran
        q = dict(self.query)
        q.update(self.materials.lu_filter(self.snls))
        forms_to_update = set(self.materials().find(q).distinct("pretty_formula"))
        #forms_to_update = set()

        # Find all new SNL formulas since the builder was last run
        for source in self.source_snls:
            new_q = source.lu_filter(self.snls)
            forms_to_update |= set(source().find(new_q).distinct("reduced_cell_formula"))

        self.logger.info("Found {} new/updated systems to proces".format(len(forms_to_update)))

        for formula in forms_to_update:
            mats = list(self.materials().find({"pretty_formula": formula}, {"material_id": 1, "structure": 1}))
            snls = []

            for source in self.source_snls:
                snls.extend(source().find({"reduced_cell_formula": formula}))
            if len(mats) > 0 and len(snls) > 0:
                print("Running")
                yield mats, snls

    def process_item(self, item):
        """
        Calculates diffraction patterns for the structures

        Args:
            item (tuple): a tuple of materials and snls

        Returns:
            list(dict): a list of collected snls with material ids
            """
        mats = item[0]
        source_snls = item[1]
        snls = defaultdict(list)

        self.logger.debug("Tagging SNLs for {}".format(mats[0].composition))

        for snl in source_snls:

            mat_id = self.match(snl, mats)
            if mat_id is not None:
                snls[mat_id].append(snl)

        return snls

    def match(self, snl, mats):
        """
        Finds a material doc that matches with the given snl

        Args:
            snl (dict): the snl doc
            mats ([dict]): the materials docs to match against

        Returns:
            dict: a materials doc if one is found otherwise returns None
        """
        sm = StructureMatcher(ltol=self.ltol, stol=self.stol, angle_tol=self.angle_tol,
                              primitive_cell=True, scale=True,
                              attempt_supercell=False, allow_subset=False,
                              comparator=ElementComparator())
        snl_struc = StructureNL.from_dict(snl)

        for m in mats:
            m_struct = Structure.from_dict(m["structure"])
            init_m_struct = Structure.from_dict(m["initial_structure"])
            if sm.fit(m_struct, snl_struc) or sm.fit(init_m_struct,snl_struc):
                return m['material_id']

        return None

    def update_targets(self, items):
        """
        Inserts the new task_types into the task_types collection

        Args:
            items ([([dict],[int])]): A list of tuples of materials to update and the corresponding processed task_ids
        """
        mat_snls  = {}
        for d in items:
            mat_snls.update(d)

        if len(mat_snls) > 0:
            self.logger.info("Updating {} materials".format(len(mat_snls)))
            bulk = self.snls().initialize_ordered_bulk_op()
            for mat,snls in mat_snls.items():
                d = {"material_id": mat,
                     "snls": snls,
                     self.snls.lu_field: datetime.utcnow()
                     }
                bulk.find({"material_id": m["material_id"]}).upsert().replace_one(d)
            bulk.execute()
        else:
            self.logger.info("No items to update")

    def ensure_indexes(self):
        """
        Ensures indexes on the tasks and materials collections
        :return:
        """
        # Search index for materials
        self.materials().create_index("material_id", unique=True, background=True)
