import numpy as np

from pymatgen.core.structure import Structure
import pymatgen.analysis
from pymatgen.analysis.local_env import *
from matminer.featurizers.site import OPSiteFingerprint ,\
CrystalSiteFingerprint, CoordinationNumber

# TODO:
# 1) complete documentation!!!

from maggma.builder import Builder

__author__ = "Nils E. R. Zimmermann <nerz@lbl.gov>"


cls_to_abbrev = {
    'OPSiteFingerprint': 'opsf', 'CrystalSiteFingerprint': 'csf', \
    'VoronoiNN': 'vnn', 'JMolNN': 'jmnn', 'MinimumDistanceNN': 'mdnn', \
    'MinimumOKeeffeNN': 'moknn', 'MinimumVIRENN': 'mvirenn', \
    'BrunnerNN': 'bnn'}

class SiteDescriptorsBuilder(Builder):

    def __init__(self, materials, site_descriptors, mat_query=None, **kwargs):
        """
        Calculates site descriptors for materials

        Args:
            materials (Store): Store of materials documents
            site_descriptors (Store): Store of site-descriptors data such as tetrahedral order parameter or percentage of 8-fold coordination
            mat_query (dict): dictionary to limit materials to be analyzed
        """

        self.materials = materials
        self.site_descriptors = site_descriptors
        self.mat_query = mat_query if mat_query else {}

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
        self.all_output_pieces = {'site_descriptors': [k for k in self.sds.keys()]}
        self.sds['opsf'] = OPSiteFingerprint()
        self.sds['csf'] = CrystalSiteFingerprint.from_preset('ops')
        self.all_output_pieces['statistics'] = ['opsf', 'csf']

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

        q = dict(self.mat_query)
        all_task_ids = list(self.materials.distinct(self.materials.key, q))
        q.update(self.materials.lu_filter(self.site_descriptors))
        new_task_ids = list(self.materials.distinct(self.materials.key, q))
        self.logger.info(
            "Found {} entirely new materials for site-descriptors data".format(len(new_task_ids)))
        for task_id in all_task_ids:
            if task_id in new_task_ids:
                output_pieces = self.all_output_pieces
                any_piece = True
            else:
                output_pieces = {}
                data_present = self.site_descriptors.query(
                        properties=[self.site_descriptors.key, "site_descriptors", "statistics"],
                        criteria={self.site_descriptors.key: task_id}).limit(1)[0]
                any_piece = False
                for k, v in self.all_output_pieces.items():
                    if k not in list(data_present.keys()):
                        output_pieces[k] = [e for e in v]
                        any_piece = True
                    else:
                        output_pieces[k] = []
                        for e in v:
                            if e not in data_present[k]:
                                output_pieces[k].append(e)
                                any_piece = True
            if any_piece:
                yield {'input': self.materials.query(
                        properties=[self.materials.key, "structure"],
                        criteria={self.materials.key: task_id}).limit(1)[0],
                        'output': output_pieces}

    def process_item(self, item):
        """
        Calculates site descriptors for the structures


        Args:
            item (dict): a dict with a task_id and a structure

        Returns:
            dict: a site-descriptors dict
        """
        self.logger.debug("Calculating site descriptors for {}".format(
            item['input'][self.materials.key]))

        struct = Structure.from_dict(item['input']['structure'])

        site_descr_doc = {'structure': struct.copy()}
        site_descr_doc['site_descriptors'] = \
                self.get_site_descriptors_from_struct(
                site_descr_doc['structure'])
        site_descr_doc['statistics'] = \
                self.get_statistics(
                site_descr_doc['site_descriptors'])
        site_descr_doc[self.site_descriptors.key] = item['input'][self.materials.key]

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
                d = []
                l = sd.feature_labels()
                for i, s in enumerate(structure.sites):
                    d.append({'site': i})
                    for j, desc in enumerate(sd.featurize(structure, i)):
                        d[i][l[j]] = desc
                doc[k] = d

            except Exception as e:
                self.logger.error("Failed calculating {} site-descriptors: "
                                  "{}".format(k, e))

        return doc

    def get_statistics(self, site_descr, fps=('opsf', 'csf')):
        doc = {}

        # Compute site-descriptor statistics.
        for fp in fps:
            doc[fp] = {}
            try:
                n_site = len(site_descr[fp])
                tmp = {}
                for isite in range(n_site):
                    for l, v in site_descr[fp][isite].items():
                        if l not in list(tmp.keys()):
                            tmp[l] = []
                        tmp[l].append(v)
                d = []
                for k, l in tmp.items():
                    dtmp = {'name': k}
                    dtmp['min'] = min(tmp[k])
                    dtmp['max'] = max(tmp[k])
                    dtmp['mean'] = np.mean(tmp[k])
                    dtmp['std'] = np.std(tmp[k])
                    d.append(dtmp)
                doc[fp] = d

            except Exception as e:
                self.logger.error("Failed calculating statistics of site "
                                  "descriptors: {}".format(e))

        return doc
