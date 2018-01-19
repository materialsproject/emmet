import gridfs
import json
import zlib
import io
import os
import traceback
from shutil import which
from itertools import chain
import numpy as np
from monty.tempfile import ScratchDir
from monty.json import jsanitize
from maggma.builder import Builder
from pydash.objects import get
import prettyplotlib as ppl
import matplotlib
import scipy.interpolate as scint
from prettyplotlib import brewer2mpl
from pymatgen.core.structure import Structure
from pymatgen.symmetry.bandstructure import HighSymmKpath
from pymatgen.electronic_structure.core import Spin, Orbital
from pymatgen.electronic_structure.bandstructure import BandStructureSymmLine, BandStructure
from pymatgen.electronic_structure.dos import CompleteDos
from pymatgen.electronic_structure.plotter import DosPlotter, BSPlotter
from pymatgen.electronic_structure.boltztrap import BoltztrapRunner, BoltztrapAnalyzer
from pymatgen.util.plotting import pretty_plot

__author__ = "Shyam Dwaraknath <shyamd@lbl.gov>"

matplotlib.use('agg')


class ElectronicStructureBuilder(Builder):
    def __init__(self,
                 materials,
                 electronic_structure,
                 query={},
                 interpolate_dos=True,
                 small_plot=True,
                 static_images=True,
                 **kwargs):
        """
        Creates an electronic structure from a tasks collection, the associated band structures and density of states, and the materials structure

        Really only usefull for MP Website infrastructure right now. 

        materials (Store) : Store of materials documents
        electronic_structure  (Store) : Store of electronic structure documents
        query (dict): dictionary to limit tasks to be analyzed
        interpolate_dos (bool): interpolate DOS using BoltzTrap
        small_plot (bool): make a small plot dictionary for Bandstructure
        static_images (bool): generate static images of Bandstructure and DOS
        """

        self.materials = materials
        self.electronic_structure = electronic_structure
        self.query = query
        self.interpolate_dos = interpolate_dos
        self.__interpolate_dos = interpolate_dos and bool(which("x_trans"))
        self.small_plot = small_plot
        self.static_images = static_images

        super().__init__(sources=[materials], targets=[electronic_structure], **kwargs)

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
        q["$or"] = [{"bandstructure.bs_oid": {"$exists": 1}}, {"bandstructure.dos_oid": {"$exists": 1}}]

        # initialize the gridfs
        self.bfs = gridfs.GridFS(self.materials.collection.database, "bandstructure_fs")
        self.dfs = gridfs.GridFS(self.materials.collection.database, "dos_fs")
        self.plot_fs = gridfs.GridFS(self.materials.collection.database, "es_plot")

        mats = list(self.materials.distinct(self.materials.key, criteria=q))

        for m in mats:
            mat = self.materials.query_one(
                [self.materials.key, "structure", "bandstructure", "origins", "calc_settings", "inputs"], {
                    self.materials.key: m
                })
            self.get_bandstructure(mat)
            self.get_dos(mat)
            if self.__interpolate_dos:
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

        bs_dict = self.make_bs_doc(mat)
        dos_dict = self.make_dos_doc(mat)
        interpolated_dos_dict = self.make_interpolated_dos_doc(mat)

        # Generate static images
        if self.static_images:
            bs_ylim = None
            bs = BandStructureSymmLine.from_dict(bs_dict)
            try:
                plotter = WebBSPlotter(bs)
                bs_dict["bs_plot"] = image_from_plotter(plotter)

            except Exception:
                self.logger.warning("Caught error in bandstructure plotting for {}: {}".format(
                    mat[self.materials.key], traceback.format_exc()))
            try:
                plotter = WebDosVertPlotter()
                bs_ylim = self.get_bs_ylim(bs)
                if interpolated_dos_dict:
                    plotter.add_dos_dict(interpolated_dos.get_element_dos())
                    dos_dict["dos_plot"] = image_from_plotter(plotter, ylim=bs_ylim)
                elif dos_dict:
                    plotter.add_dos_dict(CompleteDos.from_dict(dos_dict).get_element_dos())
                    dos_dict["dos_plot"] = image_from_plotter(plotter, ylim=bs_ylim)

            except Exception:
                self.logger.warning("Caught error in bandstructure plotting for {}: {}".format(
                    mat[self.materials.key], traceback.format_exc()))

        return [bs_dict, dos_dict]

    def update_targets(self, items):
        """
        Inserts the new task_types into the task_types collection

        Args:
            items ([([dict],[int])]): A list of tuples of materials to update and the corresponding processed task_ids
        """
        items = list(filter(None, chain.from_iterable(items)))

        docs = []
        plots = {}

        for d in items:
            if "bs_plot" in d:
                plots["bs_{}.png".format(d["material_id"])] = d["bs_plot"]
                del d["bs_plot"]

            if "dos_plot" in d:
                plots["dos_{}.png".format(d["material_id"])] = d["dos_plot"]
                del d["dos_plot"]

            docs.append(jsanitize(d))

        if len(docs) > 0:
            self.logger.info("Updating {} electronic structure docs".format(len(docs)))
            try:
                self.electronic_structure.update(docs)
            except Exception:
                # Temporary fix for documents that are too large
                traceback.print_exc()

        if len(plots) > 0:
            self.logger.info("Updating {} plots".format(len(plots)))
            for filename, p in plots.items():
                self.plot_fs.put(p, filename=filename)
        else:
            self.logger.info("No electronic structure docs to update")

    #
    # These are all helper methods designed to take a chunk of code and provide a description
    #

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
            bs_json = self.bfs.get(mat["bandstructure"]["uniform_bs_oid"]).read()

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
                BoltztrapRunner(
                    bs=bs, nelec=nelect, run_type="DOS", dos_type="TETRA", spin=1, timeout=60).run(path_dir='dos_up/')
                an_up = BoltztrapAnalyzer.from_files("boltztrap/", dos_spin=1)

            with ScratchDir("."):
                BoltztrapRunner(
                    bs=bs, nelec=nelect, run_type="DOS", dos_type="TETRA", spin=-1,
                    timeout=60).run(path_dir=os.getcwd())
                an_dw = BoltztrapAnalyzer.from_files("boltztrap/", dos_spin=-1)

            cdos = an_up.get_complete_dos(bs.structure, an_dw)

        else:
            with ScratchDir("."):
                BoltztrapRunner(
                    bs=bs, nelec=nelect, run_type="DOS", dos_type="TETRA", timeout=60).run(path_dir=os.getcwd())
                an = BoltztrapAnalyzer.from_files("boltztrap/")
            cdos = an.get_complete_dos(bs.structure)

        return cdos

    def make_bs_doc(self, mat):

        bs_dict = None

        # Process the bandstructure for information
        if "bs" in mat["bandstructure"]:
            bs_dict = mat["bandstructure"]["bs"]
            # Add in structure if not already there
            if "structure" not in bs_dict:
                bs_dict["structure"] = mat["structure"]

            # Add in High Symm K Path if not already there
            if len(bs_dict.get("labels_dict", {})) == 0:
                labels = get(mat, "inputs.nscf_line.kpoints.labels", None)
                kpts = get(mat, "inputs.nscf_line.kpoints.kpoints", None)
                if labels and kpts:
                    labels_dict = dict(zip(labels, kpts))
                    labels_dict.pop(None, None)
                else:
                    struc = Structure.from_dict(mat["structure"])
                    labels_dict = HighSymmKpath(struc)._kpath["kpoints"]

                bs_dict["labels_dict"] = labels_dict

            # Somethign is wrong with the as_dict / from_dict encoding in the two band structure objects so have to use this hodge podge serialization
            # TODO: Fix bandstructure objects in pymatgen
            bs = BandStructureSymmLine.from_dict(BandStructure.from_dict(bs_dict).as_dict())

            bs_dict = bs.as_dict()

            if self.small_plot:
                bs_dict["plot_small"] = get_small_plot(bs)

            # Get basic bandgap properties
            bs_dict["band_gap"] = {
                "band_gap": bs.get_band_gap()["energy"],
                "direct_gap": bs.get_direct_band_gap(),
                "is_direct": bs.get_band_gap()["direct"],
                "transition": bs.get_band_gap()["transition"]
            }

            origin = next(origin for origin in mat.get("origins", []) if "Line" in origin["task_type"])

            if origin:
                bs_dict["task_id"] = origin["task_id"]
                bs_dict["material_id"] = mat[self.materials.key]

        return bs_dict

    def make_dos_doc(self, mat):

        dos_dict = None
        if "dos" in mat["bandstructure"]:
            dos_dict = mat["bandstructure"]["dos"]

            origin = next(origin for origin in mat.get("origins", []) if "Uniform" in origin["task_type"])

            if origin:
                dos_dict["task_id"] = origin["task_id"]
                dos_dict["material_id"] = mat[self.materials.key]

        return dos_dict

    def make_interpolated_dos_doc(self, mat):

        interpolated_dos = None
        if self.__interpolate_dos and "uniform_bs" in mat["bandstructure"]:
            try:
                interpolated_dos = self.get_interpolated_dos(mat)
            except Exception:
                self.logger.warning("Boltztrap interpolation failed for {}. Continuing with regular DOS".format(
                    mat[self.materials.key]))

        return interpolated_dos

    def get_bs_ylim(self, bs):
        plotter = WebBSPlotter(bs)
        fig = plotter.get_plot()
        ylim = fig.ylim()
        fig.close()
        return ylim


def image_from_plotter(plotter, ylim=None):
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


#
# Obtain web-friendly images by subclassing pymatgen plotters.
# Should eventually phase out to BSDOS Plotter
#


class WebBSPlotter(BSPlotter):
    def get_plot(self, zero_to_efermi=True, ylim=None, smooth=False):
        """
        get a matplotlib object for the bandstructure plot.
        Blue lines are up spin, red lines are down
        spin.
        Args:
            zero_to_efermi: Automatically subtract off the Fermi energy from
                the eigenvalues and plot (E-Ef).
            ylim: Specify the y-axis (energy) limits; by default None let
                the code choose. It is vbm-4 and cbm+4 if insulator
                efermi-10 and efermi+10 if metal
            smooth: interpolates the bands by a spline cubic
        """

        plt = pretty_plot(6, 5.5)  # Was 12, 8

        matplotlib.rc('text', usetex=True)

        width = 4
        ticksize = int(width * 2.5)
        axes = plt.gca()
        axes.set_title(axes.get_title(), size=width * 4)
        labelsize = int(width * 3)
        axes.set_xlabel(axes.get_xlabel(), size=labelsize)
        axes.set_ylabel(axes.get_ylabel(), size=labelsize)

        plt.xticks(fontsize=ticksize)
        plt.yticks(fontsize=ticksize)

        for axis in ['top', 'bottom', 'left', 'right']:
            axes.spines[axis].set_linewidth(0.5)

        # main internal config options
        e_min = -4
        e_max = 4
        if self._bs.is_metal():
            e_min = -10
            e_max = 10
        band_linewidth = 1  # Was 3 in pymatgen

        data = self.bs_plot_data(zero_to_efermi)
        if not smooth:
            for d in range(len(data['distances'])):
                for i in range(self._nb_bands):
                    plt.plot(
                        data['distances'][d],
                        [data['energy'][d][str(Spin.up)][i][j] for j in range(len(data['distances'][d]))],
                        'b-',
                        linewidth=band_linewidth)
                    if self._bs.is_spin_polarized:
                        plt.plot(
                            data['distances'][d],
                            [data['energy'][d][str(Spin.down)][i][j] for j in range(len(data['distances'][d]))],
                            'r--',
                            linewidth=band_linewidth)
        else:
            for d in range(len(data['distances'])):
                for i in range(self._nb_bands):
                    tck = scint.splrep(
                        data['distances'][d],
                        [data['energy'][d][str(Spin.up)][i][j] for j in range(len(data['distances'][d]))])
                    step = (data['distances'][d][-1] - data['distances'][d][0]) / 1000

                    plt.plot(
                        [x * step + data['distances'][d][0] for x in range(1000)],
                        [scint.splev(x * step + data['distances'][d][0], tck, der=0) for x in range(1000)],
                        'b-',
                        linewidth=band_linewidth)

                    if self._bs.is_spin_polarized:

                        tck = scint.splrep(
                            data['distances'][d],
                            [data['energy'][d][str(Spin.down)][i][j] for j in range(len(data['distances'][d]))])
                        step = (data['distances'][d][-1] - data['distances'][d][0]) / 1000

                        plt.plot(
                            [x * step + data['distances'][d][0] for x in range(1000)],
                            [scint.splev(x * step + data['distances'][d][0], tck, der=0) for x in range(1000)],
                            'r--',
                            linewidth=band_linewidth)
        self._maketicks(plt)

        # Main X and Y Labels
        plt.xlabel(r'$\mathrm{Wave\ Vector}$')
        ylabel = r'$\mathrm{E\ -\ E_f\ (eV)}$' if zero_to_efermi \
            else r'$\mathrm{Energy\ (eV)}$'
        plt.ylabel(ylabel)

        # Draw Fermi energy, only if not the zero
        if not zero_to_efermi:
            ef = self._bs.efermi
            plt.axhline(ef, linewidth=2, color='k')

        # X range (K)
        # last distance point
        x_max = data['distances'][-1][-1]
        plt.xlim(0, x_max)

        if ylim is None:
            if self._bs.is_metal():
                # Plot A Metal
                if zero_to_efermi:
                    plt.ylim(e_min, e_max)
                else:
                    plt.ylim(self._bs.efermi + e_min, self._bs._efermi + e_max)
            else:
                for cbm in data['cbm']:
                    plt.scatter(cbm[0], cbm[1], color='r', marker='o', s=100)

                for vbm in data['vbm']:
                    plt.scatter(vbm[0], vbm[1], color='g', marker='o', s=100)
                plt.ylim(data['vbm'][0][1] + e_min, data['cbm'][0][1] + e_max)
        else:
            plt.ylim(ylim)

        plt.tight_layout()

        return plt


class WebDosVertPlotter(DosPlotter):
    def get_plot(self, xlim=None, ylim=None, plt=None, handle_only=False):
        """
        Get a matplotlib plot showing the DOS.
        Args:
            xlim: Specifies the x-axis limits. Set to None for automatic
                determination.
            ylim: Specifies the y-axis limits.
            plt: Handle on existing plot.
            handle_only: Quickly return just a handle. Useful if this method
                raises an exception so that one can close() the figure.
        """

        plt = plt or pretty_plot(2, 5.5)
        if handle_only:
            return plt

        ncolors = max(3, len(self._doses))
        ncolors = min(9, ncolors)
        colors = brewer2mpl.get_map('Set1', 'qualitative', ncolors).mpl_colors

        y = None
        alldensities = []
        allenergies = []

        width = 4
        ticksize = int(width * 2.5)
        axes = plt.gca()
        axes.set_title(axes.get_title(), size=width * 4)
        labelsize = int(width * 3)
        axes.set_xlabel(axes.get_xlabel(), size=labelsize)
        axes.set_ylabel(axes.get_ylabel(), size=labelsize)
        axes.xaxis.labelpad = 6

        # Note that this complicated processing of energies is to allow for
        # stacked plots in matplotlib.
        for key, dos in self._doses.items():
            energies = dos['energies']
            densities = dos['densities']
            if not y:
                y = {Spin.up: np.zeros(energies.shape), Spin.down: np.zeros(energies.shape)}
            newdens = {}
            for spin in [Spin.up, Spin.down]:
                if spin in densities:
                    if self.stack:
                        y[spin] += densities[spin]
                        newdens[spin] = y[spin].copy()
                    else:
                        newdens[spin] = densities[spin]
            allenergies.append(energies)
            alldensities.append(newdens)

        keys = list(self._doses.keys())
        keys.reverse()
        alldensities.reverse()
        allenergies.reverse()
        allpts = []
        for i, key in enumerate(keys):
            x = []
            y = []
            for spin in [Spin.up, Spin.down]:
                if spin in alldensities[i]:
                    densities = list(int(spin) * alldensities[i][spin])
                    energies = list(allenergies[i])
                    if spin == Spin.down:
                        energies.reverse()
                        densities.reverse()
                    y.extend(energies)
                    x.extend(densities)
            allpts.extend(list(zip(x, y)))
            if self.stack:
                plt.fill(x, y, color=colors[i % ncolors], label=str(key))
            else:
                ppl.plot(x, y, color=colors[i % ncolors], label=str(key), linewidth=1)
            if not self.zero_at_efermi:
                xlim = plt.xlim()
                ppl.plot(
                    xlim, [self._doses[key]['efermi'], self._doses[key]['efermi']],
                    color=colors[i % ncolors],
                    linestyle='--',
                    linewidth=1)

        if ylim:
            print("Setting ylim to {}".format(ylim))
            plt.ylim(ylim)
        if xlim:
            plt.xlim(xlim)
        else:
            ylim = plt.ylim()
            relevantx = [p[0] for p in allpts if ylim[0] < p[1] < ylim[1]]
            plt.xlim(min(relevantx), max(relevantx))
        if self.zero_at_efermi:
            xlim = plt.xlim()
            plt.plot(xlim, [0, 0], 'k--', linewidth=1)

        plt.ylabel(r'$\mathrm{E\ -\ E_f\ (eV)}$')
        plt.xlabel(r'$\mathrm{Density\ of\ states}$')

        locs, _ = plt.xticks()
        plt.xticks([0], fontsize=ticksize)
        plt.yticks(fontsize=ticksize)
        plt.grid(which='major', axis='y')

        plt.legend(fontsize='x-small', loc='upper right', bbox_to_anchor=(1.15, 1))
        leg = plt.gca().get_legend()
        leg.get_frame().set_alpha(0.25)
        plt.tight_layout()
        return plt
