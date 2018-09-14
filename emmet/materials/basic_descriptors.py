import numpy as np

from pymatgen.core.structure import Structure
from pymatgen.analysis import local_env
from atomate.utils.utils import get_meta_from_structure
from matminer.featurizers.site import CrystalNNFingerprint, CoordinationNumber
from matminer.featurizers.composition import ElementProperty

# TODO:
# 1) Add checking OPs present in current implementation of site fingerprints.
# 2) Complete documentation!!!

from maggma.builder import Builder

__author__ = "Nils E. R. Zimmermann <nerz@lbl.gov>"

nn_target_classes = ["MinimumDistanceNN", "VoronoiNN",
    "CrystalNN", "JmolNN", "MinimumOKeeffeNN", "MinimumVIRENN",
    "BrunnerNN_reciprocal", "BrunnerNN_relative", "BrunnerNN_real",
    "EconNN"]


class BasicDescriptorsBuilder(Builder):

    def __init__(self, materials, descriptors, mat_query=None, **kwargs):
        """
        Calculates site-based descriptors (e.g., coordination numbers
        with different near-neighbor finding approaches) for materials and
        runs statistics analysis on selected descriptor types
        (order parameter-based site fingerprints).  The latter is
        useful as a definition of a structure fingerprint
        on the basis of local coordination information.
        Furthermore, composition descriptors are calculated
        (Magpie element property vector).

        Args:
            materials (Store): Store of materials documents.
            descriptors (Store): Store of composition, site, and
                                 structure descriptor data such
                                 as tetrahedral order parameter or
                                 fraction of being 8-fold coordinated.
            mat_query (dict): dictionary to limit materials to be analyzed.
        """

        self.materials = materials
        self.descriptors = descriptors
        self.mat_query = mat_query if mat_query else {}

        # Set up all targeted site descriptors.
        self.sds = {}
        for nn in nn_target_classes:
            nn_ = getattr(local_env, nn)
            k = 'cn_{}'.format(nn)
            self.sds[k] = CoordinationNumber(nn_(), use_weights='none')
            k = 'cn_wt_{}'.format(nn)
            self.sds[k] = CoordinationNumber(nn_(), use_weights='sum')
        self.all_output_pieces = {'site_descriptors': [k for k in self.sds.keys()]}
        self.sds['csf'] = CrystalNNFingerprint.from_preset('ops',
                                                           distance_cutoffs=None,
                                                           x_diff_weight=None)
        self.all_output_pieces['statistics'] = ['csf']

        # Set up all targeted composition descriptors.
        self.cds = {}
        self.cds["magpie"] = ElementProperty.from_preset('magpie')
        self.all_output_pieces['composition_descriptors'] = ['magpie']

        self.all_output_pieces['meta'] = ['atomate']

        super().__init__(sources=[materials],
                         targets=[descriptors],
                         **kwargs)

    def get_items(self):
        """
        Gets all materials that need new descriptors.
        For example, entirely new materials and materials
        for which certain descriptor in the current Store
        are still missing.

        Returns:
            generator of materials to calculate basic descriptors
            and of the target quantities to be calculated
            (e.g., CN with the minimum distance near neighbor
            (MinimumDistanceNN) finding class from pymatgen which has label
            "cn_mdnn").
        """

        self.logger.info("Basic-Descriptors Builder Started")

        self.logger.info("Setting indexes")

        # All relevant materials that have been updated since descriptors
        # were last calculated

        q = dict(self.mat_query)
        all_task_ids = list(self.materials.distinct(self.materials.key, q))
        q.update(self.materials.lu_filter(self.descriptors))
        new_task_ids = list(self.materials.distinct(self.materials.key, q))
        self.logger.info(
            "Found {} entirely new materials for descriptors data".format(
            len(new_task_ids)))
        for task_id in all_task_ids:
            if task_id in new_task_ids:
                any_piece = True

            else: # Any piece of info missing?
                data_present = self.descriptors.query(
                        properties=[self.descriptors.key,
                                    "meta",
                                    "composition_descriptors",
                                    "site_descriptors",
                                    "statistics"],
                        criteria={self.descriptors.key: task_id}).limit(1)[0]
                any_piece = False
                for k, v in self.all_output_pieces.items():
                    if k not in list(data_present.keys()):
                        any_piece = True
                        break
                    else:
                        any_piece = False
                        for e in v:
                            if e not in data_present[k]:
                                any_piece = True
                                break
                if not any_piece:
                    for l in self.sds['csf'].feature_labels():
                        for fpi in data_present['site_descriptors']['csf']:
                            if l not in fpi.keys():
                                any_piece = True
                                break
            if any_piece:
                yield self.materials.query(
                        properties=[self.materials.key, "structure"],
                        criteria={self.materials.key: task_id}).limit(1)[0]

    def process_item(self, item):
        """
        Calculates all basic descriptors for the structures


        Args:
            item (dict): a dict with a task_id and a structure

        Returns:
            dict: a basic-descriptors dict
        """
        self.logger.debug("Calculating basic descriptors for {}".format(
            item[self.materials.key]))

        struct = Structure.from_dict(item['structure'])

        descr_doc = {'structure': struct.copy()}
        descr_doc['meta'] = {'atomate': get_meta_from_structure(struct)}
        try:
            comp_descr = [{'name': 'magpie'}]
            labels = self.cds["magpie"].feature_labels()
            values = self.cds["magpie"].featurize(struct.composition)
            for label, value in zip(labels, values):
                comp_descr[0][label] = value
            descr_doc['composition_descriptors'] = comp_descr
        except Exception as e:
            self.logger.error("Failed getting Magpie descriptors: "
                              "{}".format(e))
        descr_doc['site_descriptors'] = \
                self.get_site_descriptors_from_struct(
                descr_doc['structure'])
        descr_doc['statistics'] = \
                self.get_statistics(
                descr_doc['site_descriptors'])
        descr_doc[self.descriptors.key] = item[self.materials.key]

        return descr_doc

    def update_targets(self, items):
        """
        Inserts the new task_types into the task_types collection.

        Args:
            items ([[dict]]): a list of list of descriptors dictionaries to update.
        """
        items = list(filter(None, items))

        if len(items) > 0:
            self.logger.info("Updating {} basic-descriptors docs".format(len(items)))
            self.descriptors.update(docs=items)
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

    def get_statistics(self, site_descr, fps=('csf', )):
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
                    dtmp['mean'] = np.mean(tmp[k])
                    dtmp['std'] = np.std(tmp[k])
                    d.append(dtmp)
                doc[fp] = d

            except Exception as e:
                self.logger.error("Failed calculating statistics of site "
                                  "descriptors: {}".format(e))

        return doc
