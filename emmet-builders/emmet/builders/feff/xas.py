from typing import List, Dict
from itertools import groupby, chain
from datetime import datetime
import traceback

import numpy as np
from monty.json import jsanitize

from maggma.core import Store
from maggma.builders import GroupBuilder

from pymatgen.core import Structure
from pymatgen.analysis.xas.spectrum import XAS, site_weighted_spectrum
from pymatgen.symmetry.analyzer import SpacegroupAnalyzer
from emmet.core.xas import XASDoc
from emmet.builders.utils import maximal_spanning_non_intersecting_subsets


class XASBuilder(GroupBuilder):
    """
    Generates XAS Docs from FEFF tasks

    # TODO: Generate MPID from materials collection rather than from task metadata
    """

    def __init__(self, tasks: Store, xas: Store, num_samples: int = 200.0, **kwargs):
        self.tasks = tasks
        self.xas = xas
        self.num_samples = 200
        self.kwargs = kwargs

        super().__init__(source=tasks, target=xas, grouping_keys=["mp_id"])
        self._target_keys_field = "xas_ids"

    def process_item(self, spectra: List[Dict]) -> Dict:

        mpid = spectra[0]["mp_id"]
        sandboxes = [doc.get("sandboxes", []) for doc in spectra]
        sbxn_sets = maximal_spanning_non_intersecting_subsets(sandboxes)

        self.logger.debug(f"Processing: {mpid}")
        all_processed = []

        for sbxns in sbxn_sets:
            sbxn_spectra = [
                doc
                for doc in spectra
                if doc.get("sandboxes", []) == list(sbxns)
                or doc.get("sandboxes", []) == []
            ]

            try:

                processed = self.process_spectra(sbxn_spectra)
                for d in processed:
                    d.update({"state": "successful"})

                all_processed.extend(processed)
            except Exception as e:
                self.logger.error(traceback.format_exc())
                all_processed.append(
                    {
                        "error": str(e),
                        "state": "failed",
                        "task_ids": list(d[self.xas.key] for d in sbxn_spectra),
                    }
                )

        update_doc = {
            "_bt": datetime.utcnow(),
        }
        all_processed.update(
            {k: v for k, v in update_doc.items() if k not in processed}
        )

        return all_processed

    def process_spectra(self, items: List[Dict]) -> Dict:

        all_spectra = [feff_task_to_spectrum(task) for task in items]

        # Dictionary of all site to spectra mapping
        sites_to_spectra = {
            index: list(group)
            for index, group in groupby(
                sorted(all_spectra, key=lambda x: x.absorbing_index),
                key=lambda x: x.absorbing_index,
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
                xanes = type_to_spectra[("K", "XANES")][-1]
                exafs = type_to_spectra[("K", "EXAFS")][-1]
                try:
                    total_spectrum = xanes.stitch(exafs, mode="XAFS")
                    total_spectrum.absorbing_index = site
                    total_spectrum.task_ids = xanes.task_ids + exafs.task_ids
                    all_spectra.append(total_spectrum)
                except ValueError as e:
                    self.logger.warning(e)

            # Make L23
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
                    self.logger.warning(e)

        self.logger.debug(f"Found {len(all_spectra)} spectra")

        # Site-weighted averaging
        spectra_to_average = [
            list(group)
            for _, group in groupby(
                sorted(
                    all_spectra,
                    key=lambda x: (x.absorbing_element, x.edge, x.spectrum_type),
                ),
                key=lambda x: lambda x: (x.absorbing_element, x.edge, x.spectrum_type),
            )
        ]
        averaged_spectra = []

        for relevant_spectra in spectra_to_average:

            if len(relevant_spectra) > 0 and not is_missing_sites(relevant_spectra):
                if len(relevant_spectra) > 1:
                    try:
                        avg_spectrum = site_weighted_spectrum(
                            relevant_spectra, num_samples=self.num_samples
                        )
                        avg_spectrum.task_ids = [
                            id
                            for spectrum in relevant_spectra
                            for id in spectrum.task_ids
                        ]
                        averaged_spectra.append(avg_spectrum)
                    except ValueError as e:
                        self.logger.error(e)
                else:
                    averaged_spectra.append(relevant_spectra[0])

        spectra_docs = [
            XASDoc.from_spectrum(spectrum).dict() for spectrum in averaged_spectra
        ]

        return spectra_docs

    def update_targets(self, items):
        """
        Group buidler isn't designed for many-to-many so we unwrap that here
        """

        items = list(filter(None.__ne__, chain.from_iterable(items)))
        super().update_targets(items)


def is_missing_sites(spectra):
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


def feff_task_to_spectrum(doc):
    energy = doc["spectrum"][0]  # (eV)
    intensity = doc["spectrum"][3]  # (mu)
    structure: Structure = Structure.from_dict(doc["structure"])
    # Clean site properties
    for site_prop in structure.site_properties.keys():
        structure.remove_site_property(site_prop)

    absorbing_index = doc["absorbing_atom"]
    absorbing_element = structure[absorbing_index].specie
    edge = doc["edge"]
    spectrum_type = doc["spectrum_type"]

    spectrum = XAS(
        x=energy,
        y=intensity,
        structure=structure,
        absorbing_element=absorbing_element,
        absorbing_index=absorbing_index,
        edge=edge,
        spectrum_type=spectrum_type,
    )
    # Adding a attr is not a robust process
    # Figure out better solution later
    spectrum.last_updated = doc["last_updated"]
    spectrum.task_ids = [doc["xas_id"]]
    return spectrum
