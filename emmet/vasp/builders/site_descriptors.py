import numpy as np

from pymatgen.core.structure import Structure
import pymatgen.analysis
from pymatgen.analysis.local_env import *
from matminer.featurizers.site import OPSiteFingerprint ,\
CrystalSiteFingerprint, CoordinationNumber

# TODO:
# AGNIFingerprints, EwaldSiteEnergy, \
# VoronoiFingerprint, ChemEnvSiteFingerprint, \
# ChemicalSRO


from maggma.builder import Builder

__author__ = "Nils E. R. Zimmermann <nerz@lbl.gov>"


cls_to_abbrev = {
    'OPSiteFingerprint': 'opsf', 'CrystalSiteFingerprint': 'csf', \
    'VoronoiNN': 'vnn', 'JMolNN': 'jmnn', 'MinimumDistanceNN': 'mdnn', \
    'MinimumOKeeffeNN': 'moknn', 'MinimumVIRENN': 'mvirenn', \
    'BrunnerNN': 'bnn'}

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

        # Set up all targeted site descriptors.
        self.sds = {}
        for nn in NearNeighbors.__subclasses__():
            nn_ = getattr(pymatgen.analysis.local_env, nn.__name__)
            t = nn.__name__ if nn.__name__ \
                not in cls_to_abbrev.keys() \
                else cls_to_abbrev[nn.__name__]
            k = 'cn_{}'.format(t)
            self.sds[k] = CoordinationNumber(nn_(), use_weights=False)
            k = 'cn_wt_{}'.format(t)
            self.sds[k] = CoordinationNumber(nn_(), use_weights=True)
        self.sds['opsf'] = OPSiteFingerprint()
        self.sds['csf'] = CrystalSiteFingerprint.from_preset('ops')

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

        site_descr_doc = {'structure': struct.copy()}
        site_descr_doc['site_descriptors'] = \
                self.get_site_descriptors_from_struct(
                site_descr_doc['structure'])
        site_descr_doc['opsf_statistics'] = \
                self.get_opsf_statistics(
                site_descr_doc['site_descriptors'])
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

    def get_site_descriptors_from_struct(self, structure):
        doc = {}

        # Compute descriptors.
        for k, sd in self.sds.items():
            try:
                d = {}
                l = sd.feature_labels()
                for i, s in enumerate(structure.sites):
                    d[i] = {}
                    for j, desc in enumerate(sd.featurize(structure, i)):
                        d[i][l[j]] = desc
                doc[k] = d
            except Exception as e:
                self.logger.error("Failed calculating {} site-descriptors: "
                                  "{}".format(k, e))

        return doc

    def get_opsf_statistics(self, site_descr):
        doc = {}

        # Compute site-descriptor statistics.
        #try:
        n_site = len(list(site_descr['opsf'].keys()))
        tmp = {}
        for isite in range(n_site):
            for l, v in site_descr['opsf'][isite].items():
                if l not in list(tmp.keys()):
                    tmp[l] = []
                tmp[l].append(v)
        d = {}
        for k, l in tmp.items():
            d[k] = {}
            d[k]['min'] = min(tmp[k])
            d[k]['max'] = max(tmp[k])
            d[k]['mean'] = np.mean(tmp[k])
            d[k]['std'] = np.std(tmp[k])
        doc = d

        #except Exception as e:
        #    self.logger.error("Failed calculating statistics of site "
        #                      "descriptors: {}".format(e))

        return doc
