from itertools import chain
from collections import defaultdict
import logging

from pydash.objects import get

from pymatgen import Structure
from pymatgen.analysis.structure_matcher import StructureMatcher, ElementComparator
from pymatgen.util.provenance import StructureNL
from maggma.builder import Builder
from pybtex.database import parse_string
from pybtex.database import BibliographyData

mp_default_snl_fields = {
    "references":
        "@article{Jain2013,\nauthor = {Jain, Anubhav and Ong, Shyue Ping and "
        "Hautier, Geoffroy and Chen, Wei and Richards, William Davidson and "
        "Dacek, Stephen and Cholia, Shreyas and Gunter, Dan and Skinner, David "
        "and Ceder, Gerbrand and Persson, Kristin a.},\n"
        "doi = {10.1063/1.4812323},\nissn = {2166532X},\n"
        "journal = {APL Materials},\nnumber = {1},\npages = {011002},\n"
        "title = {{The Materials Project: A materials genome approach to "
        "accelerating materials innovation}},\n"
        "url = {http://link.aip.org/link/AMPADS/v1/i1/p011002/s1\\&Agg=doi},\n"
        "volume = {1},\nyear = {2013}\n}\n\n@misc{MaterialsProject,\n"
        "title = {{Materials Project}},\nurl = {http://www.materialsproject.org}\n}",
    "authors": [{
        "name": "Materials Project",
        "email": "feedback@materialsproject.org"
    }],
    "history": {
        "name": "Materials Project Optimized Structure",
        "url": "http://www.materialsproject.org",
        "description": {}
    }
}


class SNLBuilder(Builder):
    """
    Builds a collection of materials with their corresponding SNL list
    """

    def __init__(self,
                 materials,
                 snls,
                 source_snls,
                 query=None,
                 ltol=0.2,
                 stol=0.3,
                 angle_tol=5,
                 default_snl_fields=None,
                 **kwargs):
        """
        Args:
            materials (Store): Store of materials docs to tag with SNLs
            snls (Store): Store to update with tagged SNLs
            source_snls ([Store]): List of locations to grab SNLs
            query (dict): query on materials to limit search
            ltol (float):  Length tolerance for structure matching
            stol (float): site tolerance for structure matching
            angle_tol (float): angle tolerance for structure matching
            default_ref (str): string of bibtex entries to add by default
                to every document
        """
        self.materials = materials
        self.snls = snls
        self.source_snls = list(source_snls)
        self.ltol = ltol
        self.stol = stol
        self.angle_tol = angle_tol
        self.query = query if query else {}
        self.default_snl_fields = default_snl_fields if default_snl_fields\
            else mp_default_snl_fields
        self.kwargs = kwargs

        super(SNLBuilder, self).__init__(sources=[materials, *self.source_snls],
                                         targets=[snls], **kwargs)

    def ensure_indicies(self):

        self.materials.ensure_index(self.materials.key, unique=True)
        self.materials.ensure_index("formula_pretty")

        self.snls.ensure_index(self.snls.key, unique=True)
        self.snls.ensure_index("formula_pretty")

        for s in self.source_snls:
            s.ensure_index(s.key)
            s.ensure_index("formula_pretty")

    def get_items(self):
        """
        Gets all materials to assocaite with SNLs

        Returns:
            generator of materials and SNLs that could match
        """
        self.logger.info("SNL Builder Started")

        self.logger.info("Setting indexes")
        self.ensure_indicies()

        # Find all formulas for materials that have been updated since this
        # builder was last ran
        q = dict(self.query)
        q.update(self.materials.lu_filter(self.snls))
        forms_to_update = set(self.materials.distinct("formula_pretty", q))

        # Find all formulas for materials not present in the target SNL collection
        q = dict(self.query)
        mat_ids = self.materials.distinct("task_id", q)
        snl_t_ids = self.snls.distinct("task_id")
        to_update_t_ids = list(set(mat_ids) - set(snl_t_ids))
        forms_to_update |= set(self.materials.distinct("formula_pretty", {"task_id": {"$in": to_update_t_ids}}))

        # Find all new SNL formulas since the builder was last run
        for source in self.source_snls:
            new_q = source.lu_filter(self.snls)
            forms_to_update |= set(source.distinct("formula_pretty", new_q))

        # Now reduce to the set of formulas we actually have
        q = dict(self.query)
        forms_avail = set(self.materials.distinct("formula_pretty", q))
        forms_to_update = forms_to_update & forms_avail

        self.logger.info("Found {} new/updated systems to proces".format(len(forms_to_update)))

        self.total = len(forms_to_update)

        for formula in forms_to_update:
            mats = list(
                self.materials.query(
                    properties=[self.materials.key, "structure",
                                "initial_structures", "formula_pretty"],
                    criteria={
                        "formula_pretty": formula
                    }))
            snls = []

            for source in self.source_snls:
                snls.extend(source.query(criteria={"formula_pretty": formula}))

            self.logger.debug("Found {} snls and {} mats".format(len(snls), len(mats)))
            if len(mats) > 0 and len(snls) > 0:
                yield mats, snls

    def process_item(self, item):
        """
        Matches SNLS and Materials

        Args:
            item (tuple): a tuple of materials and snls

        Returns:
            list(dict): a list of collected snls with material ids
        """
        mats = item[0]
        source_snls = item[1]
        snl_docs = list()
        self.logger.debug("Tagging SNLs for {}".format(mats[0]["formula_pretty"]))

        # Match up SNLS with materials
        for mat in mats:
            matched_snls = list(self.match(source_snls, mat))
            if len(matched_snls) > 0:
                snl_doc = {self.snls.key: mat[self.materials.key]}
                snl_fields = aggregate_snls(matched_snls)
                self.add_defaults(snl_fields)
                snl_doc["snl"] = StructureNL(Structure.from_dict(mat["structure"]),
                                             **snl_fields).as_dict()
                snl_docs.append(snl_doc)

        return snl_docs

    def match(self, snls, mat):
        """
        Finds a material doc that matches with the given snl

        Args:
            snl ([dict]): the snls list
            mat (dict): a materials doc

        Returns:
            generator of materials doc keys
        """
        sm = StructureMatcher(
            ltol=self.ltol,
            stol=self.stol,
            angle_tol=self.angle_tol,
            primitive_cell=True,
            scale=True,
            attempt_supercell=False,
            allow_subset=False,
            comparator=ElementComparator())

        m_strucs = [Structure.from_dict(mat["structure"])
                    ] + [Structure.from_dict(init_struc)
                         for init_struc in mat["initial_structures"]]
        for snl in snls:
            snl_struc = StructureNL.from_dict(snl).structure
            # Get SNL Spacegroup
            # This try-except fixes issues for some structures where space
            # group data is not returned by spglib
            try:
                snl_spacegroup = snl_struc.get_space_group_info(symprec=0.1)[0]
            except:
                snl_spacegroup = -1
            for struc in m_strucs:

                # Get Materials Structure Spacegroup
                try:
                    struc_sg = struc.get_space_group_info(symprec=0.1)[0]
                except:
                    struc_sg = -1

                # Match spacegroups
                if struc_sg == snl_spacegroup and sm.fit(struc, snl_struc):
                    yield snl
                    break

    def add_defaults(self, snl):

        for k, v in self.default_snl_fields.items():
            if isinstance(v, list) and isinstance(snl[k], list):
                snl[k].extend(v)
            elif isinstance(snl[k], list):
                snl[k].append(v)
            elif isinstance(v, list):
                snl[k] = [snl[k]] + v

    def update_targets(self, items):
        """
        Inserts the new SNL docs into the SNL collection
        """

        snls = list(filter(None, chain.from_iterable(items)))

        if len(snls) > 0:
            self.logger.info("Found {} SNLs to update".format(len(snls)))
            self.snls.update(snls)
        else:
            self.logger.info("No items to update")


DB_indexes = {"ICSD": "icsd_ids", "Pauling": "pf_ids"}

logger = logging.getLogger(__name__)

def aggregate_snls(snls):
    """
    Aggregates a series of SNLs into the fields for a single SNL
    """
    # Choose earliesst created_at
    created_at = sorted([snl["about"]["created_at"]["string"] for snl in snls])[0]

    # Choose earliest history
    history = sorted(snls, key=lambda snl: snl["about"]["created_at"]["string"])\
        [0]["about"]["history"]

    # Aggregate all references into one dict to remove duplicates
    refs = {}
    for snl in snls:
        try:
            entries = parse_string(snl["about"]["references"], bib_format="bibtex")
            refs.update(entries.entries)
        except:
            logger.debug("Failed parsing bibtex: {}".format(
                snl["about"]["references"]))

    entries = BibliographyData(entries=refs)
    references = entries.to_string("bibtex")

    # Keep first SNL remarks since that should assocaited with the base structure
    remarks = list(set([remark for remark in snls[0]["about"]["remarks"]]))
    remarks = [r for r in remarks if len(r) < 140]
    # The rest get stored in tags
    tags = list(set([remark for snl in snls for remark in snl["about"]["remarks"]]))

    # Aggregate all projects
    projects = list(set([projects for snl in snls
                         for projects in snl["about"]["projects"]]))

    # Aggregate all authors - Converting a single dictionary first
    # performs duplicate checking
    authors = {entry["name"].lower(): entry["email"]
               for snl in snls for entry in snl["about"]["authors"]}
    authors = [{"name": name.title(), "email": email}
               for name, email in authors.items()]

    # Aggregate all the database IDs
    db_ids = defaultdict(list)
    for snl in snls:
        if len(snl["about"]["history"]) == 1 \
                and get(snl, "about.history.0.name", "") in DB_indexes:
            db_name = get(snl, "about.history.0.name", "")
            db_id_key = DB_indexes[db_name]
            db_ids[db_id_key].append(
                snl["about"]["history"][0]["description"].get("id", None))

    # remove Nones and empty lists
    db_ids = {k: list(filter(None, v)) for k, v in db_ids.items()}
    db_ids = {k: v for k, v in db_ids.items() if len(v) > 0}

    snl_fields = {
        "created_at": created_at,
        "history": history,
        "references": references,
        "remarks": remarks,
        "projects": projects,
        "authors": authors,
        "data": {
            "_db_ids": db_ids,
            "_tags": tags,
        }
    }

    return snl_fields
