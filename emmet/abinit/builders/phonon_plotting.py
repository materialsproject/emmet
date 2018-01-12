import io

from bson.binary import Binary
from maggma.builder import Builder
from pydash import py_

import numpy as np
import decimal
import prettyplotlib as ppl
from prettyplotlib import brewer2mpl
import matplotlib
from monty.json import MontyDecoder
from pymatgen.phonon.plotter import PhononBSPlotter, PhononDosPlotter
from pymatgen.util.plotting import pretty_plot


matplotlib.use('agg')


class PhononDispersionPlotter(Builder):
    def __init__(self, pmg_docs, web_docs, images,
                 add_filter=None, ignore_lu=False, **kwargs):
        """
        Produce docs for interactive and static plots of phonon dispersion.

        Args:
            pmg_docs (Store): source of serialized
                `pymatgen.phonon.bandstructure.PhononBandStructure` objects.
            web_docs (Store): target for data needed by interactive plots.
            images (Store): target for png images of phonon dispersion plots.
            add_filter (dict): MongoDB filter to add to default last-updated
                filter.
            ignore_lu (bool): Ignore pmg_docs.lu_filter when getting items.
                Useful for forcing rebuilds given `add_filter`.
        """
        self.pmg_docs = pmg_docs
        self.web_docs = web_docs
        self.images = images
        self.add_filter = add_filter if add_filter else {}
        self.ignore_lu = ignore_lu
        super().__init__(
            sources=[pmg_docs], targets=[web_docs, images], **kwargs)

    def get_items(self):
        lu_filter = self.pmg_docs.lu_filter([self.web_docs, self.images])
        filter_ = {} if self.ignore_lu else lu_filter.copy()
        filter_.update(self.add_filter)
        self.logger.info("Filtering pmg_docs by {}".format(filter_))
        cursor = self.pmg_docs.query(criteria=filter_)
        self.logger.info("Found {} pmg_docs to process".format(cursor.count()))
        if cursor.count() == 0:
            n_updated = self.pmg_docs.query(criteria=lu_filter).count()
            self.logger.debug("{} updated pmg_docs that do not match"
                              " `add_filter`".format(n_updated))
        return cursor

    def process_item(self, item):
        mp_id = item['mp-id']
        self.logger.debug("Processing {}".format(mp_id))

        decoder = MontyDecoder()
        ph_bs = decoder.process_decoded(item['ph_bs'])

        y_min = ph_bs.bands.min()
        y_max = ph_bs.bands.max()

        # neglect small negative frequencies (0.03 THz ~ 1 cm^-1)
        if -0.03 < y_min < 0:
            y_min = 0

        # increase the ymax to display all the top bands
        y_max += 0.08

        ylim = (y_min, y_max)

        bs_plotter = WebBSPlotter(ph_bs)
        ph_bs_image = image_from_plotter(bs_plotter, ylim)

        ph_dos = decoder.process_decoded(item['ph_dos'])
        dos_plotter = WebPhononDosVertPlotter()
        dos_plotter.add_dos("Total DOS", ph_dos)
        dos_plotter.add_dos_dict(ph_dos.get_element_dos())
        ph_dos_image = image_from_plotter(dos_plotter, ylim)

        web_doc = ph_bs.as_phononwebsite()
        # reduce the numerical representation of the eigendisplacements to reduce the size
        web_doc['vectors'] = reduce_eigendisplacements(web_doc['vectors'], figures=4, frac_threshold=1e-8).tolist()

        return dict(mp_id=mp_id, web_doc=web_doc, ph_bs_image=ph_bs_image, ph_dos_image=ph_dos_image)

    def update_targets(self, items):
        self.web_docs.ensure_index("mp-id", unique=True)
        self.images.ensure_index("mp-id", unique=True)

        web_docs = [{"mp-id": item["mp_id"], "ph_bs": item["web_doc"]}
                    for item in items]
        self.web_docs.update(web_docs)

        images = [{"mp-id": item["mp_id"], "ph_bs_plot": item["ph_bs_image"],
                   "ph_dos_plot": item["ph_dos_image"]} for item in items]
        self.images.update(images)
        mp_ids = py_.pluck(items, "mp_id")

        self.logger.info("Updated targets for {}".format(mp_ids))

    def validate_targets(self, n=0):
        self.logger.info("Validating {}".format(
            "all" if not n else "with sample size {}".format(n)))
        ids = self.web_docs.distinct("mp-id")
        sample_ids = py_.sample_size(ids, n) if n else ids
        criteria = {"mp-id": {"$in": sample_ids}}
        web_docs = self.web_docs.query(criteria=criteria)
        n_web_docs = web_docs.count()
        assert n_web_docs == len(sample_ids), "mp-id not unique in web_docs"
        images =self.images.query(criteria=criteria)
        n_images = images.count()
        assert n_web_docs == n_images, "counts for images and web_docs differ"
        for doc in web_docs:
            assert "ph_bs" in doc and doc["ph_bs"] is not None
        self.logger.info("Validated {} of web_docs".format(n_web_docs))
        for doc in images:
            assert "ph_bs_plot" in doc and doc["ph_bs_plot"] is not None
            assert "ph_dos_plot" in doc and doc["ph_dos_plot"] is not None
        self.logger.info("Validated {} of images".format(n_images))


class WebBSPlotter(PhononBSPlotter):
    """
    A plotter for the phonon BS suitable for visualization on the MP website.
    """

    def get_plot(self, ylim=None):
        """
        Get a matplotlib object for the bandstructure plot.

        Args:
            ylim: Specify the y-axis (frequency) limits; by default None let
                the code choose.
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

        band_linewidth = 1

        data = self.bs_plot_data()
        for d in range(len(data['distances'])):
            for i in range(self._nb_bands):
                plt.plot(data['distances'][d],
                         [data['frequency'][d][i][j]
                          for j in range(len(data['distances'][d]))], 'b-',
                         linewidth=band_linewidth)


        self._maketicks(plt)

        # plot y=0 line
        plt.axhline(0, linewidth=1, color='k')

        # Main X and Y Labels
        plt.xlabel(r'$\mathrm{Wave\ Vector}$')
        plt.ylabel(r'$\mathrm{Frequency\ (THz)}$')

        # X range (K)
        # last distance point
        x_max = data['distances'][-1][-1]
        plt.xlim(0, x_max)

        if ylim is not None:
            plt.ylim(ylim)

        plt.tight_layout()

        return plt


class WebPhononDosVertPlotter(PhononDosPlotter):
    """
    A plotter for the phonon DOS suitable for visualization on the MP website.
    """

    def get_plot(self, xlim=None, ylim=None):
        """
        Get a matplotlib plot showing the DOS.

        Args:
            xlim: Specifies the x-axis limits. Set to None for automatic
                determination.
            ylim: Specifies the y-axis limits.
        """

        plt = pretty_plot(2, 5.5)

        ncolors = max(3, len(self._doses))
        ncolors = min(9, ncolors)
        colors = brewer2mpl.get_map('Set1', 'qualitative', ncolors).mpl_colors

        y = None
        alldensities = []
        allfrequencies = []

        width = 4
        ticksize = int(width * 2.5)
        axes = plt.gca()
        axes.set_title(axes.get_title(), size=width * 4)
        labelsize = int(width * 3)
        axes.set_xlabel(axes.get_xlabel(), size=labelsize)
        axes.set_ylabel(axes.get_ylabel(), size=labelsize)
        axes.xaxis.labelpad = 6

        # Note that this complicated processing of frequencies is to allow for
        # stacked plots in matplotlib.
        for key, dos in self._doses.items():
            frequencies = dos['frequencies']
            densities = dos['densities']
            if y is None:
                y = np.zeros(frequencies.shape)
            if self.stack:
                y += densities
                newdens = y.copy()
            else:
                newdens = densities
            allfrequencies.append(frequencies)
            alldensities.append(newdens)

        keys = list(self._doses.keys())
        keys.reverse()
        alldensities.reverse()
        allfrequencies.reverse()
        allpts = []
        for i, (key, frequencies, densities) in enumerate(zip(keys, allfrequencies, alldensities)):
            allpts.extend(list(zip(densities, frequencies)))
            if self.stack:
                plt.fill(densities, color=colors[i % ncolors],
                         label=str(key))
            else:
                ppl.plot(densities, frequencies, color=colors[i % ncolors],
                         label=str(key), linewidth=3)

        if ylim:
            plt.ylim(ylim)

        if xlim:
            plt.xlim(xlim)
        else:
            ylim = plt.ylim()
            relevantx = [p[0] for p in allpts
                         if ylim[0] < p[1] < ylim[1]]
            plt.xlim((min(relevantx), max(relevantx)))

        xlim = plt.xlim()
        plt.plot(xlim, [0, 0], 'k-', linewidth=1)

        plt.ylabel('Frequencies (THz)')
        plt.xlabel('Density of states')

        locs, _ = plt.xticks()
        plt.xticks([0], fontsize=ticksize)
        plt.yticks(fontsize=ticksize)
        plt.grid(which='major', axis='y')

        # add legend only if more than one dos is present
        if len(keys) > 1:
            plt.legend(fontsize='x-small',
                       loc='upper right', bbox_to_anchor=(1.15, 1))
            leg = plt.gca().get_legend()
            leg.get_frame().set_alpha(0.25)

        plt.tight_layout()

        return plt


def image_from_plotter(plotter, ylim=None):
    plot = plotter.get_plot(ylim=ylim)
    imgdata = io.BytesIO()
    plot.savefig(imgdata, format="png", dpi=100)
    plot_img = imgdata.getvalue()
    plot.close()
    return plot_img


logBase10of2 = float(decimal.Decimal(2).log10())

def round_to_sig_figures(x, figures):
    """
    Helper function to round the value to a specific number of significant figures.
    Based on the implementation from Sean E. Lake:
    https://github.com/odysseus9672/SELPythonLibs/blob/master/SigFigRounding.py

    Args:
        x: a numpy array with real values
        figures: number of significant figures
    Returns:
        A numpy array rounded to the number of significant figures
    """

    xsgn = np.sign(x)
    absx = xsgn * x
    mantissas, binaryExponents = np.frexp(absx)

    decimalExponents = logBase10of2 * binaryExponents
    omags = np.floor(decimalExponents)

    mantissas *= 10.0 ** (decimalExponents - omags)

    if type(mantissas) is float or isinstance(mantissas, np.floating):
        if mantissas < 1.0:
            mantissas *= 10.0
            omags -= 1.0

    else:  # elif np.all(np.isreal( mantissas )):
        fixmsk = mantissas < 1.0
        mantissas[fixmsk] *= 10.0
        omags[fixmsk] -= 1.0

    result = xsgn * np.around(mantissas, decimals=figures - 1) * 10.0 ** omags

    return result


def reduce_eigendisplacements(eigdispl, figures=4, frac_threshold=1e-8):
    """
    Reduces the size of the json representation of the eigendisplacements in a phononwebsite jason by tuncating
    the numerical representation of the eigendisplacements to a given number of significant figures and setting to
    zero eigendisplacements with value lower than a threshold.

    Args:
        eigdispl: An array like object containing the eigendisplacements.
        figures: The number of decimals that should be preserved.
        frac_threshold: all the elements of eigdispl with absolute value smaller
            than man(eigdispl)*frac_threshold  will be set to zero.
    Returns:
        A numpy array with the same shape as eigdispl with the reduced eigendisplacements
    """

    red_eigdispl = round_to_sig_figures(np.array(eigdispl), figures)

    red_eigdispl[np.abs(red_eigdispl) < np.max(red_eigdispl)*frac_threshold] = 0.

    return red_eigdispl