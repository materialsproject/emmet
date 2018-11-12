import logging
from datetime import datetime

from monty.json import jsanitize
from monty.tempfile import ScratchDir
from pymatgen.core.structure import Structure
from pymatgen.electronic_structure.bandstructure import BandStructure
from pymatgen.electronic_structure.boltztrap2 import *

from maggma.builders import Builder

__author__ = "Francesco Ricci <francesco.ricci@uclouvain.be>"

class Boltztrap4DosBuilder(Builder):
    def __init__(self, materials, bandstructure, dos, query={}, **kwargs):
        """
        Calculates Density of States (DOS) using BoltzTrap2
        Saves the dos object

        Args:
            materials (Store): Store of materials documents
            bandstructure (Store): Store where bandstructures are stored
            dos (Store): Store of DOS 
            query (dict): dictionary to limit materials to be analyzed

        """

        self.materials = materials
        self.bandstructure = bandstructure
        self.dos = dos
        self.query = query

        super().__init__(sources=[materials,bandstructure],
                         targets=[dos],
                         **kwargs)

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
        q.update(self.materials.lu_filter(self.dos))
        q["band_structure_uniform"] = {"$exists": 1}
        mats = set(self.materials.distinct(self.materials.key, criteria=q))

        self.logger.info(
            "Found {} new materials for calculating boltztrap dos".format(len(mats)))

        for m in mats:
            mat = self.materials.query(
                [self.materials.key, "structure", "band_structure_uniform"], criteria={self.materials.key: m})

            # If a bandstructure uniform task exists
            bs_task_id = mat.get("band_structure_uniform",{}).get("task_id",None)
            if bs_task_id:
                bs_dict = self.bandstructures.query_one({self.bandstructures.key : bs_task_id})
                mat["band_structure_uniform"]["uniform_bs"] = bs_dict
                
            yield mat

    def process_item(self, item):
        """
        Calculates dos running Boltztrap in DOS run mode

        Args:
            item (dict): a dict with a material_id, band_structure_uniform.task_id,
            bs and a structure

        Returns:
            cdos: a complete dos object
        """
        self.logger.debug(
            "Calculating Boltztrap for {}".format(item['task_id']))

        bs_dict = item["band_structure_uniform"]['GGA']["uniform_bs"]
        bs_dict['structure'] = item['structure']
        bs = BandStructure.from_dict(bs_dict)
        st = bs.structure
        
        #projection are not available in the bs obj taken from the DB
        #either the DB has to be updated with projections or they need to be
        #loaded from the raw data
        projections = True if bs.projections else False
        
        
        
        
        try:
            if bs.is_spin_polarized:
                data_up = BandstructureLoader(bs,st,spin=1)
                data_dn = BandstructureLoader(bs,st,spin=-1)

                min_bnd = min(data_up.ebands.min(),data_dn.ebands.min())
                max_bnd = max(data_up.ebands.max(),data_dn.ebands.max())
                data_up.set_upper_lower_bands(min_bnd,max_bnd)
                data_dn.set_upper_lower_bands(min_bnd,max_bnd)
                bztI_up = BztInterpolator(data_up,energy_range=np.inf,curvature=False)
                bztI_dn = BztInterpolator(data_dn,energy_range=np.inf,curvature=False)
                
                
                #set a number of energy point according to a fix energy step 0.005 eV
                energy_grid = 0.005 * units.eV
                npts_mu = int((max_bnd - min_bnd) / energy_grid)
                dos_up = bztI_up.get_dos(partial_dos=projections,npts_mu=npts_mu)
                dos_dn = bztI_dn.get_dos(partial_dos=projections,npts_mu=npts_mu)
                cdos = merge_up_down_doses(dos_up,dos_dn)
                
            else:
                data = BandstructureLoader(bs,st)
                bztI = BztInterpolator(data,energy_range=np.inf,curvature=False)
                cdos = bztI.get_dos(partial_dos=projections)
        
            return {'mp_id':item['task_id'], 
                    'task_id':item['band_structure_uniform']['GGA']['task_id'], 
                    'cdos':cdos.as_dict()}

        except Exception as e:
            self.logger.warning(
                                "Error generating the dos for {}: \
                                {}".format(item["task_id"], e))
            
            raise
            return None

    def update_targets(self, items):
        """
        Inserts the new task_types into the task_types collection

        Args:
            items ([[dict]]): a list of list of dos dictionaries to update
        """
        items = list(filter(None, items))

        if len(items) > 0:
            self.logger.info("Updating {} boltztrap dos".format(len(items)))
            self.dos.update(docs=items)

        else:
            self.logger.info("No items to update")


