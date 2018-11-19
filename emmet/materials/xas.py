import os
import numpy as np
from monty.serialization import loadfn
from pydash import py_
from pymatgen import Structure
from pymatgen.symmetry.analyzer import SpacegroupAnalyzer
from pymatgen.analysis.xas.spectrum import XANES

from maggma.builders import MapBuilder, GroupBuilder
from scipy.interpolate import interp1d

# Mapping from MP task ids / deprecated material ids to current material ids
# Most XAS calculations were done with reference to a past material id.
tid_mid = loadfn(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "settings", "tid_mid.json"))


class XASBuilder(MapBuilder):
    def __init__(self, calcs, xas, **kwargs):
        """MSONable site-specific spectra from calculations.

        Args:
            calcs (Store): XAS calculations with raw output
            xas (Store): output serialized pymatgen XANES objects
        """
        self.calcs = calcs
        self.xas = xas
        super().__init__(source=calcs, target=xas, **kwargs)

    @staticmethod
    def ufn(item):
        return msonify_xas(item)


def msonify_xas(item):
    energy = py_.pluck(item['spectrum'], 0) # (eV)
    intensity = py_.pluck(item['spectrum'], 3) # (mu)
    structure = Structure.from_dict(item['structure'])
    absorption_specie = structure[item['absorbing_atom']].species_string
    mid_and_el = ",".join([item["mp_id"], absorption_specie])
    edge = "K"
    structure.add_site_property(
        'absorbing_atom', [
            i == item['absorbing_atom']
            for i, _ in enumerate(structure.sites)
        ])
    if len(energy) == 0:
        return {"spectrum": None, "mid_and_el": mid_and_el,
                "error": "Empty spectrum"}
    try:
        out = {
            "spectrum": XANES(
                x=energy, y=intensity, structure=structure,
                absorption_specie=absorption_specie, edge=edge,
            ).as_dict(),
            "mid_and_el": mid_and_el,
        }
    except ValueError as e:
        out = {"spectrum": None, "mid_and_el": mid_and_el, "error": str(e)}
    return out


class XASAverager(GroupBuilder):
    def __init__(self, spectra_site, spectra_avg, **kwargs):
        self.spectra_site = spectra_site
        self.spectra_avg = spectra_avg
        super().__init__(source=spectra_site, target=spectra_avg, **kwargs)
        self.n_items_per_group = 1

    @staticmethod
    def grouping_properties():
        return ["mid_and_el"]

    @staticmethod
    def docs_to_groups(docs):
        return {d["mid_and_el"] for d in docs}

    def group_to_items(self, group):
        # XXX a list of docs is the one item yielded by this group.
        docs = list(self.source.query(criteria={"mid_and_el": group}))
        key_val = docs[0][self.source.key]
        lu_field_val = max(d[self.source.lu_field] for d in docs)

        return [{
            "xas_docs": docs,
            self.source.key: key_val,
            self.source.lu_field: lu_field_val
        }]

    @staticmethod
    def ufn(item):
        xas_docs = item["xas_docs"]
        mid_and_el = xas_docs[0]["mid_and_el"]
        mp_id, element = xas_docs[0]["mid_and_el"].split(",")
        msg = data_missing(xas_docs)
        if msg:
            out = {
                "spectrum": None,
                "mid_and_el": mid_and_el,
                "error": "Some sites have no spectra recorded: "+str(msg),
                "valid": False,
                "mp_id": tid_mid[mp_id],
                "element": element,
            }
        else:
            out = {
                "spectrum": site_weighted_spectrum(xas_docs).as_dict(),
                "mid_and_el": mid_and_el,
                "valid": True,
                "mp_id": tid_mid[mp_id],
                "element": element,
            }
        return out


def data_missing(xas_docs):
    """
    Do some sites have no spectra recorded?

    Checks symmetrically equivalent sites.
    """
    xas_docs = [d for d in xas_docs if "error" not in d]
    if len(xas_docs) == 0:
        return "No docs at all"
    spectra = [XANES.from_dict(d['spectrum']) for d in xas_docs]
    absorption_specie = spectra[0].absorption_specie
    ss = SymmSites(spectra[0].structure)
    absorbing_atoms = set([next(
        i for i, yes in
        enumerate(s.structure.site_properties['absorbing_atom']) if yes)
        for s in spectra])
    site_indices_with_absorption_specie = [
        i for i, site in enumerate(spectra[0].structure.sites)
        if site.species_and_occu.reduced_formula == absorption_specie
    ]
    some_sites_absent = any(
        len(set(ss.get_equivalent_site_indices(i)) & absorbing_atoms) == 0
        for i in site_indices_with_absorption_specie)
    some_spectra_empty = any(len(s.energy) == 0 for s in spectra)
    return ((some_sites_absent and
             ("absent sites", absorbing_atoms)
             ) or (some_spectra_empty and "empty spectra"))


class SymmSites:
    def __init__(self, structure):
        self.structure = structure
        sa = SpacegroupAnalyzer(self.structure)
        symm_data = sa.get_symmetry_dataset()
        # equivalency mapping for the structure
        # i'th site in the input structure equivalent to eq_atoms[i]'th site
        self.eq_atoms = symm_data["equivalent_atoms"]

    def get_equivalent_site_indices(self, i):
        """
        Site indices in the structure that are equivalent to the given site i.
        """
        rv = np.argwhere(self.eq_atoms == self.eq_atoms[i]).squeeze().tolist()
        if isinstance(rv, int):
            rv = [rv]
        return rv


def site_weighted_spectrum(xas_docs, num_samples=200):
    """
    Equivalent-site-weighted spectrum for a specie in a structure.

    Args:
        xas_docs (list): MongoDB docs for all XAS XANES K-edge spectra
            for a specie for a structure.
        num_samples (int): Number of samples for interpolation.
            Original data has 100 data points.

    Returns:
        tuple: a plottable (x, y) pair for the spectrum
    """
    maxes, mins = [], []
    fs = []
    multiplicities = []
    absorbing_atoms = set()

    spectra = [XANES.from_dict(d['spectrum']) for d in xas_docs]

    for spectrum in spectra:
        # Checking the multiplicities of sites
        structure = spectrum.structure
        sa = SpacegroupAnalyzer(structure)
        ss = sa.get_symmetrized_structure()
        absorbing_atom = next(
            i for i, yes in
            enumerate(structure.site_properties['absorbing_atom']) if yes)
        multiplicity = len(ss.find_equivalent_sites(structure[absorbing_atom]))
        multiplicities.append(multiplicity)

        # Getting axis limits for each spectrum for the sites corresponding to
        # K-edge is a bit tricky, because the x-axis data points don't align
        # among different spectra for the same structure. So, prepare for
        # interpolation within the intersection of x-axis ranges.
        mins.append(spectrum.energy[0])
        maxes.append(spectrum.energy[-1])

        # 3rd-order spline interpolation
        f = interp1d(
            spectrum.energy, spectrum.intensity,
            kind='cubic', bounds_error=False, fill_value=0)
        fs.append(f)

        absorbing_atoms |= set(
            SymmSites(structure).get_equivalent_site_indices(absorbing_atom))

    energy = np.linspace(max(mins), min(maxes), num=num_samples)
    weighted_intensity = np.zeros(num_samples)
    sum_multiplicities = sum(multiplicities)
    for i in range(len(multiplicities)):
        weighted_intensity += (
            multiplicities[i] * fs[i](energy)) / sum_multiplicities
    structure = spectra[0].structure
    structure.remove_site_property('absorbing_atom')
    structure.add_site_property(
        'absorbing_atom', [
            i in absorbing_atoms
            for i, _ in enumerate(structure.sites)
        ])
    return XANES(
        x=energy, y=weighted_intensity, structure=structure,
        absorption_specie=spectra[0].absorption_specie, edge=spectra[0].edge,
    )
