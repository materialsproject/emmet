from maggma.builder import Builder
from pymatgen.core.structure import Structure
from pymatgen.symmetry.bandstructure import HighSymmKpath
from pymatgen.electronic_structure.bandstructure import BandStructureSymmLine, BandStructure
from pymatgen.electronic_structure.dos import CompleteDos
from pymatgen.electronic_structure.plotter import BSDOSPlotter, DosPlotter, BSPlotter
import gridfs
import json

import zlib
import io
from datetime import datetime

__author__ = "Shyam Dwaraknath <shyamd@lbl.gov>"


class ElectronicStructureBuilder(Builder):

    def __init__(self, materials, electronic_structure, bandstructure_fs="bandstructure_fs", dos_fs="dos_fs", query={},
                 **kwargs):
        """
        Creates an electronic structure from a tasks collection, the associated band structures and density of states, and the materials structure

        :param tasks:
        :param materials:
        :param electronic_structure:
        """

        self.materials = materials
        self.electronic_structure = electronic_structure
        self.query = query
        self.bandstructure_fs = bandstructure_fs
        self.dos_fs = dos_fs

        super().__init__(sources=[materials],
                         targets=[electronic_structure],
                         **kwargs)

    def get_items(self):
        """
        Gets all items to process into materials documents

        Returns:
            generator or list relevant tasks and materials to process into materials documents
        """

        self.logger.info("Electronic Structure Builder Started")

        # only consider materials that were updated since the electronic structure was last updated
        # and there is either a dos or bandstructure
        q = dict(self.query)
        q.update(self.materials.lu_filter(self.electronic_structure))
        q["$or"] = [{"bandstructure.bs_oid": {"$exists": 1}},
                    {"bandstructure.dos_oid": {"$exists": 1}}]

        # initialize the gridfs
        bfs = gridfs.GridFS(
            self.materials.collection.database, self.bandstructure_fs)
        dfs = gridfs.GridFS(self.materials.collection.database, self.dos_fs)

        mats = list(self.materials.distinct(self.materials.key, criteria=q))

        for m in mats:

            mat = self.materials.query([self.materials.key, "structure", "bandstructure"],
                                       {self.materials.key: m}).limit(1)[0]

            # If a bandstructure oid exists
            if "bs_oid" in mat.get("bandstructure", {}):
                bs_json = bfs.get(mat["bandstructure"]["bs_oid"]).read()

                if "zlib" in mat["bandstructure"].get("bs_compression", ""):
                    bs_json = zlib.decompress(bs_json)

                bs_dict = json.loads(bs_json.decode())
                mat["bandstructure"]["bs"] = bs_dict

            if "dos_oid" in mat.get("bandstructure", {}):
                dos_json = dfs.get(mat["bandstructure"]["dos_oid"]).read()

                if "zlib" in mat["bandstructure"].get("dos_compression", ""):
                    dos_json = zlib.decompress(dos_json)

                dos_dict = json.loads(dos_json.decode())
                mat["bandstructure"]["dos"] = dos_dict

            yield mat

    def process_item(self, mat):
        """
        Process the tasks and materials into just a list of materials

        Args:
            mat (dict): material document

        Returns:
            (dict): electronic_structure document
        """

        self.logger.info("Processing: {}".format(mat[self.materials.key]))

        d = {self.materials.key: mat[self.materials.key], "bandstructure": {}}
        bs = None
        dos = None

        if "bs" in mat["bandstructure"]:
            try:
                struc = Structure.from_dict(mat["structure"])
                if "structure" not in mat["bandstructure"]["bs"]:
                    mat["bandstructure"]["bs"]["structure"] = struc
                if "labels_dict" not in mat["bandstructure"]["bs"]:
                    kpath = HighSymmKpath(struc)._kpath["kpoints"]
                    mat["bandstructure"]["bs"]["labels_dict"] = kpath

                # Somethign is wrong with the as_dict / from_dict encoding in the two band structure objects so have to use this hodge podge serialization
                # TODO: Fix bandstructure objects in pymatgen
                bs = BandStructureSymmLine.from_dict(
                    BandStructure.from_dict(mat["bandstructure"]["bs"]).as_dict())

            except Exception as e:
                self.logger.warning(
                    "Caught error in building bandstructure: {}".format(e))

        if "dos" in mat["bandstructure"]:
            dos = CompleteDos.from_dict(mat["bandstructure"]["dos"])

        try:
            plot = None
            if bs and dos:
                plotter = BSDOSPlotter()
                plot = plotter.get_plot(bs, dos)
                d["bandstructure"]["plot_type"] = "bsdos"
            elif bs:
                plotter = BSPlotter(bs)
                plot = plotter.get_plot()
                d["bandstructure"]["plot_type"] = "bs"
            elif dos:
                plotter = DosPlotter(dos)
                plot = plotter.get_plot()
                d["bandstructure"]["plot_type"] = "dos"
            if plot:
                imgdata = io.BytesIO()
                plot.savefig(imgdata, format="png", dpi=100)
                d["bandstructure"]["plot"] = imgdata.getvalue()
                plot.close()

        except Exception as e:
            self.logger.warning(
                "Caught error in electronic structure plotting: {}".format(e))
            return None

        return d

    def update_targets(self, items):
        """
        Inserts the new task_types into the task_types collection

        Args:
            items ([([dict],[int])]): A list of tuples of materials to update and the corresponding processed task_ids
        """
        items = list(filter(None, items))

        if len(items) > 0:
            self.logger.info("Updating {} band structures".format(len(items)))
            self.electronic_structure.update(items)
        else:
            self.logger.info("No items to update")
