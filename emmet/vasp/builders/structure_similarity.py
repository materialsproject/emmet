import numpy as np

from maggma.builder import Builder

__author__ = "Nils E. R. Zimmermann <nerz@lbl.gov>"


class StructureSimilarityBuilder(Builder):

    def __init__(self, site_descriptors, structure_similarity,
                 **kwargs):
        """
        Calculates similarity metrics between structures on the basis
        of site descriptors.

        Args:
            site_descriptors (Store): storage of site-descriptors data
                                      such as tetrahedral order parameter
                                      or percentage of 8-fold coordination.
            structure_similarity (Store): storage of structure similarity
                                          metrics.
        """

        self.site_descriptors = site_descriptors
        self.structure_similarity = structure_similarity

        super().__init__(sources=[site_descriptors],
                         targets=[structure_similarity],
                         **kwargs)

    def get_items(self):
        """
        Gets all materials that need new site descriptors.

        Returns:
            generator of materials to calculate site descriptors.
        """

        self.logger.info("Structure Similarity Builder Started")

        self.logger.info("Setting indexes")

        #TODO: re-introduce last-updated filter possibility.
        task_ids = sorted(list(self.site_descriptors.distinct(self.site_descriptors.key)))
        n_task_ids = len(task_ids)
        for i in range(n_task_ids-1):
            for j in range(i+1, n_task_ids):
                yield self.site_descriptors.query(
                    properties=[self.site_descriptors.key, "opsf_statistics"],
                    criteria={self.site_descriptors.key: d}).limit(1)[0]

    def process_item(self, item):
        """
        Calculates site descriptors for the structures

        Args:
            item (dict): a dict with a material_id and a structure

        Returns:
            dict: a site-descriptors dict
        """
        pass
        #self.logger.debug("Calculating site descriptors for {}".format(
        #    item[self.materials.key]))

        #struct = Structure.from_dict(item['structure'])

        #site_descr_doc = {'structure': struct.copy()}
        #site_descr_doc['site_descriptors'] = \
        #        self.get_site_descriptors_from_struct(
        #        site_descr_doc['structure'])
        #site_descr_doc['opsf_statistics'] = \
        #        self.get_opsf_statistics(
        #        site_descr_doc['site_descriptors'])
        #site_descr_doc[self.site_descriptors.key] = item[self.materials.key]

        #return site_descr_doc

    #def update_targets(self, items):
    #    """
    #    Inserts the new task_types into the task_types collection.

    #    Args:
    #        items ([[dict]]): a list of list of site-descriptors dictionaries to update.
    #    """
    #    items = list(filter(None, items))

    #    if len(items) > 0:
    #        self.logger.info("Updating {} site-descriptors docs".format(len(items)))
    #        self.site_descriptors.update(docs=items)
    #    else:
    #        self.logger.info("No items to update")

    def get_similarities(self, d1, d2):
        doc = {}

        # Compute similarty metrics.
        try:
            dout = {}
            l = {}
            v = {}
            for i, d in enumerate([d1, d2]):
                v[i] = []
                l[i] = []
                for optype, stats in d.items():
                    for stattype, val in stats.items():
                        v[i].append(val)
                        l[i].append('{} {}'.format(optype, stattype))
            if len(l[0]) != len(l[1]):
                raise RuntimeError('Site-fingerprint statistics dictionaries'
                                   ' have different sizes ({}, {})'.format(
                                   len(l[0]), len(l[1])))
            for k in l[0]:
                if k not in l[1]:
                    raise RuntimeError('Label "{}" not found in second site-'
                                       'fingerprint statistics '
                                       'dictionary'.format(k))
            v1 = np.array([v[0][k] for k in l[0]])
            v2 = np.array([v[1][k] for k in l[0]])
            dout['cos'] = np.dot(v1, v2) / sqrt(
                    np.linalg.norm(v1) * np.linalg.norm(v2))
            dout['dist'] = np.linalg.norm(v1 - v2)
            doc = dout

        except Exception as e:
             self.logger.error("Failed calculating structure similarity"
                              "metrics: {}".format(e))

        return doc
