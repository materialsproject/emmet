"""Random configuration generators for disordered supercells.

Vendored from phaseedge.science.random_configs with imports adjusted.
"""

from typing import Mapping

import numpy as np
from ase.atoms import Atoms
from pymatgen.core import Structure
from pymatgen.io.ase import AseAtomsAdaptor


def validate_counts_for_sublattices(
    *,
    primitive_cell: Atoms,
    supercell_diag: tuple[int, int, int],
    composition_map: Mapping[str, Mapping[str, int]],
) -> None:
    """Validate that integer counts sum to sublattice sizes in the supercell."""
    sc = primitive_cell.repeat(supercell_diag)
    symbols = np.array(sc.get_chemical_symbols())

    for replace_element, counts in composition_map.items():
        target_idx = np.where(symbols == replace_element)[0]
        n_sites = int(target_idx.size)

        if any(int(v) < 0 for v in counts.values()):
            raise ValueError(f"Negative count in counts for {replace_element}: {counts}")

        total = sum(int(v) for v in counts.values())
        if total != n_sites:
            raise ValueError(
                f"[{replace_element}] counts must sum to sublattice size: "
                f"got {total}, expected {n_sites} \n {composition_map}"
            )


def make_one_snapshot(
    *,
    primitive_cell: Atoms,
    supercell_diag: tuple[int, int, int],
    composition_map: Mapping[str, Mapping[str, int]],
    rng: np.random.Generator,
) -> Structure:
    """Build a supercell with exact integer counts assigned by permuting sublattice indices."""
    validate_counts_for_sublattices(
        primitive_cell=primitive_cell,
        supercell_diag=supercell_diag,
        composition_map=composition_map,
    )

    sc = primitive_cell.repeat(supercell_diag)
    symbols = np.array(sc.get_chemical_symbols())

    for replace_element, counts in sorted(composition_map.items()):
        target_idx = np.where(symbols == replace_element)[0]
        n_sites = int(target_idx.size)

        perm = rng.permutation(n_sites)

        start = 0
        for elem, n in sorted(counts.items()):
            n_int = int(n)
            if n_int <= 0:
                raise ValueError(f"Zero or negative count for {elem}: {n_int}")

            idx_slice = target_idx[perm[start : start + n_int]]
            symbols[idx_slice] = elem
            start += n_int

        if start != n_sites:
            raise RuntimeError(
                f"[{replace_element}] count slices consumed {start} out of {n_sites} sites."
            )

    sc.set_chemical_symbols(symbols.tolist())
    structure = AseAtomsAdaptor.get_structure(sc)
    return structure
