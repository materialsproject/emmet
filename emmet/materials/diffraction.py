import logging
import os
from datetime import datetime

from monty.json import jsanitize
from monty.serialization import loadfn

from pymatgen.core.structure import Structure
from pymatgen.analysis.diffraction.xrd import XRDCalculator, WAVELENGTHS

from emmet.common.utils import load_settings
from maggma.builders import MapBuilder

__author__ = "Shyam Dwaraknath <shyamd@lbl.gov>"

MODULE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_XRD_SETTINGS = os.path.join(MODULE_DIR, "settings", "xrd.json")


class DiffractionBuilder(MapBuilder):
    def __init__(self, materials, diffraction, xrd_settings=None, **kwargs):
        """
        Calculates diffraction patterns for materials

        Args:
            materials (Store): Store of materials documents
            diffraction (Store): Store of diffraction data such as formation energy and decomposition pathway
            xrd_settings (Store): Store of xrd settings
        """

        self.materials = materials
        self.diffraction = diffraction
        self.xrd_settings = xrd_settings
        self.__settings = load_settings(self.xrd_settings, DEFAULT_XRD_SETTINGS)

        super().__init__(
            source=materials, target=diffraction, ufn=self.calc, projection=["structure"], **kwargs)

    def calc(self, item):
        """
        Calculates diffraction patterns for the structures

        Args:
            item (dict): a dict with a material_id and a structure

        Returns:
            dict: a diffraction dict
        """
        self.logger.debug("Calculating diffraction for {}".format(item[self.materials.key]))

        struct = Structure.from_dict(item['structure'])
        xrd_doc = {"xrd": self.get_xrd_from_struct(struct)}
        return xrd_doc

    def get_xrd_from_struct(self, structure):
        doc = {}

        for xs in self.__settings:
            xrdcalc = XRDCalculator(wavelength="".join([xs['target'], xs['edge']]), symprec=xs.get('symprec', 0))

            pattern = jsanitize(xrdcalc.get_pattern(structure, two_theta_range=xs['two_theta']).as_dict())
            d = {
                'wavelength': {
                    'element': xs['target'],
                    'in_angstroms': WAVELENGTHS["".join([xs['target'], xs['edge']])]
                },
                'pattern': pattern
            }
            doc[xs['target']] = d
        return doc
