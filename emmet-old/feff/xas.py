from maggma.core import Store
from maggma.builders import GroupBuilder
from typing import List, Dict, Tuple


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

        xas_ids = list(d[self.source.key] for d in items)
        self.logger.debug("Processing: {}".format(xas_ids))

        docs_spectra = [
            feff_task_to_spectrum(task) for task in items if len(task["spectrum"]) > 0
        ]
        for d in docs_spectra:
            d.last_updated = self.source._lu_func[0](d.last_updated)
        merged_spectra = merge_spectra(
            docs_spectra, sampling_density=self.sampling_density
        )
        all_spectra = docs_spectra + merged_spectra

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

            try:
                if not is_missing_sites(relevant_spectra, element):
                    avg_spectrum = site_weighted_averaged_spectrum(
                        relevant_spectra, sampling_density=self.sampling_density
                    )

                    averaged_spectra.append(avg_spectrum)
            except Exception:
                # So many errors cause this
                # Structures don't match even tho same MPID in DB
                # Weird Spectra
                # Missing fields
                # Empty spectra
                pass

        spectra_docs = [spectra_to_doc(doc) for doc in averaged_spectra]

        for d in spectra_docs:
            xas_ids = d["xas_ids"]
            del d["xas_ids"]

            t_id = items[0]["mp_id"]
            typ = d["spectrum_type"]
            edge = d["edge"]
            el = d["absorbing_element"]

            d.update(
                {
                    # TODO: Get this by matching to materials in the future
                    self.target.key: f"{t_id}-{typ}-{el}-{edge}",
                    "task_id": items[0]["mp_id"],
                    f"{self.source.key}s": xas_ids,
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
            self.target.update(
                items, key=["task_id", "edge", "absorbing_element", "spectrum_type"]
            )

    def unary_function(self):
        pass


def is_missing_sites(spectra, element):
    """
    Determines if the collection of spectra are missing any indicies for the given element
    """

    if len(spectra) > 0:

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
    else:
        return True


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


def merge_spectra(spectra: List[XAS], sampling_density: float = 4):
    """
    Converts the given FEFF Task Docs into the releveant XAS Spectra

    Args:
        docs: list of FEFF Task Docs
        sampling_density: the number of samples per unit eV to the sample the stitched spectrum
    """

    merged_spectra = []

    # Dictionary of all site to spectra mapping
    sites_to_spectra = {
        index: list(group)
        for index, group in groupby(
            sorted(spectra, key=lambda x: x.absorbing_atom),
            key=lambda x: x.absorbing_atom,
        )
    }

    # perform spectra merging
    for site, spectra in sites_to_spectra.items():
        type_to_spectra = {
            index: list(group)
            for index, group in groupby(
                sorted(
                    spectra, key=lambda x: (x.edge, x.spectrum_type, x.last_updated)
                ),
                key=lambda x: (x.edge, x.spectrum_type),
            )
        }
        # Make K-Total
        if ("K", "XANES") in type_to_spectra and ("K", "EXAFS") in type_to_spectra:
            try:
                xanes = type_to_spectra[("K", "XANES")][-1]
                exafs = type_to_spectra[("K", "EXAFS")][-1]
                num_samples = int(
                    (np.max(exafs.x) - np.min(xanes.x[0])) / sampling_density
                )
                total_spectrum = xanes.stitch(
                    exafs, mode="XAFS", num_samples=num_samples
                )

                total_spectrum.absorbing_atom = site
                total_spectrum.last_updated = max(
                    [xanes.last_updated, exafs.last_updated]
                )
                total_spectrum.xas_ids = xanes.xas_ids + exafs.xas_ids
                merged_spectra.append(total_spectrum)
            except Exception:
                pass

        # Make L23
        if ("L2", "XANES") in type_to_spectra and ("L3", "XANES") in type_to_spectra:
            try:
                l2 = type_to_spectra[("L2", "XANES")][-1]
                l3 = type_to_spectra[("L3", "XANES")][-1]
                num_samples = int((np.max(l3.x) - np.min(l2.x[0])) / sampling_density)
                total_spectrum = l2.stitch(l3, mode="L23", num_samples=num_samples)
                total_spectrum.absorbing_atom = site
                total_spectrum.last_updated = max([l2.last_updated, l3.last_updated])
                total_spectrum.xas_ids = l2.xas_ids + l3.xas_ids
                merged_spectra.append(total_spectrum)
            except Exception:
                pass

    return merged_spectra


def feff_task_to_spectrum(doc):
    energy = py_.pluck(doc["spectrum"], 0)  # (eV)
    intensity = py_.pluck(doc["spectrum"], 3)  # (mu)
    structure = Structure.from_dict(doc["structure"])
    absorbing_element = str(structure[doc["absorbing_atom"]].specie)
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
    spectrum.xas_ids = [doc["xas_id"]]
    return spectrum


def site_weighted_averaged_spectrum(spectra: List[XAS], sampling_density: float = 4):
    """
    Equivalent-site-weighted spectrum for a specie in a structure.
    Args:
        spectra: XAS spectra to average
        sampling_density:
        num_samples (int): Number of samples for interpolation.
            Original data has 100 data points.
    Returns:
        XAS: a site-weighted XAS Spectrum
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

    num_samples = int(np.abs(max(mins) - min(maxes)) / sampling_density)
    energy = np.linspace(max(mins), min(maxes), num=num_samples)
    weighted_intensity = np.zeros(num_samples)
    total_multiplicity = sum(multiplicities)
    for i in range(len(multiplicities)):
        weighted_intensity += (multiplicities[i] * fs[i](energy)) / total_multiplicity

    avg_spectrum = XAS(
        x=energy,
        y=weighted_intensity,
        structure=structure,
        absorbing_element=spectra[0].absorbing_element,
        edge=spectra[0].edge,
        spectrum_type=spectra[0].spectrum_type,
    )

    avg_spectrum.last_updated = max([s.last_updated for s in spectra])
    avg_spectrum.xas_ids = list(chain.from_iterable([s.xas_ids for s in spectra]))

    return avg_spectrum


def spectra_to_doc(spectrum):
    """
    Helper to conver the spectraum to a document with meta
    information
    """
    structure = spectrum.structure

    doc = structure_metadata(structure)

    doc.update(
        {
            "spectrum": spectrum.as_dict(),
            "edge": spectrum.edge,
            "absorbing_element": spectrum.absorbing_element,
            "spectrum_type": spectrum.spectrum_type,
        }
    )

    for k in ["xas_ids", "last_updated"]:
        if hasattr(spectrum, k):
            doc[k] = getattr(spectrum, k)
    return jsanitize(doc)
