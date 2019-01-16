from pymatgen.electronic_structure.bandstructure import BandStructure
from pymatgen.electronic_structure.boltztrap2 import BandstructureLoader, BztInterpolator, units, merge_up_down_doses

from maggma.builders import Builder
from maggma.utils import source_keys_updated

import numpy as np

__author__ = "Francesco Ricci <francesco.ricci@uclouvain.be>"


class Boltztrap4DosBuilder(Builder):
    def __init__(self,
                 materials,
                 bandstructures,
                 boltztrap_dos,
                 query=None,
                 energy_grid=0.005,
                 avoid_projections=False,
                 **kwargs):
        """
        Calculates Density of States (DOS) using BoltzTrap2

        Args:
            materials (Store): Store of materials documents
            bandstructures (Store): Store where bandstructures are stored
            boltztrap_dos (Store): Store of DOS
            query (dict): dictionary to limit materials to be analyzed
            energy_grid(float): the energy_grid spacing for the DOS in eV
            avoid_projections(bool): Don't interpolate projections even if present
        """

        self.materials = materials
        self.bandstructures = bandstructures
        self.boltztrap_dos = boltztrap_dos
        self.query = query if query else {}
        self.energy_grid = energy_grid
        self.avoid_projections = avoid_projections

        super().__init__(sources=[materials, bandstructures], targets=[boltztrap_dos], **kwargs)

    def get_items(self):
        """
        Gets all materials that need a new DOS

        Returns:
            generator of materials to calculate DOS
        """

        self.logger.info("BoltzTrap Dos Builder Started")

        # All relevant materials that have been updated since boltztrap was last run
        # and a uniform bandstructure exists
        q = dict(self.query)
        q.update({"bandstructure.uniform_task": {"$exists": 1}})
        mats = set(source_keys_updated(source=self.materials, target=self.boltztrap_dos, query=self.query))

        self.logger.info("Found {} new materials for calculating boltztrap dos".format(len(mats)))

        for m in mats:
            mat = self.materials.query([self.materials.key, "structure", "bandstructure"],
                                       criteria={self.materials.key: m})

            # If a bandstructure uniform task exists
            bs_task_id = mat.get("bandstructure", {}).get("uniform_task", None)
            if bs_task_id:
                bs_dict = self.bandstructures.query_one({self.bandstructures.key: bs_task_id})
                mat["bandstructure_uniform"] = bs_dict

            yield mat

    def process_item(self, item):
        """
        Calculates dos running Boltztrap2

        Args:
            item (dict): a dict with a material_id, band_structure_uniform.task_id,
            bs and a structure

        Returns:
            cdos: a complete dos object
        """
        self.logger.debug("Calculating Boltztrap for {}".format(item[self.materials.key]))

        bs_dict = item["bandstructure_uniform"]
        bs_dict['structure'] = item['structure']

        try:
            btz_dos = dos_from_boltztrap(
                bs_dict, energy_grid=self.energy_grid, avoid_projections=self.avoid_projections)

            btz_dos.update({self.boltztrap_dos.key: item[self.materials.key]})
            return btz_dos
        except Exception as e:
            self.logger.error("Error generating the DOS for {}: \
                            {}".format(item[self.materials.key], e))

        return None

    def update_targets(self, items):
        """
        Inserts the new dos into the dos collection

        Args:
            items ([[dict]]): a list of BoltzTrap interpolated DOSes
        """
        items = list(filter(None, items))

        if len(items) > 0:
            self.logger.info("Updating {} BoltzTrap DOS".format(len(items)))
            self.boltztrap_dos.update(docs=items)

        else:
            self.logger.info("No items to update")

    def ensure_indexes(self):
        """
        Ensure basic indexes for all stores to build BoltzTrap DOS collection
        """
        self.materials.ensure_index(self.materials.key)
        self.materials.ensure_index(self.materials.lu_field)

        self.bandstructures.ensure_index(self.bandstructures.key)
        self.bandstructures.ensure_index(self.bandstructures.lu_field)

        self.boltztrap_dos.ensure_index(self.boltztrap_dos.key)
        self.boltztrap_dos.ensure_index(self.boltztrap_dos.lu_field)


def dos_from_boltztrap(bs_dict, energy_grid=0.005, avoid_projections=False):
    """
    Function to just interpolate a DOS from a bandstructure using BoltzTrap
    Args:
        bs_dict(dict): A MSONable dictionary for a bandstructure object
        energy_grid(float): the energy_grid spacing for the DOS in eV
        avoid_projections(bool): don't interpolate projections even if present
    """

    bs = BandStructure.from_dict(bs_dict)
    st = bs.structure
    energy_grid = energy_grid * units.eV
    projections = True if bs.projections and not avoid_projections else False

    if bs.is_spin_polarized:
        data_up = BandstructureLoader(bs, st, spin=1)
        data_dn = BandstructureLoader(bs, st, spin=-1)

        min_bnd = min(data_up.ebands.min(), data_dn.ebands.min())
        max_bnd = max(data_up.ebands.max(), data_dn.ebands.max())
        data_up.set_upper_lower_bands(min_bnd, max_bnd)
        data_dn.set_upper_lower_bands(min_bnd, max_bnd)
        bztI_up = BztInterpolator(data_up, energy_range=np.inf, curvature=False)
        bztI_dn = BztInterpolator(data_dn, energy_range=np.inf, curvature=False)

        npts_mu = int((max_bnd - min_bnd) / energy_grid)
        dos_up = bztI_up.get_dos(partial_dos=projections, npts_mu=npts_mu)
        dos_dn = bztI_dn.get_dos(partial_dos=projections, npts_mu=npts_mu)
        cdos = merge_up_down_doses(dos_up, dos_dn)

    else:
        data = BandstructureLoader(bs, st)
        min_bnd = min(data.ebands.min(), data.ebands.min())
        max_bnd = max(data.ebands.max(), data.ebands.max())
        npts_mu = int((max_bnd - min_bnd) / energy_grid)
        bztI = BztInterpolator(data, energy_range=np.inf, curvature=False)
        cdos = bztI.get_dos(partial_dos=projections, npts_mu=npts_mu)

    return cdos.as_dict()
