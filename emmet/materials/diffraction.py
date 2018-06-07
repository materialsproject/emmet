import logging
import os
from datetime import datetime

from monty.json import jsanitize
from monty.serialization import loadfn

from pymatgen.core.structure import Structure
from pymatgen.analysis.diffraction.xrd import XRDCalculator, WAVELENGTHS

from maggma.builder import Builder

__author__ = "Shyam Dwaraknath <shyamd@lbl.gov>"

module_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)))
default_xrd_settings = os.path.join(
    module_dir, "settings", "xrd.json")


class DiffractionBuilder(Builder):

    def __init__(self, materials, diffraction, xrd_settings=None, query=None, **kwargs):
        """
        Calculates diffraction patterns for materials

        Args:
            materials (Store): Store of materials documents
            diffraction (Store): Store of diffraction data such as formation energy and decomposition pathway
            xrd_settings (Store): Store of xrd settings
            query (dict): dictionary to limit materials to be analyzed
        """

        self.materials = materials
        self.diffraction = diffraction
        self.xrd_settings = xrd_settings
        self.query = query if query else {}
        self.__settings = loadfn(
            self.xrd_settings if self.xrd_settings else default_xrd_settings)

        super().__init__(sources=[materials],
                         targets=[diffraction],
                         **kwargs)

    def get_items(self):
        """
        Gets all materials that need a new XRD 

        Returns:
            generator of materials to calculate xrd
        """

        self.logger.info("Diffraction Builder Started")

        self.logger.info("Setting indexes")
        self.ensure_indicies()

        # All relevant materials that have been updated since diffraction props
        # were last calculated
        q = dict(self.query)
        q.update(self.materials.lu_filter(self.diffraction))
        mats = list(self.materials.distinct(self.materials.key, q))
        self.logger.info(
            "Found {} new materials for diffraction data".format(len(mats)))
        self.total = len(mats)
        for m in mats:
            yield self.materials.query(properties=[self.materials.key, "structure", self.materials.lu_field],
                                       criteria={self.materials.key: m}).limit(1)[0]

    def process_item(self, item):
        """
        Calculates diffraction patterns for the structures

        Args:
            item (dict): a dict with a material_id and a structure

        Returns:
            dict: a diffraction dict
        """
        self.logger.debug("Calculating diffraction for {}".format(
            item[self.materials.key]))

        struct = Structure.from_dict(item['structure'])

        xrd_doc = {"xrd": self.get_xrd_from_struct(struct)}
        xrd_doc[self.diffraction.key] = item[self.materials.key]

        elsyms = sorted(set([el.symbol for el in struct.composition.elements]))
        xrd_doc[self.diffraction.lu_field] = item[self.materials.lu_field]

        return xrd_doc

    def get_xrd_from_struct(self, structure):
        doc = {}

        for xs in self.__settings:
            xrdcalc = XRDCalculator(wavelength="".join([xs['target'], xs['edge']]),
                                    symprec=xs.get('symprec', 0))

            pattern = jsanitize(xrdcalc.get_pattern(
                structure, two_theta_range=xs['two_theta']).as_dict())
            d = {'wavelength': {'element': xs['target'],
                                'in_angstroms': WAVELENGTHS["".join([xs['target'], xs['edge']])]},
                 'pattern': pattern}
            doc[xs['target']] = d
        return doc

    def update_targets(self, items):
        """
        Inserts the new task_types into the task_types collection

        Args:
            items ([[dict]]): a list of list of thermo dictionaries to update
        """
        items = list(filter(None, items))

        if len(items) > 0:
            self.logger.info("Updating {} diffraction docs".format(len(items)))
            self.diffraction.update(docs=items,update_lu=False)
        else:
            self.logger.info("No items to update")

    def ensure_indicies(self):
        """
        Ensures indicies on the diffraction and materials collections
        """
        # Search indicies for materials
        self.materials.ensure_index(self.materials.key, unique=True)
        self.materials.ensure_index(self.materials.lu_field)

        # Search indicies for diffraction
        self.diffraction.ensure_index(self.diffraction.key, unique=True)
        self.diffraction.ensure_index(self.diffraction.lu_field)
