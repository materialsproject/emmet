"""Caching and vectorized utilities for batch reverse-Pourbaix downloads.

This module contains three pieces:

1. ``ChemsysEntryCache`` — SQLite-backed cache of ``pbx_entries`` keyed by
   ``(chemsys, mp_db_version)``. Avoids re-hitting the network when the
   downloader is re-run with different (filter, conc) settings or after a
   crash. Build-time scratch space; safe to delete after the parquet is
   built.

2. ``CachedPourbaixDiagram`` — subclass of pymatgen's ``PourbaixDiagram``
   that accepts a pre-filtered, pre-conc-adjusted entry list and skips the
   expensive setup that's already been done at the chemsys level
   (deepcopy, solid filter, ion concentration override). The convex-hull /
   ``_preprocess_pourbaix_entries`` step still runs per ``comp_dict``
   because that's intrinsic to the algorithm — but everything cacheable
   above it is reused.

3. ``vectorized_decomposition_energies`` — single numpy operation using pymatgen's
   already-vectorized ``get_hull_energy``. Returns a 2-D array shaped
   ``(len(pH), len(V))``.

The chemsys-level helpers (``compute_filtered_solids``, ``apply_conc_dict``)
implement the precomputation pattern that lets a single ``pbx_entries``
download serve all filter_solids, ion_concentration combinations.
"""

from __future__ import annotations

import gzip
import json
import logging
import sqlite3
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
from monty.json import MontyDecoder
from pymatgen.analysis.phase_diagram import PhaseDiagram
from pymatgen.analysis.pourbaix_diagram import PourbaixDiagram, PourbaixEntry
from pymatgen.core.entries import ComputedEntry

if TYPE_CHECKING:
    from collections.abc import Iterable

logger = logging.getLogger(__name__)


class ChemsysEntryCache:
    """SQLite-backed cache of ``pbx_entries`` per chemsys.

    Keyed by ``(chemsys, db_version)``. Values are gzipped JSON of
    ``[entry.as_dict() for entry in pbx_entries]``.

    Concurrent access from multiple workers is handled by SQLite's locking;
    we set a large busy_timeout so writers wait rather than failing. WAL
    journaling lets reads proceed while a writer holds the lock.
    """

    SCHEMA = """
    CREATE TABLE IF NOT EXISTS pbx_entries (
        chemsys     TEXT NOT NULL,
        db_version  TEXT NOT NULL,
        blob        BLOB NOT NULL,
        n_entries   INTEGER NOT NULL,
        created_at  TEXT NOT NULL,
        PRIMARY KEY (chemsys, db_version)
    );
    """

    def __init__(self, path: str | Path, db_version: str):
        self.path = Path(path)
        self.db_version = db_version
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(self.SCHEMA)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")

    def _connect(self) -> sqlite3.Connection:
        # 60s busy timeout: under concurrent worker load, writers may queue
        # briefly. Network I/O dominates so this is rarely hit.
        conn = sqlite3.connect(str(self.path), timeout=60.0)
        return conn

    def get(self, chemsys: str) -> list[PourbaixEntry] | None:
        """Return cached ``pbx_entries`` for a chemsys, or None on miss."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT blob FROM pbx_entries WHERE chemsys = ? AND db_version = ?",
                (self._canonical(chemsys), self.db_version),
            ).fetchone()
        if row is None:
            return None
        try:
            payload = json.loads(gzip.decompress(row[0]).decode("utf-8"))
            decoder = MontyDecoder()
            return [decoder.process_decoded(d) for d in payload]
        except Exception:
            logger.exception("Failed to decode cached entries for cs=%s", chemsys)
            return None

    def put(self, chemsys: str, entries: list[PourbaixEntry]) -> None:
        """Store ``pbx_entries`` for a chemsys."""
        payload = [e.as_dict() for e in entries]
        blob = gzip.compress(json.dumps(payload).encode("utf-8"), compresslevel=3)
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO pbx_entries "
                "(chemsys, db_version, blob, n_entries, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    self._canonical(chemsys),
                    self.db_version,
                    blob,
                    len(entries),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            conn.commit()

    @staticmethod
    def _canonical(chemsys: str) -> str:
        """Canonicalize a chemsys string to a sorted, dash-joined form."""
        return "-".join(sorted(chemsys.split("-")))


# Sentinel oxygen energy used by pymatgen's solid filter: O is 2.46 eV because
# pbx entries are referenced to H2O. Lifted directly from pymatgen so our
# filter produces identical results to the upstream path.
_PBX_ENTRY_H_REF = ComputedEntry("H", 0)
_PBX_ENTRY_O_REF = ComputedEntry("O", 2.46)


def compute_filtered_solids(
    pbx_entries: list[PourbaixEntry],
    filter_solids: bool,
) -> list[PourbaixEntry]:
    """Apply (or skip) the compositional-phase-diagram solid filter.

    When ``filter_solids=True``, replicates exactly what
    ``PourbaixDiagram.__init__`` does: builds a ``PhaseDiagram`` of all
    solid entries plus the H/O references, keeps only the stable ones,
    drops the H/O sentinels, then re-attaches the ion entries unchanged.

    When ``filter_solids=False``, returns the entries split-and-rejoined
    (no-op for correctness, but ensures the returned object has the same
    ordering invariant as the filtered branch).

    This step depends only on ``pbx_entries`` and ``filter_solids``, not on
    ``comp_dict`` or ``conc_dict``, so it can be computed once per
    ``(chemsys, filter_solids)`` pair.
    """
    solid_entries = [e for e in pbx_entries if e.phase_type == "Solid"]
    ion_entries = [e for e in pbx_entries if e.phase_type == "Ion"]

    if filter_solids:
        ho_sentinels = [_PBX_ENTRY_H_REF, _PBX_ENTRY_O_REF]
        solid_pd = PhaseDiagram(solid_entries + ho_sentinels)
        solid_entries = list(set(solid_pd.stable_entries) - set(ho_sentinels))

    return solid_entries + ion_entries


def apply_conc_dict(
    filtered_entries: list[PourbaixEntry],
    conc_dict: dict[str, float],
) -> list[PourbaixEntry]:
    """Return a copy of ``filtered_entries`` with ion concentrations set.

    pymatgen mutates ion entries in place when it applies a conc_dict, so
    we deepcopy the ions to keep the input list reusable across multiple
    conc settings. Solid entries are passed through unchanged — they're
    never mutated downstream and are far more expensive to deepcopy.

    The concentration math mirrors ``PourbaixDiagram.__init__``:
    single-element ions get ``conc_dict[symbol] * normalization_factor``;
    multi-element ions are required to have a pre-set concentration.
    """
    out: list[PourbaixEntry] = []
    ho_symbols = {"H", "O"}
    for entry in filtered_entries:
        if entry.phase_type == "Ion":
            ion = deepcopy(entry)
            ion_elts = [el.symbol for el in ion.elements if el.symbol not in ho_symbols]
            if len(ion_elts) == 1:
                ion.concentration = (
                    conc_dict[ion_elts[0]] * ion.normalization_factor
                )
            elif len(ion_elts) > 1 and not ion.concentration:
                raise ValueError(
                    "Elemental concentration not compatible with multi-element ion: "
                    f"{ion}"
                )
            out.append(ion)
        else:
            out.append(entry)
    return out


class CachedPourbaixDiagram(PourbaixDiagram):
    """``PourbaixDiagram`` subclass that accepts pre-processed entries.

    The upstream ``__init__`` does three expensive things before the
    per-comp-dict work begins:

      1. ``deepcopy(entries)``
      2. Apply ``filter_solids`` via a fresh ``PhaseDiagram`` build
      3. Apply ``conc_dict`` by mutating ion entries in place

    All three depend only on ``(chemsys, filter_solids, conc_dict)``, NOT
    on ``comp_dict``. For batch downloads we precompute them at the
    chemsys level and feed the result here, avoiding 100s of pointless
    repetitions per chemsys.

    The caller is responsible for not mutating ``ready_entries`` after
    construction. ``apply_conc_dict`` already deepcopies the ion entries,
    so this is safe in our pipeline.
    """

    def __init__(
        self,
        ready_entries: list[PourbaixEntry],
        comp_dict: dict[str, float],
        filter_solids: bool,
        conc_dict: dict[str, float] | None = None,
        nproc: int | None = None,
    ) -> None:
        """
        Args:
            ready_entries: entries already filtered (per ``filter_solids``)
                and already adjusted (per ``conc_dict``). Will not be
                deepcopied or mutated.
            comp_dict: non-H/O elemental composition (caller strips H/O).
            filter_solids: stored for round-tripping via ``as_dict`` only;
                the filtering has already been applied to ``ready_entries``.
            conc_dict: stored for round-tripping; concentrations already
                applied to ``ready_entries``.
            nproc: passed through to ``_preprocess_pourbaix_entries``.
        """
        # Mirror the bits of PourbaixDiagram.__init__ we still need, but
        # without the deepcopy or the filter/conc work.
        import itertools  # local to avoid polluting module namespace

        self.filter_solids = filter_solids

        # pbx_elts: non-H/O elements present in the entries.
        self.pbx_elts = list(
            set(
                itertools.chain.from_iterable(
                    entry.composition.elements for entry in ready_entries
                )
            )
            - self.elements_ho
        )
        self.dim = len(self.pbx_elts) - 1

        if not comp_dict:
            raise ValueError("comp_dict is required for CachedPourbaixDiagram")

        ho_symbols = {elt.symbol for elt in self.elements_ho}
        filtered_comp_dict = {
            k: v for k, v in comp_dict.items() if k not in ho_symbols
        }
        if not filtered_comp_dict:
            raise ValueError(
                "comp_dict must contain at least one non-H/O element; "
                "H and O are open species in the Pourbaix formalism."
            )

        self._elt_comp = filtered_comp_dict
        self._conc_dict = conc_dict
        self.pourbaix_elements = self.pbx_elts

        self._unprocessed_entries = ready_entries
        self._filtered_entries = ready_entries

        if len(self._elt_comp) > 1:
            self._multi_element = True
            self._processed_entries = self._preprocess_pourbaix_entries(
                self._filtered_entries, nproc=nproc
            )
        else:
            self._multi_element = False
            self._processed_entries = self._filtered_entries

        self._stable_domains, self._stable_domain_vertices = (
            self.get_pourbaix_domains(self._processed_entries)
        )


def vectorized_decomposition_energies(
    pbx: PourbaixDiagram,
    entry: PourbaixEntry,
    ph_values: np.ndarray,
    v_values: np.ndarray,
) -> np.ndarray:
    """Compute decomposition energies on a (pH, V) grid in one numpy op.

    Pymatgen's ``get_hull_energy`` and ``normalized_energy_at_conditions``
    both already accept array inputs — we just need to feed them a
    meshgrid instead of looping. For a 15×9 grid this collapses 135 Python
    calls into ~3 numpy ops.

    The composition consistency check from pymatgen's
    ``get_decomposition_energy`` is replicated here so semantics are
    identical to the original method.

    Args:
        pbx: a ``PourbaixDiagram`` (or subclass) already constructed for
            the material's comp_dict.
        entry: the ``PourbaixEntry`` to evaluate (the material's own
            entry from the chemsys ``pbx_entries`` list).
        ph_values: 1-D array of pH values.
        v_values: 1-D array of V values.

    Returns:
        2-D array of shape ``(len(ph_values), len(v_values))`` of
        decomposition energies in eV/atom. Index ordering matches
        ``itertools.product(ph_values, v_values)`` flattened row-major.
    """
    from pymatgen.core import Composition

    # Composition consistency check (lifted verbatim from pymatgen).
    pbx_comp = Composition(pbx._elt_comp).fractional_composition
    entry_pbx_comp = Composition(
        {
            elt: coeff
            for elt, coeff in entry.composition.items()
            if elt not in pbx.elements_ho
        }
    ).fractional_composition
    if entry_pbx_comp != pbx_comp:
        raise ValueError("Composition of stability entry does not match Pourbaix Diagram")

    # Meshgrid with indexing='ij' so axis 0 is pH and axis 1 is V.
    ph_grid, v_grid = np.meshgrid(ph_values, v_values, indexing="ij")

    entry_g = entry.normalized_energy_at_conditions(ph_grid, v_grid)
    hull_g = pbx.get_hull_energy(ph_grid, v_grid)

    decomp = entry_g - hull_g
    # eV/normalized-formula-unit -> eV/atom
    decomp = decomp / entry.normalization_factor / entry.composition.num_atoms
    return decomp


def iter_filter_conc_combos(
    filter_solids_options: Iterable[bool],
    conc_options: Iterable[float],
):
    """Yield ``(filter_solids, ion_concentration)`` pairs for one chemsys.

    Outer loop is ``filter_solids`` so the (expensive) filtered-solids
    list is computed twice per chemsys; inner loop is ``conc`` so the
    (cheap) ion-concentration deepcopy is done for each conc.
    """
    for fs in filter_solids_options:
        for conc in conc_options:
            yield fs, conc