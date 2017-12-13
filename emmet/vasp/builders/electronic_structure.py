import gridfs
import json
import zlib
import io
import os
import traceback
from shutil import which

from datetime import datetime
from monty.tempfile import ScratchDir
from maggma.builder import Builder
from pymatgen.core.structure import Structure
from pymatgen.symmetry.bandstructure import HighSymmKpath
from pymatgen.electronic_structure.bandstructure import BandStructureSymmLine, BandStructure
from pymatgen.electronic_structure.dos import CompleteDos
from pymatgen.electronic_structure.plotter import BSDOSPlotter, DosPlotter, BSPlotter
from pymatgen.electronic_structure.boltztrap import BoltztrapRunner, BoltztrapAnalyzer

__author__ = "Shyam Dwaraknath <shyamd@lbl.gov>"


class ElectronicStructureBuilder(Builder):

    def __init__(self, materials, electronic_structure, bandstructure_fs="bandstructure_fs", dos_fs="dos_fs", query={},
                 interpolate_dos=True, small_plot=True, static_images=True, **kwargs):
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
        self.interpolate_dos = bool(interpolate_dos and which("x_trans"))
        self.small_plot = small_plot
        self.static_images = static_images

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
        self.bfs = gridfs.GridFS(
            self.materials.collection.database, self.bandstructure_fs)
        self.dfs = gridfs.GridFS(
            self.materials.collection.database, self.dos_fs)

        mats = list(self.materials.distinct(self.materials.key, criteria=q))

        for m in mats:

            mat = self.materials.query([self.materials.key, "structure", "bandstructure", "calc_settings"],
                                       {self.materials.key: m}).limit(1)[0]
            self.get_bandstructure(mat)
            self.get_dos(mat)
            if self.interpolate_dos:
                self.get_uniform_bandstructure(mat)

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

        d = {self.electronic_structure.key: mat[
            self.materials.key], "bandstructure": {}}
        bs = None
        dos = None
        interpolated_dos = None

        # Process the bandstructure for information
        if "bs" in mat["bandstructure"]:
            if "structure" not in mat["bandstructure"]["bs"]:
                mat["bandstructure"]["bs"]["structure"] = mat["structure"]
            if len(mat["bandstructure"]["bs"].get("labels_dict",{})) == 0:
                struc = Structure.from_dict(mat["structure"])
                kpath = HighSymmKpath(struc)._kpath["kpoints"]
                mat["bandstructure"]["bs"]["labels_dict"] = kpath
            # Somethign is wrong with the as_dict / from_dict encoding in the two band structure objects so have to use this hodge podge serialization
            # TODO: Fix bandstructure objects in pymatgen
            bs = BandStructureSymmLine.from_dict(
                BandStructure.from_dict(mat["bandstructure"]["bs"]).as_dict())
            d["bandstructure"]["band_gap"] = {"band_gap": bs.get_band_gap()["energy"],
                                              "direct_gap": bs.get_direct_band_gap(),
                                              "is_direct": bs.get_band_gap()["direct"],
                                              "transition": bs.get_band_gap()["transition"]}

            if self.small_plot:
                d["bandstructure"]["plot_small"] = get_small_plot(bs)

            except Exception:
                self.logger.warning(
                    "Caught error in building bandstructure for {}: {}".format(mat[self.materials.key],traceback.format_exc()))

        if "dos" in mat["bandstructure"]:
            dos = CompleteDos.from_dict(mat["bandstructure"]["dos"])

        if self.interpolate_dos and "uniform_bs" in mat["bandstructure"]:
            interpolated_dos = self.get_interpolated_dos(mat)

        # Generate static images
        if self.static_images:
            try:
                ylim = None
                if bs:
                    plotter = BSPlotter(bs)
                    fig = plotter.get_plot()
                    ylim = fig.ylim() # Used by DOS plot
                    fig.close()

                    d["bandstructure"]["bs_plot"] = image_from_plotter(plotter)

                if dos or interpolated_dos:
                    plotter = DosPlotter()
                    if interpolated_dos:
                        plotter.add_dos_dict(interpolated_dos.get_element_dos())
                    else:
                        plotter.add_dos_dict(dos.get_element_dos())
                    d["bandstructure"][
                        "dos_plot"] = image_from_plotter(plotter,ylim=ylim)

            except Exception:
                self.logger.warning(
                    "Caught error in electronic structure plotting for {}: {}".format(mat[self.materials.key],traceback.format_exc()))
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

    def get_bandstructure(self, mat):

        # If a bandstructure oid exists
        if "bs_oid" in mat.get("bandstructure", {}):
            bs_json = self.bfs.get(mat["bandstructure"]["bs_oid"]).read()

            if "zlib" in mat["bandstructure"].get("bs_compression", ""):
                bs_json = zlib.decompress(bs_json)

            bs_dict = json.loads(bs_json.decode())
            mat["bandstructure"]["bs"] = bs_dict

    def get_uniform_bandstructure(self, mat):

        # If a bandstructure oid exists
        if "uniform_bs_oid" in mat.get("bandstructure", {}):
            bs_json = self.bfs.get(mat["bandstructure"][
                                   "uniform_bs_oid"]).read()

            if "zlib" in mat["bandstructure"].get("uniform_bs_compression", ""):
                bs_json = zlib.decompress(bs_json)

            bs_dict = json.loads(bs_json.decode())
            mat["bandstructure"]["uniform_bs"] = bs_dict

    def get_dos(self, mat):

        # if a dos oid exists
        if "dos_oid" in mat.get("bandstructure", {}):
            dos_json = self.dfs.get(mat["bandstructure"]["dos_oid"]).read()

            if "zlib" in mat["bandstructure"].get("dos_compression", ""):
                dos_json = zlib.decompress(dos_json)

            dos_dict = json.loads(dos_json.decode())
            mat["bandstructure"]["dos"] = dos_dict

    def get_interpolated_dos(self, mat):

        nelect = mat["calc_settings"]["nelect"]

        bs_dict = mat["bandstructure"]["uniform_bs"]
        bs_dict["structure"] = mat['structure']
        bs = BandStructure.from_dict(bs_dict)

        if bs.is_spin_polarized:
            with ScratchDir("."):
                BoltztrapRunner(bs=bs,
                                nelec=nelect,
                                run_type="DOS",
                                dos_type="TETRA",
                                spin=1).run(path_dir=os.getcwd())
                an_up = BoltztrapAnalyzer.from_files("boltztrap/", dos_spin=1)

            with ScratchDir("."):
                BoltztrapRunner(bs=bs,
                                nelec=nelect,
                                run_type="DOS",
                                dos_type="TETRA",
                                spin=-1).run(path_dir=os.getcwd())
                an_dw = BoltztrapAnalyzer.from_files("boltztrap/", dos_spin=-1)

            cdos = an_up.get_complete_dos(bs.structure, an_dw)

        else:
            with ScratchDir("."):
                BoltztrapRunner(bs=bs,
                                nelec=nelect,
                                run_type="DOS",
                                dos_type="TETRA").run(path_dir=os.getcwd())
                an = BoltztrapAnalyzer.from_files("boltztrap/")
            cdos = an.get_complete_dos(bs.structure)

        return cdos

def image_from_plotter(plotter,ylim=None):
    plot = plotter.get_plot(ylim=ylim)
    imgdata = io.BytesIO()
    plot.savefig(imgdata, format="png", dpi=100)
    plot_img = imgdata.getvalue()
    plot.close()
    return plot_img


def get_small_plot(bs):

    plot_small = BSPlotter(bs).bs_plot_data()

    gap = bs.get_band_gap()["energy"]
    for branch in plot_small['energy']:
        for spin, v in branch.items():
            new_bands = []
            for band in v:
                if min(band) < gap + 3 and max(band) > -3:
                    new_bands.append(band)
            branch[spin] = new_bands
    return plot_small
