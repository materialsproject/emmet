import warnings
from itertools import groupby
from typing import List

import numpy as np
from pydantic import Field
from pymatgen.analysis.xas.spectrum import XAS, site_weighted_spectrum
from pymatgen.core.periodic_table import Element
from pymatgen.symmetry.analyzer import SpacegroupAnalyzer

from emmet.core.feff.task import TaskDocument
from emmet.core.mpid import MPID
from emmet.core.spectrum import SpectrumDoc
from emmet.core.utils import ValueEnum


class Edge(ValueEnum):
    """
    The interaction edge for XAS
    There are 2n-1 sub-components to each edge where
    K: n=1
    L: n=2
    M: n=3
    N: n=4
    """

    K = "K"
    L2 = "L2"
    L3 = "L3"
    L2_3 = "L2,3"


class Type(ValueEnum):
    """
    The type of XAS Spectrum
    XANES - Just the near-edge region
    EXAFS - Just the extended region
    XAFS - Fully stitched XANES + EXAFS
    """

    XANES = "XANES"
    EXAFS = "EXAFS"
    XAFS = "XAFS"


class XASDoc(SpectrumDoc):
    """
    Document describing a XAS Spectrum.
    """

    spectrum_name = "XAS"

    spectrum: XAS

    task_ids: List[str] = Field(
        ...,
        title="Calculation IDs",
        description="List of Calculations IDs used to make this XAS spectrum.",
    )

    absorbing_element: Element = Field(..., description="Absoring element.")
    spectrum_type: Type = Field(..., description="XAS spectrum type.")
    edge: Edge = Field(
        ..., title="Absorption Edge", description="The interaction edge for XAS."
    )

    @classmethod
    def from_spectrum(
        cls,
        xas_spectrum: XAS,
        material_id: MPID,
        **kwargs,
    ):
        spectrum_type = xas_spectrum.spectrum_type
        el = xas_spectrum.absorbing_element
        edge = xas_spectrum.edge
        xas_id = f"{material_id}-{spectrum_type}-{el}-{edge}"

        if xas_spectrum.absorbing_index is not None:
            xas_id += f"-{xas_spectrum.absorbing_index}"

        return super().from_structure(
            meta_structure=xas_spectrum.structure,
            material_id=material_id,
            spectrum=xas_spectrum,
            edge=edge,
            spectrum_type=spectrum_type,
            absorbing_element=xas_spectrum.absorbing_element,
            spectrum_id=xas_id,
            **kwargs,
        )

    @classmethod
    def from_task_docs(
        cls, all_tasks: List[TaskDocument], material_id: MPID, num_samples: int = 200
    ) -> List["XASDoc"]:
        """
        Converts a set of FEFF Task Documents into XASDocs by merging XANES + EXAFS into XAFS spectra first
        and then merging along equivalent elements to get element averaged spectra

        Args:
            all_tasks: FEFF Task documents that have matching structure
            material_id: The material ID for the generated XASDocs
            num_samples: number of sampled points for site-weighted averaging
        """

        all_spectra: List[XAS] = []
        averaged_spectra: List[XAS] = []

        # This is a hack using extra attributes within this function to carry some extra information
        # without generating new objects
        for task in all_tasks:
            spectrum = task.xas_spectrum
            spectrum.last_updated = task.last_updated
            spectrum.task_ids = [task.task_id]
            all_spectra.append(spectrum)

        # Pre sort by keys to remove needing to sort in the group by stage
        all_spectra = sorted(
            all_spectra,
            key=lambda x: (
                x.absorbing_index,
                x.edge,
                x.spectrum_type,
                -1 * x.last_updated,
            ),
        )

        # Generate Merged Spectra
        # Dictionary of all site to spectra mapping
        sites_to_spectra = {
            index: list(group)
            for index, group in groupby(
                all_spectra,
                key=lambda x: x.absorbing_index,
            )
        }

        # perform spectra merging
        for site, spectra in sites_to_spectra.items():
            type_to_spectra = {
                index: list(group)
                for index, group in groupby(
                    spectra,
                    key=lambda x: (x.edge, x.spectrum_type),
                )
            }
            # Make K-edge XAFS spectra by merging XANES + EXAFS
            if ("K", "XANES") in type_to_spectra and ("K", "EXAFS") in type_to_spectra:
                xanes = type_to_spectra[("K", "XANES")][-1]
                exafs = type_to_spectra[("K", "EXAFS")][-1]
                try:
                    total_spectrum = xanes.stitch(exafs, mode="XAFS")
                    total_spectrum.absorbing_index = site
                    total_spectrum.task_ids = xanes.task_ids + exafs.task_ids
                    all_spectra.append(total_spectrum)
                except ValueError as e:
                    warnings.warn(f"Warning during spectral merging in XASDoC: {e}")

            # Make L2,3 XANES spectra by merging L2 and L3 spectra
            if ("L2", "XANES") in type_to_spectra and (
                "L3",
                "XANES",
            ) in type_to_spectra:
                l2 = type_to_spectra[("L2", "XANES")][-1]
                l3 = type_to_spectra[("L3", "XANES")][-1]
                try:
                    total_spectrum = l2.stitch(l3, mode="L23")
                    total_spectrum.absorbing_index = site
                    total_spectrum.task_ids = l2.task_ids + l3.task_ids
                    all_spectra.append(total_spectrum)
                except ValueError as e:
                    warnings.warn(f"Warning during spectral merging in XASDoC: {e}")

        # We don't have L2,3 EXAFS yet so don't have any merging

        # Site-weighted averaging
        spectra_to_average = [
            list(group)
            for _, group in groupby(
                sorted(
                    all_spectra,
                    key=lambda x: (x.absorbing_element, x.edge, x.spectrum_type),
                ),
                key=lambda x: (x.absorbing_element, x.edge, x.spectrum_type),
            )
        ]

        for relevant_spectra in spectra_to_average:
            if len(relevant_spectra) > 0 and not _is_missing_sites(relevant_spectra):
                if len(relevant_spectra) > 1:
                    try:
                        avg_spectrum = site_weighted_spectrum(
                            relevant_spectra, num_samples=num_samples
                        )
                        avg_spectrum.task_ids = [
                            id
                            for spectrum in relevant_spectra
                            for id in spectrum.task_ids
                        ]
                        avg_spectrum.last_updated = max(
                            [spectrum.last_updated for spectrum in relevant_spectra]
                        )
                        averaged_spectra.append(avg_spectrum)
                    except ValueError as e:
                        warnings.warn(
                            f"Warning during site-weighted averaging in XASDoC: {e}"
                        )
                else:
                    averaged_spectra.append(relevant_spectra[0])

        spectra_docs = []

        for spectrum in averaged_spectra:
            doc = XASDoc.from_spectrum(
                xas_spectrum=spectrum,
                material_id=material_id,
                task_ids=spectrum.task_ids,
                last_updated=spectrum.last_updated,
            )
            spectra_docs.append(doc)

        return spectra_docs


def _is_missing_sites(spectra: List[XAS]):
    """
    Determines if the collection of spectra are missing any indicies for the given element
    """
    structure = spectra[0].structure
    element = spectra[0].absorbing_element

    # Find missing symmeterically inequivalent sites
    symm_sites = SymmSites(structure)
    absorption_indicies = {spectrum.absorbing_index for spectrum in spectra}

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
