from maggma.core import Store
from maggma.builders import GroupBuilder
from typing import List, Dict, Tuple

import traceback
from datetime import datetime
from itertools import groupby, product, chain
from pydash import py_
from pymatgen import Structure
import numpy as np

from pymatgen.analysis.xas.spectrum import XAS
from pymatgen.symmetry.analyzer import SpacegroupAnalyzer
from scipy.interpolate import interp1d
from emmet.vasp.materials import structure_metadata
from monty.json import jsanitize


class XASBuilder(GroupBuilder):
    """
    Generates XAS Docs for the API from FEFF Tasks collection
    """

    def __init__(
    def __init__(self, tasks: Store, xas: Store, sampling_density: float = 4, **kwargs):
        """
        Args:
            tasks: source store of FEFF tasks to process
            xas: target store to put processed XAS Tasks into
            sampling_density: the sampling density in number of points per eV 
        """
        self.tasks = tasks
        self.xas = xas
        self.sampling_density = sampling_density
        self.kwargs = kwargs

        super().__init__(source=tasks, target=xas, grouping_keys=["mp_id"], **kwargs)

    def process_item(self, items: List[Dict]) -> Dict[Tuple, Dict]:  # type: ignore

        keys = list(d[self.source.key] for d in items)

        self.logger.debug("Processing: {}".format(keys))

        try:
            all_spectra = [feff_task_to_spectrum(task) for task in items]

            # Dictionary of all site to spectra mapping
            sites_to_spectra = {
                index: list(group)
                for index, group in groupby(
                    sorted(all_spectra, key=lambda x: x.absorbing_atom),
                    key=lambda x: x.absorbing_atom,
                )
            }

            # perform spectra merging
            for site, spectra in sites_to_spectra.items():
                type_to_spectra = {
                    index: list(group)
                    for index, group in groupby(
                        sorted(
                            spectra,
                            key=lambda x: (x.edge, x.spectrum_type, x.last_updated),
                        ),
                        key=lambda x: (x.edge, x.spectrum_type),
                    )
                }
                # Make K-Total
                if ("K", "XANES") in type_to_spectra and (
                    "K",
                    "EXAFS",
                ) in type_to_spectra:
                    try:
                        xanes = type_to_spectra[("K", "XANES")][-1]
                        exafs = type_to_spectra[("K", "EXAFS")][-1]
                        total_spectrum = xanes.stitch(exafs, mode="XAFS")
                        total_spectrum.absorbing_atom = site
                        all_spectra.append(total_spectrum)
                    except Exception:
                        pass

                # Make L23
                if ("L2", "XANES") in type_to_spectra and (
                    "L3",
                    "XANES",
                ) in type_to_spectra:
                    try:
                        l2 = type_to_spectra[("L2", "XANES")][-1]
                        l3 = type_to_spectra[("L3", "XANES")][-1]
                        total_spectrum = l2.stitch(l3, mode="L23")
                        total_spectrum.absorbing_atom = site
                        all_spectra.append(total_spectrum)
                    except Exception:
                        pass

            # Site-weighted averaging
            elements = {spectrum.absorbing_element for spectrum in all_spectra}
            edges = {spectrum.edge for spectrum in all_spectra}
            types = {spectrum.spectrum_type for spectrum in all_spectra}

            averaged_spectra = []

            for element, edge, spectrum_type in product(elements, edges, types):
                relevant_spectra = [
                    spectrum
                    for spectrum in all_spectra
                    if spectrum.absorbing_element == element
                    and spectrum.edge == edge
                    and spectrum.spectrum_type == spectrum_type
                ]

                if not is_missing_sites(relevant_spectra, element):
                    avg_spectrum = site_weighted_spectrum(
                        relevant_spectra, num_samples=self.sampling_density
                    )
                    averaged_spectra.append(avg_spectrum)

            spectra_docs = [spectra_to_doc(doc) for doc in averaged_spectra]

        except Exception as e:
            self.logger.error(traceback.format_exc())
            spectra_docs = [{"error": str(e), "state": "failed"}]

        last_updated = [
            self.source._lu_func[0](d[self.source.last_updated_field]) for d in items
        ]

        for d in spectra_docs:
            d.update(
                {
                    self.target.key: items[0]["mp_id"],
                    f"{self.source.key}s": keys,
                    self.target.last_updated_field: max(last_updated),
                    "_bt": datetime.utcnow(),
                }
            )

        return spectra_docs

    def update_targets(self, items):
        """
        Group buidler isn't deisgned for many-to-many so we unwrap that here
        """
        items = list(chain.from_iterable(items))
        if len(items) > 0:
            print(items)
            self.target.update(
                items, key=["task_id", "edge", "absorbing_element", "spectrum_type"]
            )

    def unary_function(self):
        pass


def is_missing_sites(spectra, element):
    """
    Determines if the collection of spectra are missing any indicies for the given element
    """
    structure = spectra[0].structure

    # Find missing symmeterically inequivalent sites
    symm_sites = SymmSites(structure)
    absorption_indicies = {spectrum.absorbing_atom for spectrum in spectra}

    missing_site_spectra_indicies = (
        set(structure.indices_from_symbol(element)) - absorption_indicies
    )
    for site_index in absorption_indicies:
        missing_site_spectra_indicies -= set(
            symm_sites.get_equivalent_site_indices(site_index)
        )

    return len(missing_site_spectra_indicies) != 0


class SymmSites:
    """
    Wrapper to get equivalent site indicies from SpacegroupAnalyzer
    """

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


def feff_task_to_spectrum(doc):
    energy = py_.pluck(doc["spectrum"], 0)  # (eV)
    intensity = py_.pluck(doc["spectrum"], 3)  # (mu)
    structure = Structure.from_dict(doc["structure"])
    absorbing_element = structure[doc["absorbing_atom"]].specie
    edge = doc["edge"]
    spectrum_type = doc["spectrum_type"]

    spectrum = XAS(
        x=energy,
        y=intensity,
        structure=structure,
        absorbing_element=absorbing_element,
        edge=edge,
        spectrum_type=spectrum_type,
    )
    # Adding a attr is not a robust process
    # Figure out better solution later
    spectrum.absorbing_atom = doc["absorbing_atom"]
    spectrum.last_updated = doc["last_updated"]
    return spectrum


def site_weighted_spectrum(spectra, num_samples=200):
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
    structure = spectra[0].structure
    symm_sites = SymmSites(structure)

    spectra = [spectrum for spectrum in spectra if len(spectrum.energy) > 0]

    for spectrum in spectra:
        # Checking the multiplicities of sites
        structure = spectrum.structure
        absorbing_atom = spectrum.absorbing_atom
        multiplicity = len(symm_sites.get_equivalent_site_indices(absorbing_atom))
        multiplicities.append(multiplicity)

        # Getting axis limits for each spectrum for the sites corresponding to
        # K-edge is a bit tricky, because the x-axis data points don't align
        # among different spectra for the same structure. So, prepare for
        # interpolation within the intersection of x-axis ranges.
        mins.append(spectrum.energy[0])
        maxes.append(spectrum.energy[-1])

        # 3rd-order spline interpolation
        f = interp1d(
            spectrum.energy,
            spectrum.intensity,
            kind="cubic",
            bounds_error=False,
            fill_value=0,
        )
        fs.append(f)

    energy = np.linspace(max(mins), min(maxes), num=num_samples)
    weighted_intensity = np.zeros(num_samples)
    total_multiplicity = sum(multiplicities)
    for i in range(len(multiplicities)):
        weighted_intensity += (multiplicities[i] * fs[i](energy)) / total_multiplicity

    return XAS(
        x=energy,
        y=weighted_intensity,
        structure=structure,
        absorbing_element=spectra[0].absorbing_element,
        edge=spectra[0].edge,
        spectrum_type=spectra[0].spectrum_type,
    )


def spectra_to_doc(spectrum):
    """
    Helper to conver the spectraum to a document with meta
    information
    """
    structure = spectrum.structure

    doc = structure_metadata(structure)
    doc.update(
        {
            "spectrum": jsanitize(spectrum.as_dict()),
            "edge": spectrum.edge,
            "absorbing_element": spectrum.absorbing_element,
            "spectrum_type": spectrum.spectrum_type,
        }
    )
    return doc
