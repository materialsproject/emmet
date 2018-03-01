from itertools import chain
from collections import defaultdict

from pymatgen import Structure
from pymatgen.analysis.structure_matcher import StructureMatcher, ElementComparator
from pymatgen.util.provenance import StructureNL
from maggma.builder import Builder
from pydash.objects import get


class SNLBuilder(Builder):
    """
    Builds SNL collection for materials
    """

    def __init__(self, materials, snls, *source_snls, query=None, ltol=0.2, stol=0.3,
                 angle_tol=5, **kwargs):
        self.materials = materials
        self.snls = snls
        self.source_snls = list(source_snls)
        self.ltol = ltol
        self.stol = stol
        self.angle_tol = angle_tol
        self.query = query if query else {}
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

        # Find all formulas for materials that have been updated since this
        # builder was last ran
        q = dict(self.query)
        q.update(self.materials.lu_filter(self.snls))
        forms_to_update = set(self.materials.distinct("pretty_formula", q))
        #forms_to_update = set()

        # Find all new SNL formulas since the builder was last run
        # for source in self.source_snls:
        #    new_q = source.lu_filter(self.snls)
        #    forms_to_update |= set(source.distinct("reduced_cell_formula", new_q))

        self.logger.info(
            "Found {} new/updated systems to proces".format(len(forms_to_update)))

        for formula in forms_to_update:
            mats = list(self.materials.query(properties=[
                        self.materials.key, "structure", "initial_structure", "pretty_formula"], criteria={"pretty_formula": formula}))
            snls = []

            for source in self.source_snls:
                snls.extend(source.query(criteria={"reduced_cell_formula": formula}))

            #snls = [s["snl"] for s in snls]
            self.logger.debug("Found {} snls and {} mats".format(len(snls), len(mats)))
            if len(mats) > 0 and len(snls) > 0:
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
        self.logger.debug("Tagging SNLs for {}".format(
            mats[0]["pretty_formula"]))

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
        snl_struc = StructureNL.from_dict(snl).structure

        for m in mats:
            m_struct = Structure.from_dict(m["structure"])
            init_m_struct = Structure.from_dict(m["initial_structure"])
            if sm.fit(m_struct, snl_struc) or sm.fit(init_m_struct, snl_struc):
                return m[self.materials.key]

        return None

    def update_targets(self, items):
        """
        Inserts the new task_types into the task_types collection

        """

        snls = [snl for snl_dict in items for snl in self.collect_snls_mp(snl_dict)]

        if len(snls) > 0:
            self.logger.info("Found {} SNLs to update".format(len(snls)))
            self.snls.update(snls)
        else:
            self.logger.info("No items to update")

    def collect_snls_mp(self, snl_dict):
        """
        Converts a dict of materials and snls into docs for the snl by choosing the first by creation date and storing all applicable ICSD ids
        """

        snls = []

        for mat_id, snl_list in snl_dict.items():
            snl = sorted(
                snl_list, key=lambda x: StructureNL.from_dict(x).created_at)[0]
            icsd_ids = list(filter(None, [get(snl, "about._icsd.icsd_id", None) for snl in snl_list]))
            snls.append({self.snls.key: mat_id, "snl": snl, "icsd_ids": icsd_ids})
        return snls
