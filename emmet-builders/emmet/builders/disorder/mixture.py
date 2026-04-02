"""Composition-map utilities for disorder builders.

Vendored from phaseedge.schemas.mixture with imports adjusted.
"""

from typing import Any, Mapping, Sequence


def canonical_counts(counts: Mapping[str, Any]) -> dict[str, int]:
    """CE-style canonicalization: sort keys and cast values to int."""
    return {str(k): int(v) for k, v in sorted(counts.items())}


def canonical_comp_map(
    comp_map: Mapping[str, Mapping[str, int]],
) -> dict[str, dict[str, int]]:
    """Canonicalize a composition_map by sorting outer and inner keys."""
    return {str(ok): canonical_counts(inner) for ok, inner in sorted(comp_map.items())}


def sublattices_from_composition_maps(
    composition_maps: Sequence[dict[str, dict[str, int]]],
) -> dict[str, tuple[str, ...]]:
    """Extract the sublattice dictionary from a list of composition maps."""
    sublattices: dict[str, set[str]] = {}
    for composition_map in composition_maps:
        for site, comp in composition_map.items():
            if site not in sublattices:
                sublattices[site] = set()
            sublattices[site].update(comp.keys())
    return {site: tuple(sorted(elements)) for site, elements in sublattices.items()}
