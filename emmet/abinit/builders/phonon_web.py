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
from pymatgen.phonon.plotter import PhononBSPlotter, PhononDosPlotter, freq_units, ThermoPlotter
from pymatgen.util.plotting import pretty_plot


matplotlib.use('agg')


class PhononWebBuilder(Builder):
    def __init__(self, pmg_bs_docs, pmg_dos_docs, ph_calc_docs, web_docs, images, ph_processed_docs,
                 ignore_lu=False, query=None, **kwargs):
        """
        Produce docs for interactive and static plots of phonon dispersion.
        Processed data are also included.

        Args:
            pmg_bs_docs (Store): source of serialized
                `pymatgen.phonon.bandstructure.PhononBandStructure` objects.
            pmg_dos_docs (Store): source of serialized
                `pymatgen.phonon.dos.CompletePhononDos` objects.
            ph_calc_docs (Store): source of other iformation directly extracted from
                the calculation results.
            web_docs (Store): target for data needed by interactive plots. The document
                may exceed the 16MB limit of the mongodb collections.
            images (Store): target for png images of phonon related quantities.
            ph_processed_docs (Store) target for other post-preocessed quantities.
            ignore_lu (bool): Ignore ph_calc_docs.lu_filter when getting items.
                Useful for forcing rebuilds given `add_filter`.
            query (dict): dictionary to limit the entries to be analyzed
        """
        self.pmg_bs_docs = pmg_bs_docs
        self.pmg_dos_docs = pmg_dos_docs
        self.ph_calc_docs = ph_calc_docs
        self.web_docs = web_docs
        self.images = images
        self.ph_processed_docs = ph_processed_docs
        self.ignore_lu = ignore_lu
        if query is None:
            query = {}
        self.query = query
        super().__init__(
            sources=[pmg_bs_docs, pmg_dos_docs, ph_calc_docs],
            targets=[web_docs, images, ph_processed_docs], **kwargs)

    def get_items(self):
        """
        Gets all materials that need phonons web data

        Returns:
            generator of materials to extract phonon properties
        """

        self.logger.info("Phonon Web Builder Started")

        # All relevant materials that have been updated since diffraction props were last calculated
        q = dict(self.query)
        if not self.ignore_lu:
            # q.update(self.ph_calc_docs.lu_filter(self.targets))
            q.update(self.ph_calc_docs.lu_filter(self.targets))
        self.logger.info("Filtering ph_calc_docs by {}".format(q))

        mats = list(self.ph_calc_docs.distinct(self.ph_calc_docs.key, criteria=q))
        self.logger.info("Found {} new materials for phonon data".format(len(mats)))

        for m in mats:

            item = {"ph_calc": self.ph_calc_docs.query_one(criteria={self.ph_calc_docs.key: m})}

            item["pmg_ph_bs"] = self.pmg_bs_docs.query_one(criteria={self.pmg_bs_docs.key: m})

            item["pmg_ph_dos"] = self.pmg_dos_docs.query_one(criteria={self.pmg_dos_docs.key: m})

            yield item

    def process_item(self, item):
        task_id = item['ph_calc'][self.ph_calc_docs.key]
        self.logger.debug("Processing {}".format(task_id))

        decoder = MontyDecoder()
        ph_bs = decoder.process_decoded(item['pmg_ph_bs']['ph_bs'])

        y_min = ph_bs.bands.min()
        y_max = ph_bs.bands.max()

        # neglect small negative frequencies (0.03 THz ~ 1 cm^-1)
        if -0.03 < y_min < 0:
            y_min = 0

        # increase the ymax to display all the top bands
        y_max += 0.08

        units = "cm-1"
        yfactor = freq_units(units).factor
        ylim = (y_min*yfactor, y_max*yfactor)

        bs_plotter = WebBSPlotter(ph_bs)
        ph_bs_image = image_from_plotter(bs_plotter, ylim, units="cm-1")

        ph_dos = decoder.process_decoded(item['pmg_ph_dos']['ph_dos'])
        dos_dict = ph_dos.get_element_dos()
        dos_plotter = WebPhononDosVertPlotter()
        if len(dos_dict) > 1:
            dos_plotter.add_dos("Total DOS", ph_dos)
        dos_plotter.add_dos_dict(dos_dict)
        ph_dos_image = image_from_plotter(dos_plotter, ylim, units="cm-1")

        web_doc = ph_bs.as_phononwebsite()
        # reduce the numerical representation of the eigendisplacements to reduce the size
        web_doc['vectors'] = reduce_eigendisplacements(web_doc['vectors'], figures=4, frac_threshold=1e-8).tolist()

        thermo_data, thermo_image = self.get_thermodynamic_properties(ph_dos)

        images = {"dos": ph_dos_image, "bs": ph_bs_image, "thermodynamic": thermo_image}
        self.logger.debug("image class {}".format(images["bs"].__class__))
        from monty.json import jsanitize
        self.logger.debug("image class after sanitize {}".format(jsanitize(images)["bs"].__class__))

        return {self.ph_calc_docs.key: item['ph_calc'][self.ph_calc_docs.key],
                "web_doc": web_doc, "images": images, "thermodynamic": thermo_data}

    def get_thermodynamic_properties(self, ph_dos):
        """
        Calculates the thermodynamic properties and prepare the figure with those values

        Args:
            ph_dos: A CompletePhononDos

        Returns:
            a dict containing the thermodynamic properties and a Binary object containg the figure
        """

        tstart, tstop, nt = 0, 800, 161
        temp = np.linspace(tstart, tstop, nt)

        cv = []
        entropy = []
        internal_energy = []
        helmholtz_free_energy = []

        for t in temp:
            cv.append(ph_dos.cv(t, ph_dos.structure))
            entropy.append(ph_dos.entropy(t, ph_dos.structure))
            internal_energy.append(ph_dos.internal_energy(t, ph_dos.structure))
            helmholtz_free_energy.append(ph_dos.helmholtz_free_energy(t, ph_dos.structure))

        thermo_data = {"temperature": temp.tolist(),
                       "cv": cv,
                       "entropy": entropy,
                       "internal_energy": internal_energy,
                       "helmholtz_free_energy": helmholtz_free_energy
                      }

        tplotter = ThermoPlotter(ph_dos)
        fig = tplotter.plot_thermodynamic_properties(tstart, tstop, nt, show=False)
        imgdata = io.BytesIO()
        fig.savefig(imgdata, format="png", dpi=100)
        thermo_image = Binary(imgdata.getvalue())

        return thermo_data, thermo_image

    def update_targets(self, items):
        # self.web_docs.ensure_index("mp-id", unique=True)
        # self.images.ensure_index("mp-id", unique=True)

        web_docs = [{self.web_docs.key: item[self.ph_calc_docs.key], "ph_bs": item["web_doc"]}
                    for item in items]
        self.web_docs.update(web_docs)

        images = [{self.images.key: item[self.ph_calc_docs.key],
                   "ph_bs_plot": item["images"]["bs"], "ph_dos_plot": item["images"]["dos"],
                   "thermodynamic_plot": item["images"]["thermodynamic"]} for item in items]
        self.images.update(images)

        processed_docs = [{self.ph_processed_docs.key: item[self.ph_calc_docs.key],
                                "thermodynamic": item["thermodynamic"]} for item in items]
        self.ph_processed_docs.update(processed_docs)

        mp_ids = py_.pluck(items, self.ph_calc_docs.key)

        self.logger.info("Updated targets for {}".format(mp_ids))

    # def validate_targets(self, n=0):
    #     self.logger.info("Validating {}".format(
    #         "all" if not n else "with sample size {}".format(n)))
    #     ids = self.web_docs.distinct("mp-id")
    #     sample_ids = py_.sample_size(ids, n) if n else ids
    #     criteria = {"mp-id": {"$in": sample_ids}}
    #     web_docs = self.web_docs.query(criteria=criteria)
    #     n_web_docs = web_docs.count()
    #     assert n_web_docs == len(sample_ids), "mp-id not unique in web_docs"
    #     images =self.images.query(criteria=criteria)
    #     n_images = images.count()
    #     assert n_web_docs == n_images, "counts for images and web_docs differ"
    #     for doc in web_docs:
    #         assert "ph_bs" in doc and doc["ph_bs"] is not None
    #     self.logger.info("Validated {} of web_docs".format(n_web_docs))
    #     for doc in images:
    #         assert "ph_bs_plot" in doc and doc["ph_bs_plot"] is not None
    #         assert "ph_dos_plot" in doc and doc["ph_dos_plot"] is not None
    #     self.logger.info("Validated {} of images".format(n_images))


class WebBSPlotter(PhononBSPlotter):
    """
    A plotter for the phonon BS suitable for visualization on the MP website.
    """

    def get_plot(self, ylim=None, units="thz"):
        """
        Get a matplotlib object for the bandstructure plot.

        Args:
            ylim: Specify the y-axis (frequency) limits; by default None let
                the code choose.
            units: units for the frequencies. Accepted values thz, ev, mev, ha, cm-1, cm^-1.
        """

        u = freq_units(units)

        plt = pretty_plot(6, 5.5)  # Was 12, 8

        matplotlib.rc('text', usetex=True)
        plt.rc('font', **{'family': 'serif', 'serif': ['Times New Roman']})

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
                         [data['frequency'][d][i][j] * u.factor
                          for j in range(len(data['distances'][d]))], 'b-',
                         linewidth=band_linewidth)


        self._maketicks(plt)

        # plot y=0 line
        plt.axhline(0, linewidth=1, color='k')

        # Main X and Y Labels
        plt.xlabel(r'$\mathrm{Wave\ Vector}$')
        plt.ylabel(r'$\mathrm{{Frequencies\ ({})}}$'.format(u.label))
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

    def get_plot(self, xlim=None, ylim=None, units="thz"):
        """
        Get a matplotlib plot showing the DOS.

        Args:
            xlim: Specifies the x-axis limits. Set to None for automatic
                determination.
            ylim: Specifies the y-axis limits.
            units: units for the frequencies. Accepted values thz, ev, mev, ha, cm-1, cm^-1.
        """

        u = freq_units(units)

        plt = pretty_plot(2, 5.5)

        matplotlib.rc('text', usetex=True)
        plt.rc('font', **{'family': 'serif', 'serif': ['Times New Roman']})

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
            frequencies = dos['frequencies'] * u.factor
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
                         label=str(key), linewidth=1)

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

        plt.ylabel(r'$\mathrm{{Frequencies\ ({})}}$'.format(u.label))
        plt.xlabel(r'$\mathrm{Density\ of\ states}$')

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
        # to accomodate the larger numbers of the cm^-1
        plt.subplots_adjust(left=0.3)

        return plt


def image_from_plotter(plotter, ylim=None, units="thz"):
    plot = plotter.get_plot(ylim=ylim, units=units)
    imgdata = io.BytesIO()
    plot.savefig(imgdata, format="png", dpi=100)
    plot_img = Binary(imgdata.getvalue())
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

    if isinstance(mantissas, float) or isinstance(mantissas, np.floating):
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
    Reduces the size of the json representation of the eigendisplacements in a phononwebsite json by tuncating
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
