from __future__ import annotations

import warnings
from itertools import groupby
from functools import cached_property
from typing import TYPE_CHECKING, overload

import numpy as np
from pydantic import Field
from emmet.core.io.pymatgen import (
    XAS,
    site_weighted_spectrum,
    Element,
    SpacegroupAnalyzer,
)

from emmet.core.feff.task import TaskDocument
from emmet.core.spectrum import SpectrumDoc
from emmet.core.types.enums import ValueEnum, XasEdge, XasType
from emmet.core.types.pymatgen_types.element_adapter import ElementType
from emmet.core.types.pymatgen_types.xas_adapter import XASType
from emmet.core.mpid import AlphaID
from emmet.core.types.typing import (
    ID_PADLEN,
    IdentifierType,
    validate_compound_identifier,
)

if TYPE_CHECKING:
    from typing import Any, Literal
    from emmet.core.types.typing import CompoundIDType

Type = ValueEnum("Type", [(e.name, e.value) for e in XasType])  # type: ignore[call-arg]
"""Type is deprecated and will be removed - migrate to XasType."""

Edge = ValueEnum("Edge", [(e.name, e.value) for e in XasEdge])  # type: ignore[call-arg]
"""Edge is deprecated and will be removed - migrate to XasEdge."""


@overload
def validate_xas_spectrum_id(
    idx: str, as_components: Literal[True] = True
) -> CompoundIDType: ...


@overload
def validate_xas_spectrum_id(
    idx: str, as_components: Literal[False] = False
) -> str: ...


def validate_xas_spectrum_id(
    idx: str, as_components: bool = False
) -> str | CompoundIDType:
    """Validate an XAS spectrum identifier."""
    return validate_compound_identifier(
        idx,
        suffixes=(XasType, Element, XasEdge),
        separator="-",
        use_prefix=False,
        as_components=as_components,
    )


def format_spectrum_id(
    spectrum_id: "Any",
    legacy: bool,
    prefix: str = "mp",
    padlen: int = ID_PADLEN,
) -> str | None:
    """Render an XAS spectrum id in either legacy or new alpha form.

    Spectrum ids are composite identifiers built at runtime from a task id
    plus three typed suffix components (spectrum type, absorbing element,
    edge), all joined with ``-``. Their shape convention follows the same
    prefix-dropping rule as task ids — the leading id portion is prefixed
    in legacy form and bare in alpha form:

    - Legacy form: ``mp-<int>-<XasType>-<Element>-<XasEdge>``
      (e.g. ``mp-779827-XANES-O-K``).
    - New alpha form: ``<padded-alpha>-<XasType>-<Element>-<XasEdge>``
      (e.g. ``aaabsjpj-XANES-O-K``) with **no** ``mp-`` prefix.

    Parsing delegates to :func:`validate_xas_spectrum_id` (and through it
    to :func:`validate_compound_identifier`), so the suffix shape stays in
    lockstep with the canonical XAS spectrum_id schema.

    Args:
        spectrum_id: A spectrum id in either form. May be the bare composite
            string, or anything :func:`validate_xas_spectrum_id` accepts.
        legacy: If True, returns the legacy ``mp-<int>-...`` form. If False,
            returns the bare-alpha-prefixed ``<padded-alpha>-...`` form.
        prefix: The id prefix used in the legacy form. Defaults to ``"mp"``.
        padlen: The minimum identifier length on the alpha-form output.
            Defaults to 8.

    Returns:
        The formatted string. If ``spectrum_id`` is None or empty, it is
        returned unchanged. If parsing fails, the input is coerced to a
        string and returned unchanged (defensive: this helper never raises
        from a display path).

    Examples:
        >>> format_spectrum_id("mp-779827-XANES-O-K", legacy=False)
        'aaabsjpj-XANES-O-K'
        >>> format_spectrum_id("aaabsjpj-XANES-O-K", legacy=True)
        'mp-779827-XANES-O-K'
    """
    # Two-step guard avoids triggering ``MPID.__eq__`` (which raises
    # ValueError on ``MPID(...) == ""``) when ``spectrum_id`` is an
    # MPID/AlphaID subclass instance rather than a plain string.
    if spectrum_id is None:
        return spectrum_id
    if isinstance(spectrum_id, str) and not spectrum_id:
        return spectrum_id

    try:
        components = validate_xas_spectrum_id(str(spectrum_id), as_components=True)
    except (ValueError, TypeError, IndexError):
        return str(spectrum_id)

    identifier = components["identifier"]
    suffix = components["suffix"]
    separator = components["separator"]

    suffix_str = separator.join(s.value for s in suffix)
    if legacy:
        base = f"{prefix}-{int(identifier)}"
    else:
        # Alpha display: bare padded identifier with no prefix, matching
        # the convention `validate_xas_spectrum_id(..., use_prefix=False)`
        # uses when emitting the canonical alpha form server-side.
        base = str(AlphaID(int(identifier), padlen=padlen, prefix=None))
    return f"{base}{separator}{suffix_str}"


class XASDoc(SpectrumDoc):
    """
    Document describing a XAS Spectrum.
    """

    spectrum_name: str = "XAS"
    spectrum: XASType | None = Field(
        None, description="The XAS spectrum for this calculation."
    )
    absorbing_element: ElementType = Field(..., description="Absoring element.")
    spectrum_type: XasType = Field(..., description="XAS spectrum type.")
    edge: XasEdge = Field(
        ..., title="Absorption Edge", description="The interaction edge for XAS."
    )

    @cached_property
    def spectrum_id(self) -> str:
        """Return legacy-style spectrum_id in AlphaID format."""
        if not self.task_id:
            raise ValueError("Cannot determine `spectrum_id` without a `task_id`.")
        return validate_xas_spectrum_id(
            "-".join(
                [
                    self.task_id.string,
                    self.spectrum_type.value,
                    self.absorbing_element.value,
                    self.edge.value,
                ]
            ),
            as_components=False,
        )

    @classmethod
    def from_spectrum(
        cls,
        xas_spectrum: XAS,
        material_id: IdentifierType | None = None,
        **kwargs,
    ):
        spectrum_type = XasType(xas_spectrum.spectrum_type)
        edge = XasEdge(xas_spectrum.edge)

        return super().from_structure(
            meta_structure=xas_spectrum.structure,
            material_id=material_id,
            spectrum=xas_spectrum,
            edge=edge,
            spectrum_type=spectrum_type,
            absorbing_element=xas_spectrum.absorbing_element,
            **kwargs,
        )

    @classmethod
    def from_task_docs(
        cls,
        all_tasks: list[TaskDocument],
        material_id: IdentifierType | None = None,
        num_samples: int = 200,
    ) -> list["XASDoc"]:
        """
        Converts a set of FEFF Task Documents into XASDocs by merging XANES + EXAFS into XAFS spectra first
        and then merging along equivalent elements to get element averaged spectra

        Args:
            all_tasks: FEFF Task documents that have matching structure
            material_id: The material ID for the generated XASDocs
            num_samples: number of sampled points for site-weighted averaging
        """

        all_spectra: list[XAS] = []
        averaged_spectra: list[XAS] = []

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
                    total_spectrum.task_ids = xanes.task_ids + exafs.task_ids  # type: ignore[attr-defined]
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
                    total_spectrum.task_ids = l2.task_ids + l3.task_ids  # type: ignore[attr-defined]
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
                        avg_spectrum.task_ids = [  # type: ignore[attr-defined]
                            id
                            for spectrum in relevant_spectra
                            for id in spectrum.task_ids
                        ]
                        avg_spectrum.last_updated = max(  # type: ignore[attr-defined, type-var]
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


def _is_missing_sites(spectra: list[XAS]):
    """
    Determines if the collection of spectra are missing any indicies for the given element
    """
    structure = spectra[0].structure
    element = spectra[0].absorbing_element.symbol

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
