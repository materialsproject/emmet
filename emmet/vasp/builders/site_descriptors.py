import logging

from pymatgen.core.structure import Structure
from matminer.featurizers.site import OPSiteFingerprint ,\
CrystalSiteFingerprint, CoordinationNumber

# Maybe include those, too?
# AGNIFingerprints, EwaldSiteEnergy, \
# VoronoiFingerprint, ChemEnvSiteFingerprint, \
# ChemicalSRO


from maggma.builder import Builder

__author__ = "Nils E. R. Zimmermann <nerz@lbl.gov>"


cls_to_abbrev = {
    'OPSiteFingerprint': 'opsf', 'CrystalSiteFingerprint': 'csf', \
    'VoronoiNN': 'vnn', 'JMolNN': 'jmnn', 'MinimumDistanceNN': 'mdnn', \
    'MinimumOKeeffeNN': 'moknn', 'MinimumVIRENN': 'mvirenn'}

class SiteDescriptorsBuilder(Builder):

    def __init__(self, materials, site_descriptors, query=None, **kwargs):
        """
        Calculates site descriptors for materials

        Args:
            materials (Store): Store of materials documents
            site_descriptors (Store): Store of site-descriptors data such as tetrahedral order parameter or percentage of 8-fold coordination
            query (dict): dictionary to limit materials to be analyzed
        """

        self.materials = materials
        self.site_descriptors = site_descriptors
        self.query = query if query else {}

        super().__init__(sources=[materials],
                         targets=[site_descriptors],
                         **kwargs)

    def get_items(self):
        """
        Gets all materials that need new site descriptors.

        Returns:
            generator of materials to calculate site descriptors.
        """

        self.logger.info("Site-Descriptors Builder Started")

        self.logger.info("Setting indexes")
        self.ensure_indexes()

        # All relevant materials that have been updated since site-descriptors
        # were last calculated
        q = dict(self.query)
        q.update(self.materials.lu_filter(self.site_descriptors))
        mats = list(self.materials.distinct(self.materials.key, q))
        self.logger.info(
            "Found {} new materials for site-descriptors data".format(len(mats)))
        for m in mats:
            yield self.materials.query(properties=[self.materials.key, "structure"], criteria={self.materials.key: m}).limit(1)[0]

    def process_item(self, item):
        """
        Calculates site descriptors for the structures

        Args:
            item (dict): a dict with a material_id and a structure

        Returns:
            dict: a site-descriptors dict
        """
        self.logger.debug("Calculating site descriptors for {}".format(
            item[self.materials.key]))

        struct = Structure.from_dict(item['structure'])

        site_descr_doc = {"site_descriptors": get_site_descriptors_from_struct(struct)}
        # TODO: Should I add lattice matrix and frac coords of all sites?
        site_descr_doc[self.site_descriptors.key] = item[self.materials.key]

        return site_descr_doc

    def update_targets(self, items):
        """
        Inserts the new task_types into the task_types collection.

        Args:
            items ([[dict]]): a list of list of site-descriptors dictionaries to update.
        """
        items = list(filter(None, items))

        if len(items) > 0:
            self.logger.info("Updating {} site-descriptors docs".format(len(items)))
            self.site_descriptors.update(docs=items)
        else:
            self.logger.info("No items to update")

    def ensure_indexes(self):
        """
        Ensures indexes on the tasks and materials collections.
        """
        # Search index for materials
        self.materials.ensure_index(self.materials.key, unique=True)

        # Search index for materials
        self.site_descriptors.ensure_index(self.site_descriptors.key, unique=True)

def get_site_descriptors_from_struct(structure):
    doc = {}

    # Set up all targeted site descriptors.
    sds = {}
    for nn in NearNeighbors.__subclasses__():
        nn_ = getattr(pymatgen.analysis.local_env, nn)
        t = nn.__name__ if nn.__name__ \
            not in cls_to_abbrev.keys() \
            else cls_to_abbrev[nn.__name__]
        k = 'cn_{}'.format(t)
        sds[k] = CoordinationNumber(nn_(), use_weights=False)
        k = 'cn_wt_{}'.format(t)
        sds[k] = CoordinationNumber(nn_(), use_weights=True)
    sds['opsf'] = OPSiteFingerprint()
    sds['csf'] = CrystalSiteFingerprint()

    # Compute descriptors.
    for k, sd in sds.items():
        try:
            d = {}
            for i, s in enumerate(structure.sites):
                d[i] = sd.featurize(structure, i)
            doc[k] = d
        except Exception as e:
            self.logger.error("Failed calculating {} site-descriptors: "
                              "{}".format(k, e))

    return doc

