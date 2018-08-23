from itertools import chain
import numpy as np

from pymatgen import Structure
from pymatgen.symmetry.analyzer import SpacegroupAnalyzer
from pymatgen.analysis.gb.gb import Gb

from maggma.builder import Builder

__author__ = "Xiang-Guo Li <xil110@ucsd.edu>"


class GBBuilder(Builder):
    def __init__(self, materials, gb, bulk, query=None, **kwargs):
        """
        Calculates grain boundary energies from gb and bulk data.

        Args:
            materials (Store): Store of materials documents from gb task.
            gb (Store): Store to update with grain boundary data.
            bulk (Store): Store of corresponding bulk data such as energy per atom from bulk task.
            query (dict): dictionary to limit materials to be analyzed
        """

        self.materials = materials
        self.gb = gb
        self.bulk = bulk
        self.query = query if query else {}
        super(GBBuilder, self).__init__(sources=[materials, bulk], targets=[gb], **kwargs)

    def get_items(self):
        """
        Gets sets of entries from grain boundary systems that need to be processed

        Returns:
            generator of relevant entries from one gb system
        """
        self.logger.info("GB Builder Started")

        self.logger.info("Setting indexes")
        self.ensure_indicies()
        # All relevant materials that have been updated since GB props
        # were last calculated
        q = dict(self.query)
        q.update(self.materials.lu_filter(self.gb))
        updated_mats = set(self.materials.distinct(self.materials.key, q))
        self.logger.info(
            "Found {} updated materials for GB data".format(len(updated_mats)))

        all_mats = set(self.materials.distinct(self.materials.key, self.query))
        all_bulks = set(self.bulk.distinct(self.bulk.key, self.query))
        curr_gb = set(self.gb.distinct(self.gb.key))
        self.logger.info("Found {} new materials for GB data".format(len(all_mats - curr_gb)))

        mats = list((all_mats - curr_gb) | updated_mats)
        bulks = list(all_bulks)
        self.total = len(mats)

        gb_docs = []
        for m in mats:
            gb_doc = \
                self.materials.query(properties=[self.materials.key, "structure", "GB_info", "nsites",
                                                 "formula_pretty", "Material_id", "task_id", "energy_per_atom"],
                                     criteria={self.materials.key: m}).limit(1)[0]
            gb_docs.append(gb_doc)

        bulk_docs = []
        for n in all_bulks:
            bulk_doc = \
                self.bulk.query(properties=[self.bulk.key, "energy_per_atom", "formula_pretty", "structure"],
                                criteria={self.bulk.key: n}).limit(1)[0]
            bulk_docs.append(bulk_doc)

        yield gb_docs, bulk_docs

    def process_item(self, item):
        """
        Compute GB energy

        Args:
            item (list): a tuple of list of materials and list of Bulks

        Returns:
            list(dict): a list of collected gbs with material ids
        """
        gb_docs = list()
        mats = item[0]
        bulks = item[1]
        all_gb_doc = {}
        for mat in mats:
            mpid = mat['Material_id'][0]
            grain = {}
            space_group = {}
            gb_doc = {}
            self.logger.debug("Tagging GBs for {}".format(mat["formula_pretty"]))
            structure = Structure.from_dict(mat['structure'])
            area = np.linalg.norm(np.cross(structure.lattice.matrix[0], structure.lattice.matrix[1]))
            for bulk in bulks:
                if bulk['formula_pretty'] == mat['formula_pretty']:
                    bulk_str = Structure.from_dict(bulk['structure'])
                    analyzer = SpacegroupAnalyzer(bulk_str)
                    space_group['symbol'] = analyzer.get_space_group_symbol()
                    space_group['number'] = analyzer.get_space_group_number()
                    grain['GB_energy in J/m2'] = 16.0217656 * (mat['energy_per_atom'] - bulk['energy_per_atom']) * \
                                                 mat['nsites'] / area
                    break
            grain['initial_structure'] = mat['GB_info']
            gb_temp = Gb.from_dict(mat['GB_info'])
            grain['rotation_axis'] = gb_temp.rotation_axis
            grain['rotation_angle'] = gb_temp.rotation_angle
            grain['gb_plane'] = gb_temp.gb_plane
            grain['sigma'] = gb_temp.sigma
            final_gb = Gb(structure.lattice, structure.species_and_occu, structure.frac_coords,
                          gb_temp.rotation_axis, gb_temp.rotation_angle, gb_temp.gb_plane,
                          gb_temp.init_cell, gb_temp.vacuum_thickness, gb_temp.ab_shift,
                          gb_temp.site_properties, gb_temp.oriented_unit_cell)
            grain['final_structure'] = final_gb.as_dict()

            if str(mpid) in all_gb_doc.keys():
                all_gb_doc[str(mpid)]['grain_boundaries'].append(grain)
            else:
                gb_doc['grain_boundaries'] = [grain]
                gb_doc['Material_id'] = mat['Material_id'][0]
                gb_doc['task_id'] = mat['task_id']
                gb_doc['formula_pretty'] = mat['formula_pretty']
                gb_doc['spacegroup'] = space_group
                all_gb_doc[str(mpid)] = gb_doc

        for key in all_gb_doc.keys():
            gb_docs.append(all_gb_doc[key])

        return gb_docs

    def update_targets(self, items):
        """
        Inserts the new gb docs into the gb collection
        """

        gbs = list(filter(None, chain.from_iterable(items)))

        if len(gbs) > 0:
            self.logger.info("Found {} gbs to update".format(len(gbs)))
            self.gb.update(gbs)
        else:
            self.logger.info("No items to update")

    def ensure_indicies(self):
        '''
        Ensures indexes on the materials, bulk and gb
        '''
        self.materials.ensure_index(self.materials.key, unique=True)
        self.materials.ensure_index("formula_pretty")
        self.materials.ensure_index("GB_info")

        self.bulk.ensure_index(self.bulk.key, unique=True)
        self.bulk.ensure_index("formula_pretty")
        self.bulk.ensure_index("energy_per_atom")

        self.gb.ensure_index(self.gb.key, unique=True)
