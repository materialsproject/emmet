import logging
import os
from datetime import datetime

from monty.json import jsanitize
from monty.serialization import loadfn

from pymatgen.core.structure import Structure
from matminer.featurizers.site import OPSiteFingerprint ,\
CrystalSiteFingerprint, ChemEnvSiteFingerprint
CoordinationNumber

# Maybe include those, too?
# AGNIFingerprints, EwaldSiteEnergy, \
# VoronoiFingerprint, ChemEnvSiteFingerprint, \
# ChemicalSRO


from maggma.builder import Builder

__author__ = "Nils E. R. Zimmermann <nerz@lbl.gov>"


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

        #xrd_doc = {"xrd": self.get_xrd_from_struct(struct)}
        #xrd_doc[self.diffraction.key] = item[self.materials.key]

        return xrd_doc

    #def get_xrd_from_struct(self, structure):
    #    doc = {}

    #    for xs in self.__settings:
    #        xrdcalc = XRDCalculator(wavelength="".join([xs['target'], xs['edge']]),
    #                                symprec=xs.get('symprec', 0))

    #        pattern = jsanitize(xrdcalc.get_xrd_pattern(
    #            structure, two_theta_range=xs['two_theta']).as_dict())
    #        # TODO: Make sure this is what the website actually needs
    #        d = {'wavelength': {'element': xs['target'],
    #                            'in_angstroms': WAVELENGTHS["".join([xs['target'], xs['edge']])]},
    #             'pattern': pattern}
    #        doc[xs['target']] = d
    #    return doc

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
