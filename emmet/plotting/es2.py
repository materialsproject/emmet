import io
import traceback
import prettyplotlib as ppl
import matplotlib
import numpy as np
from prettyplotlib import brewer2mpl
from maggma.builders import Builder
from pydash.objects import get
from pymatgen.electronic_structure.bandstructure import (
    BandStructureSymmLine,
    BandStructure,
)
from pymatgen.electronic_structure.core import Spin, Orbital
from pymatgen.symmetry.bandstructure import HighSymmKpath
from pymatgen.electronic_structure.dos import CompleteDos
from sumo.plotting.dos_plotter import SDOSPlotter
from sumo.plotting.bs_plotter import SBSPlotter
from sumo.electronic_structure.dos import get_pdos
from pymatgen.electronic_structure.plotter import DosPlotter, BSPlotter
from pymatgen.util.plotting import pretty_plot

import seaborn as sns
sns.set(style='ticks', palette='Set2')
sns.despine()


__author__ = "Shyam Dwaraknath <shyamd@lbl.gov>"


class ElectronicStructureImageBuilder(Builder):
    def __init__(
        self,
        materials,
        electronic_structure,
        bandstructures,
        dos,
        query=None,
        plot_options=None,
        **kwargs
    ):
        """
        Creates an electronic structure from a tasks collection, the associated band structures and density of states, and the materials structure

        Really only usefull for MP Website infrastructure right now.

        materials (Store) : Store of materials documents
        electronic_structure  (Store) : Store of electronic structure documents
        bandstructures (Store) : store of bandstructures
        dos (Store) : store of DOS
        plot_options (dict): options to pass to the sumo SBSPlotter
        query (dict): dictionary to limit tasks to be analyzed
        """

        self.materials = materials
        self.electronic_structure = electronic_structure
        self.bandstructures = bandstructures
        self.dos = dos
        self.query = query if query else {}
        self.plot_options = plot_options if plot_options else {}

        super().__init__(
            sources=[materials, bandstructures, dos],
            targets=[electronic_structure],
            **kwargs
        )

    def get_items(self):
        """
        Gets all items to process into materials documents

        Returns:
            generator or list relevant tasks and materials to process into materials documents
        """

        self.logger.info("Electronic Structure Builder Started")

        # get all materials without an electronic_structure document but bandstructure and dos fields
        # and there is either a dos or bandstructure
        q = dict(self.query)
        q["$and"] = [
            {"bandstructure.bs_task": {"$exists": 1}},
            {"bandstructure.dos_task": {"$exists": 1}},
        ]
        mat_ids = list(self.materials.distinct(self.materials.key, criteria=q))
        es_ids = self.electronic_structure.distinct("task_id")

        # get all materials that were updated since the electronic structure was last updated
        # and there is either a dos or bandstructure
        q = dict(self.query)
        q.update(self.materials.lu_filter(self.electronic_structure))
        q["$and"] = [
            {"bandstructure.bs_task": {"$exists": 1}},
            {"bandstructure.dos_task": {"$exists": 1}},
        ]
        mats = set(self.materials.distinct(self.materials.key, criteria=q)) | (
            set(mat_ids) - set(es_ids)
        )

        self.logger.debug(
            "Processing {} materials for electronic structure".format(len(mats))
        )

        self.total = len(mats)

        for m in mats:
            mat = self.materials.query_one(
                {self.materials.key: m},
                [self.materials.key, "structure", "bandstructure", "inputs"],
            )
            mat["bandstructure"]["bs"] = self.bandstructures.query_one(
                criteria={"task_id": get(mat, "bandstructure.bs_task")}
            )

            mat["bandstructure"]["dos"] = self.dos.query_one(
                criteria={"task_id": get(mat, "bandstructure.dos_task")}
            )
            yield mat

    def process_item(self, mat):
        """
        Process the tasks and materials into just a list of materials

        Args:
            mat (dict): material document

        Returns:
            (dict): electronic_structure document
        """
        d = {self.electronic_structure.key: mat[self.materials.key]}
        self.logger.info("Processing: {}".format(mat[self.materials.key]))

        bs = build_bs(mat["bandstructure"]["bs"], mat)
        dos = CompleteDos.from_dict(mat["bandstructure"]["dos"])

        # Plot Band structure
        if bs:
            try:
                plotter = WebBSPlotter(bs)
                plot = plotter.get_plot()
                ylim = plot.ylim()
                d["bs_plot"] = image_from_plot(plot)
                plot.close()
            except Exception:
                self.logger.warning(
                    "Caught error in bandstructure plotting for {}: {}".format(
                        mat[self.materials.key], traceback.format_exc()
                    )
                )

        # Reduced Band structure plot
        try:
            gap = bs.get_band_gap()["energy"]
            plot_data = plotter.bs_plot_data()
            d["bs_plot_small"] = get_small_plot(plot_data, gap)
        except Exception:
            self.logger.warning(
                "Caught error in generating reduced bandstructure plot for {}: {}".format(
                    mat[self.materials.key], traceback.format_exc()
                )
            )

        # Plot DOS
        if dos:
            try:
                plotter = WebDosVertPlotter()
                plotter.add_dos_dict(dos.get_element_dos())
                plot = plotter.get_plot(ylim=ylim)
                d["dos_plot"] = image_from_plot(plot)
                plot.close()
            except Exception:
                self.logger.warning(
                    "Caught error in dos plotting for {}: {}".format(
                        mat[self.materials.key], traceback.format_exc()
                    )
                )

        # Store task_ids
        for k in ["bs_task", "dos_task", "uniform_task"]:
            if k in mat["bandstructure"]:
                d[k] = mat["bandstructure"][k]

        return d

    def update_targets(self, items):
        """
        Inserts the new task_types into the task_types collection

        Args:
            items ([([dict],[int])]): A list of tuples of materials to update and the corresponding processed task_ids
        """
        items = list(filter(None, items))

        if len(items) > 0:
            self.logger.info("Updating {} electronic structure docs".format(len(items)))
            self.electronic_structure.update(items)
        else:
            self.logger.info("No electronic structure docs to update")


def get_small_plot(plot_data, gap):
    for branch in plot_data["energy"]:
        for spin, v in branch.items():
            new_bands = []
            for band in v:
                if min(band) < gap + 3 and max(band) > -3:
                    new_bands.append(band)
                else:
                    new_bands.append([])
            branch[spin] = new_bands
    return plot_data


def image_from_plot(plot):
    imgdata = io.BytesIO()
    plot.tight_layout()
    plot.savefig(imgdata, format="png", dpi=100)
    plot_img = imgdata.getvalue()
    return plot_img


def build_bs(bs_dict, mat):

    bs_dict["structure"] = mat["structure"]

    # Add in High Symm K Path if not already there
    if len(bs_dict.get("labels_dict", {})) == 0:
        labels = get(mat, "inputs.nscf_line.kpoints.labels", None)
        kpts = get(mat, "inputs.nscf_line.kpoints.kpoints", None)
        if labels and kpts:
            labels_dict = dict(zip(labels, kpts))
            labels_dict.pop(None, None)
        else:
            struc = Structure.from_dict(bs_dict["structure"])
            labels_dict = HighSymmKpath(struc)._kpath["kpoints"]

        bs_dict["labels_dict"] = labels_dict

    # This is somethign to do with BandStructureSymmLine's from dict being problematic
    bs = BandStructureSymmLine.from_dict(bs_dict)

    return bs


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

        matplotlib.rc("text", usetex=True)

        width = 4
        ticksize = int(width * 2.5)
        axes = plt.gca()
        axes.set_title(axes.get_title(), size=width * 4)
        labelsize = int(width * 3)
        axes.set_xlabel(axes.get_xlabel(), size=labelsize)
        axes.set_ylabel(axes.get_ylabel(), size=labelsize)

        plt.xticks(fontsize=ticksize)
        plt.yticks(fontsize=ticksize)

        for axis in ["top", "bottom", "left", "right"]:
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
            for d in range(len(data["distances"])):
                for i in range(self._nb_bands):
                    plt.plot(
                        data["distances"][d],
                        [
                            data["energy"][d][str(Spin.up)][i][j]
                            for j in range(len(data["distances"][d]))
                        ],
                        "b-",
                        linewidth=band_linewidth,
                    )
                    if self._bs.is_spin_polarized:
                        plt.plot(
                            data["distances"][d],
                            [
                                data["energy"][d][str(Spin.down)][i][j]
                                for j in range(len(data["distances"][d]))
                            ],
                            "r--",
                            linewidth=band_linewidth,
                        )
        else:
            for d in range(len(data["distances"])):
                for i in range(self._nb_bands):
                    tck = scint.splrep(
                        data["distances"][d],
                        [
                            data["energy"][d][str(Spin.up)][i][j]
                            for j in range(len(data["distances"][d]))
                        ],
                    )
                    step = (data["distances"][d][-1] - data["distances"][d][0]) / 1000

                    plt.plot(
                        [x * step + data["distances"][d][0] for x in range(1000)],
                        [
                            scint.splev(x * step + data["distances"][d][0], tck, der=0)
                            for x in range(1000)
                        ],
                        "b-",
                        linewidth=band_linewidth,
                    )

                    if self._bs.is_spin_polarized:

                        tck = scint.splrep(
                            data["distances"][d],
                            [
                                data["energy"][d][str(Spin.down)][i][j]
                                for j in range(len(data["distances"][d]))
                            ],
                        )
                        step = (
                            data["distances"][d][-1] - data["distances"][d][0]
                        ) / 1000

                        plt.plot(
                            [x * step + data["distances"][d][0] for x in range(1000)],
                            [
                                scint.splev(
                                    x * step + data["distances"][d][0], tck, der=0
                                )
                                for x in range(1000)
                            ],
                            "r--",
                            linewidth=band_linewidth,
                        )
        self._maketicks(plt)

        # Main X and Y Labels
        plt.xlabel(r"$\mathrm{Wave\ Vector}$")
        ylabel = (
            r"$\mathrm{E\ -\ E_f\ (eV)}$"
            if zero_to_efermi
            else r"$\mathrm{Energy\ (eV)}$"
        )
        plt.ylabel(ylabel)

        # Draw Fermi energy, only if not the zero
        if not zero_to_efermi:
            ef = self._bs.efermi
            plt.axhline(ef, linewidth=2, color="k")

        # X range (K)
        # last distance point
        x_max = data["distances"][-1][-1]
        plt.xlim(0, x_max)

        if ylim is None:
            if self._bs.is_metal():
                # Plot A Metal
                if zero_to_efermi:
                    plt.ylim(e_min, e_max)
                else:
                    plt.ylim(self._bs.efermi + e_min, self._bs._efermi + e_max)
            else:
                for cbm in data["cbm"]:
                    plt.scatter(cbm[0], cbm[1], color="r", marker="o", s=100)

                for vbm in data["vbm"]:
                    plt.scatter(vbm[0], vbm[1], color="g", marker="o", s=100)
                plt.ylim(data["vbm"][0][1] + e_min, data["cbm"][0][1] + e_max)
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
        colors = brewer2mpl.get_map("Set1", "qualitative", ncolors).mpl_colors

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
            energies = dos["energies"]
            densities = dos["densities"]
            if not y:
                y = {
                    Spin.up: np.zeros(energies.shape),
                    Spin.down: np.zeros(energies.shape),
                }
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
                plt.plot(x, y, color=colors[i % ncolors], label=str(key), linewidth=1)
            if not self.zero_at_efermi:
                xlim = plt.xlim()
                plt.plot(
                    xlim,
                    [self._doses[key]["efermi"], self._doses[key]["efermi"]],
                    color=colors[i % ncolors],
                    linestyle="--",
                    linewidth=1,
                )

        if ylim:
            plt.ylim(ylim)
        if xlim:
            plt.xlim(xlim)
        else:
            ylim = plt.ylim()
            relevantx = [p[0] for p in allpts if ylim[0] < p[1] < ylim[1]]
            plt.xlim(min(relevantx), max(relevantx))
        if self.zero_at_efermi:
            xlim = plt.xlim()
            plt.plot(xlim, [0, 0], "k--", linewidth=1)

        plt.ylabel(r"$\mathrm{E\ -\ E_f\ (eV)}$")
        plt.xlabel(r"$\mathrm{Density\ of\ states}$")

        locs, _ = plt.xticks()
        plt.xticks([0], fontsize=ticksize)
        plt.yticks(fontsize=ticksize)
        plt.grid(which="major", axis="y")

        plt.legend(fontsize="x-small", loc="upper right", bbox_to_anchor=(1.15, 1))
        leg = plt.gca().get_legend()
        leg.get_frame().set_alpha(0.25)
        plt.tight_layout()
        return plt

