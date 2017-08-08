import logging
from datetime import datetime

from pymatgen.core.structure import Structure
from pymatgen.analysis.diffraction.xrd import XRDCalculator, WAVELENGTHS

from maggma.builder import Builder

__author__ = "Shyam Dwaraknath <shyamd@lbl.gov>"


class DiffractionBuilder(Builder):
    def __init__(self, materials, diffraction, xrd_settings, query={}, **kwargs):
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
        self.query = query
        self.xrd_settings.connect()
        self.__xrd_settings = list(self.xrd_settings().find())

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

        # All relevant materials that have been updated since diffraction props were last calculated
        q = dict(self.query)
        q.update(self.materials.lu_filter(self.diffraction))
        mats = self.materials().find(q, {"material_id": 1,
                                         "structure": 1})
        self.logger.info("Found {} new materials for diffraction data".format(mats.count()))
        return mats

    def process_item(self, item):
        """
        Calculates diffraction patterns for the structures

        Args:
            item (dict): a dict with a material_id and a structure

        Returns:
            dict: a diffraction dict
        """
        self.logger.debug("Calculating diffraction for {}".format(item['material_id']))
        
        struct = Structure.from_dict(item['structure'])

        xrd_doc = {"xrd": self.get_xrd_from_struct(struct)}
        xrd_doc['material_id'] = item['material_id']

        return xrd_doc

    def get_xrd_from_struct(self, structure):
        doc = {}

        for xs in self.__xrd_settings:
            xrdcalc = XRDCalculator(wavelength="".join([xs['target'], xs['edge']]),
                                    symprec=xs.get('symprec', 0))

            pattern = [[float(p[1]), [int(x) for x in list(p[2])[0]], p[0], float(p[3])] for p in
                       xrdcalc.get_xrd_data(structure, two_theta_range=xs['two_theta'])]
            # TODO: Make sure this is what the website actually needs
            d = {'wavelength': {'element': xs['target'],
                                'in_angstroms': WAVELENGTHS["".join([xs['target'], xs['edge']])]},
                 'meta': ['amplitude', 'hkl', 'two_theta', 'd_spacing'],
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
            bulk = self.diffraction().initialize_ordered_bulk_op()

            for m in items:
                m[self.diffraction.lu_field] = datetime.utcnow()
                bulk.find({"material_id": m["material_id"]}).upsert().replace_one(m)
            bulk.execute()
        else:
            self.logger.info("No items to update")
