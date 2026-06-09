"""Reverse-Pourbaix downloader (refactored).

Pulls Pourbaix decomposition energies from the Materials Project for every
material on a (pH, V) grid, at the pymatgen defaults
(``filter_solids=True``, ``ion_concentration=1e-6``).

A full sweep over ``(filter_solids, ion_concentration)`` is
deliberately not run her. App already supports the ability to inspect
individual materials using the old Pourbaix diagram app. 

However, if deemed needed in future, restore the
multi-valued tuples in ``schema.py`` and put the two inner loops back
around the ``CachedPourbaixDiagram`` construction in ``process_chemsys``.
The chemsys-level helpers (``compute_filtered_solids``, ``apply_conc_dict``)
and ``CachedPourbaixDiagram`` are unchanged and already designed for that
sweep — only the orchestrator currently calls them once.

Restart a timed-out / crashed run (same MP data):
    rm -rf pbx_cache/parquet_dataset/        # avoid duplicate rows
    # KEEP sqlite + summary_docs -> cached chemsystems skip the network and
    # the restart resumes fast.
    # (optionally bump num_procs / slurm --cpus-per-task / --mem first)

New materials added to MP (new DB release) — update the parquet:
    rm -f  pbx_cache/summary_docs.jsonl.gz   # REQUIRED: re-fetch the catalog,
                                             # else new materials are invisible
    rm -rf pbx_cache/parquet_dataset/        # avoid duplicate rows
    # sqlite can be KEPT (auto-invalidated by the new db version) or deleted
    # to reclaim space — either way the new run re-fetches every chemsys.

Fully clean run from scratch:
    rm -rf pbx_cache/                        # drop all caches

Always wipe parquet_dataset/ before any run; delete
summary_docs.jsonl.gz whenever the MP catalog may have changed; keep the
sqlite cache to make same-version restarts effectively free.

Final pos-processing function makes the files required for the web app.
"""

from __future__ import annotations

import gzip
import json
import logging
import multiprocessing as mp
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
from emmet.core.mpid import AlphaID
from mp_api.client import MPRester
from pydantic import BaseModel
from pymatgen.analysis.pourbaix_diagram import PourbaixDiagram
from pymatgen.core import Composition

from pourbaix_cache import (
    CachedPourbaixDiagram,
    ChemsysEntryCache,
    apply_conc_dict,
    compute_filtered_solids,
    vectorized_decomposition_energies,
)
from schema import (
    DEFAULT_FILTER_SOLIDS,
    DEFAULT_ION_CONCENTRATION,
    PARQUET_SCHEMA,
    PARTITION_COLS,
    PH_VALUES,
    SCHEMA_VERSION,
    V_VALUES,
)

if TYPE_CHECKING:
    from pymatgen.analysis.pourbaix_diagram import PourbaixEntry

logger = logging.getLogger(__name__)

MP_API_KEY = os.environ.get("MP_API_KEY", "YOUR_API_KEY_HERE")


class SummaryDocSubset(BaseModel):
    """Just the fields we need to drive the scan.

    Enrichment fields (band_gap, formation_energy, etc.) are processed later.
    """

    material_id: str
    chemsys: str | None = None
    formula_pretty: str | None = None

def get_mpr() -> MPRester:
    return MPRester(MP_API_KEY) if MP_API_KEY else MPRester()


def comp_dict_from_formula(formula: str | None) -> dict[str, float] | None:
    """Strip H and O from a composition. Returns None for pure-aqueous formulas.
       However, a fix for this was merged into pymatgen which already does this,
       so could be ommitted perhaps.
    """
    if not formula:
        return None
    comp = Composition(formula).as_dict()
    comp.pop("O", None)
    comp.pop("H", None)
    return comp or None


def mpid_from_entry_id(eid: str) -> str | None:
    """Extract the material id ('mp-N' or 'mvc-N') from a PourbaixEntry's entry_id.

    Pourbaix entry_ids look like 'mp-12345-GGA' or 'mp-12345-GGA+U'.
    Ion entries look like 'ion-0', 'ion-1', etc., and are excluded by this
    function (returns None for non-mp/mvc prefixes).
    """
    parts = eid.split("-", 2)
    if len(parts) >= 2 and parts[0] in ("mp", "mvc"):
        return AlphaID("-".join(parts[:2])).string
    return None


def _setup_worker_logger(log_dir: Path) -> logging.Logger:
    log_dir.mkdir(parents=True, exist_ok=True)
    worker_logger = logging.getLogger(f"pbx_{os.getpid()}")
    if worker_logger.handlers:
        return worker_logger
    worker_logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    fh = logging.FileHandler(log_dir / f"worker_{os.getpid()}.log")
    fh.setFormatter(fmt)
    worker_logger.addHandler(fh)
    return worker_logger


def _write_error(error_path: Path, payload: dict) -> None:
    with open(error_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(payload) + "\n")


def _fetch_pbx_entries(
    chemsys: str,
    elements_no_oh: list[str],
    cache: ChemsysEntryCache,
    mpr: MPRester | None,
    error_path: Path | None,
    worker_logger: logging.Logger,
) -> list[PourbaixEntry] | None:
    """Get pbx_entries for a chemsys, from cache or from the MP API.

    Returns None on hard error (writes to error_path). Successful empty
    fetches are stored in the cache as empty lists so we don't re-query
    chemsystems that legitimately have no Pourbaix data.
    """
    cached = cache.get(chemsys)
    if cached is not None:
        return cached

    if mpr is None:
        raise RuntimeError(
            "Cache miss for chemsys=%s but no MPRester provided" % chemsys
        )
    try:
        entries = mpr.get_pourbaix_entries(elements_no_oh)
    except Exception as exc:
        worker_logger.exception("get_pourbaix_entries failed cs=%s", chemsys)
        if error_path:
            _write_error(
                error_path,
                {
                    "chemsys": chemsys,
                    "stage": "get_pourbaix_entries",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
            )
        return None

    cache.put(chemsys, entries)
    return entries


def process_chemsys(
    docs: list[SummaryDocSubset],
    cache: ChemsysEntryCache,
    mpr: MPRester | None,
    error_path: Path | None,
    worker_logger: logging.Logger,
    max_elements: int = 0,
) -> list[dict]:
    """Process one chemsys: emit decomp-energy rows for all materials at defaults.

    Returned rows match the parquet schema:
        mp_id, filter_solids, ion_concentration, pH, V, decomposition_energy
    """
    cs = docs[0].chemsys
    if not cs:
        return []
    if max_elements and len(cs.split("-")) > max_elements:
        return []

    elements_no_oh = [el for el in cs.split("-") if el not in ("O", "H")]
    if not elements_no_oh:
        return []

    # Index docs by canonical mp-id for matching against PourbaixEntry.entry_id later.
    docs_by_mpid = {
        AlphaID(doc.material_id).string: doc.formula_pretty for doc in docs
    }

    pbx_entries = _fetch_pbx_entries(
        cs, elements_no_oh, cache, mpr, error_path, worker_logger
    )
    if pbx_entries is None:
        return []
    if not pbx_entries:
        worker_logger.info("cs=%s entries=0", cs)
        return []

    # Map pbx_entries back to mp-ids. Ion entries (entry_id starts with 'ion-')
    # are skipped by mpid_from_entry_id and don't appear here.
    pbx_entries_by_mpid: dict[str, PourbaixEntry] = {}
    for entry in pbx_entries:
        mpid = mpid_from_entry_id(entry.entry_id)
        if mpid:
            pbx_entries_by_mpid[mpid] = entry

    mpids_to_process = set(pbx_entries_by_mpid) & set(docs_by_mpid)
    if not mpids_to_process:
        worker_logger.info("cs=%s zero-intersection", cs)
        return []

    rows: list[dict] = []

    # Chemsys-level work: one solid filter, one conc.
    filter_solids = DEFAULT_FILTER_SOLIDS
    conc = DEFAULT_ION_CONCENTRATION

    try:
        filtered_entries = compute_filtered_solids(pbx_entries, filter_solids)
    except Exception as exc:
        worker_logger.exception(
            "compute_filtered_solids failed cs=%s filter_solids=%s", cs, filter_solids
        )
        if error_path:
            _write_error(
                error_path,
                {
                    "chemsys": cs,
                    "stage": "compute_filtered_solids",
                    "filter_solids": filter_solids,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
            )
        return []

    conc_dict = {el: conc for el in elements_no_oh}
    ready_entries = apply_conc_dict(filtered_entries, conc_dict)

    # Per-comp-dict diagram cache. Materials with the same metals-only
    # composition share the (still per-comp_dict-intrinsic) preprocess step.
    diagram_cache: dict[tuple, CachedPourbaixDiagram] = {}

    for mpid in mpids_to_process:
        formula = docs_by_mpid[mpid]
        comp_dict = comp_dict_from_formula(formula)
        if not comp_dict:
            continue

        comp_key = tuple(sorted(comp_dict.items()))
        if comp_key not in diagram_cache:
            try:
                diagram_cache[comp_key] = CachedPourbaixDiagram(
                    ready_entries=ready_entries,
                    comp_dict=comp_dict,
                    filter_solids=filter_solids,
                    conc_dict=conc_dict,
                )
            except Exception as exc:
                worker_logger.exception(
                    "CachedPourbaixDiagram failed cs=%s mpid=%s "
                    "filter_solids=%s conc=%s",
                    cs, mpid, filter_solids, conc,
                )
                if error_path:
                    _write_error(
                        error_path,
                        {
                            "chemsys": cs,
                            "material_id": mpid,
                            "stage": "CachedPourbaixDiagram",
                            "filter_solids": filter_solids,
                            "ion_concentration": conc,
                            "error_type": type(exc).__name__,
                            "error": str(exc),
                        },
                    )
                continue

        pbx = diagram_cache[comp_key]
        entry_obj = pbx_entries_by_mpid[mpid]

        try:
            decomp_grid = vectorized_decomposition_energies(
                pbx, entry_obj, PH_VALUES, V_VALUES
            )
        except Exception as exc:
            worker_logger.exception(
                "decomposition scan failed cs=%s mpid=%s "
                "filter_solids=%s conc=%s",
                cs, mpid, filter_solids, conc,
            )
            if error_path:
                _write_error(
                    error_path,
                    {
                        "chemsys": cs,
                        "material_id": mpid,
                        "stage": "vectorized_decomposition_energies",
                        "filter_solids": filter_solids,
                        "ion_concentration": conc,
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    },
                )
            continue

        # Flatten the (pH, V) grid into one row per cell.
        # decomp_grid[i, j] corresponds to (PH_VALUES[i], V_VALUES[j]).
        for i, p in enumerate(PH_VALUES):
            for j, v in enumerate(V_VALUES):
                rows.append(
                    {
                        "mp_id": mpid,
                        "filter_solids": bool(filter_solids),
                        "ion_concentration": float(conc),
                        "pH": int(p),
                        "V": float(v),
                        "decomposition_energy": float(decomp_grid[i, j]),
                    }
                )

    worker_logger.info(
        "cs=%s n_materials=%d n_rows=%d", cs, len(mpids_to_process), len(rows)
    )
    return rows


# Per-worker globals so we don't re-open the cache / MPRester for every chemsys
# inside one worker. ``_init_worker`` sets these after the Pool forks.
_WORKER_CACHE: ChemsysEntryCache | None = None
_WORKER_MPR: MPRester | None = None
_WORKER_ERROR_PATH: Path | None = None
_WORKER_LOGGER: logging.Logger | None = None


def _init_worker(cache_path: str, db_version: str, log_dir: str, error_path: str) -> None:
    global _WORKER_CACHE, _WORKER_MPR, _WORKER_ERROR_PATH, _WORKER_LOGGER
    _WORKER_CACHE = ChemsysEntryCache(cache_path, db_version)
    _WORKER_MPR = get_mpr().__enter__()
    _WORKER_ERROR_PATH = Path(error_path)
    _WORKER_LOGGER = _setup_worker_logger(Path(log_dir))


def _process_one_chemsys(
    docs: list[SummaryDocSubset],
) -> list[dict]:
    """Pool worker: process one chemsys and return its rows."""
    assert _WORKER_CACHE is not None
    assert _WORKER_LOGGER is not None
    try:
        return process_chemsys(
            docs=docs,
            cache=_WORKER_CACHE,
            mpr=_WORKER_MPR,
            error_path=_WORKER_ERROR_PATH,
            worker_logger=_WORKER_LOGGER,
        )
    except Exception:
        _WORKER_LOGGER.exception(
            "Unhandled exception processing cs=%s",
            docs[0].chemsys if docs else "(empty)",
        )
        return []


def _load_or_fetch_summary_docs(
    cache_dir: Path, cached_filename: str = "summary_docs.jsonl.gz"
) -> list[SummaryDocSubset]:
    """Load cached summary docs, or query MP and cache them."""
    cache_path = cache_dir / cached_filename
    if cache_path.is_file():
        with gzip.open(cache_path, "rt") as f:
            return [SummaryDocSubset(**json.loads(line)) for line in f if line.strip()]

    logger.info("Fetching summary docs from MP API (this can take a few minutes)")
    with get_mpr() as mpr:
        raw = mpr.materials.summary.search(
            fields=["chemsys", "material_id", "formula_pretty"]
        )
    docs = [
        SummaryDocSubset(
            material_id=str(d.material_id),
            chemsys=d.chemsys,
            formula_pretty=d.formula_pretty,
        )
        for d in raw
    ]
    cache_dir.mkdir(parents=True, exist_ok=True)
    with gzip.open(cache_path, "wt") as f:
        for doc in docs:
            f.write(doc.model_dump_json() + "\n")
    return docs


def _get_db_version() -> str:
    """Fetch the MP database version for cache invalidation."""
    with get_mpr() as mpr:
        v = mpr.get_database_version()
    return v or "unknown"


def run(
    output_path: Path = Path("reverse_pourbaix.parquet"),
    cache_dir: Path = Path("pbx_cache"),
    num_procs: int = 12,
    limit_chemsys: int | None = None,
) -> None:
    """End-to-end run: download (or cache-hit) every chemsys, write the parquet.

    Args:
        output_path: parquet destination. Will be a partitioned dataset directory
            if it has no .parquet extension; a single file otherwise.
        cache_dir: scratch directory for sqlite entries cache, summary docs,
            worker logs, error log, and the partial-write parquet dataset.
        num_procs: worker count for Pool. 12 is a sensible default on an HPC node.
        limit_chemsys: cap the number of chemsystems processed (for testing).
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    log_dir = cache_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    error_path = cache_dir / "errors.jsonl"

    db_version = _get_db_version()
    logger.info("MP database version: %s", db_version)
    logger.info("Schema version: %s", SCHEMA_VERSION)

    entries_cache_path = cache_dir / "pbx_entries_cache.sqlite"

    # Touch the cache once on the main process so the file exists and has
    # the schema applied before workers race to open it.
    ChemsysEntryCache(entries_cache_path, db_version)

    summary_docs = _load_or_fetch_summary_docs(cache_dir)
    logger.info("Loaded %d summary docs", len(summary_docs))

    chemsys_to_docs: dict[str, list[SummaryDocSubset]] = {}
    for doc in summary_docs:
        if doc.chemsys:
            chemsys_to_docs.setdefault(doc.chemsys, []).append(doc)

    work_items = list(chemsys_to_docs.values())
    if limit_chemsys:
        work_items = work_items[:limit_chemsys]
    # Largest chemsystems last so the pool finishes balanced.
    work_items.sort(key=len)

    logger.info(
        "Processing %d chemsystems with %d workers -> %s",
        len(work_items), num_procs, output_path,
    )

    # Write to a partitioned dataset directory; pyarrow consolidates later
    # if you want a single file. 
    dataset_dir = output_path
    if dataset_dir.suffix == ".parquet":
        # User wants a single file. We'll write to a temp dir then consolidate.
        dataset_dir = cache_dir / "parquet_dataset"
    dataset_dir.mkdir(parents=True, exist_ok=True)

    n_done = 0
    n_rows_total = 0
    with mp.Pool(
        processes=num_procs,
        initializer=_init_worker,
        initargs=(str(entries_cache_path), db_version, str(log_dir), str(error_path)),
    ) as pool:
        batch_buffer: list[dict] = []
        BATCH_FLUSH = 50_000  # rows per parquet write; ~couple MB compressed

        for rows in pool.imap_unordered(_process_one_chemsys, work_items, chunksize=4):
            n_done += 1
            if rows:
                batch_buffer.extend(rows)
                n_rows_total += len(rows)
            if len(batch_buffer) >= BATCH_FLUSH:
                _flush_rows(batch_buffer, dataset_dir)
                batch_buffer.clear()
            if n_done % 100 == 0:
                logger.info(
                    "progress=%d/%d rows=%d", n_done, len(work_items), n_rows_total
                )

        if batch_buffer:
            _flush_rows(batch_buffer, dataset_dir)

    logger.info("Done. %d rows total across %d chemsystems.", n_rows_total, n_done)

    # If user wanted a single file, consolidate the partitioned dataset.
    if output_path.suffix == ".parquet":
        logger.info("Consolidating partitioned dataset -> %s", output_path)
        table = pq.read_table(dataset_dir)
        pq.write_table(table, output_path, compression="zstd")
        logger.info("Wrote %s (%d rows)", output_path, table.num_rows)


def _flush_rows(rows: list[dict], dataset_dir: Path) -> None:
    """Append a batch of rows to the partitioned parquet dataset."""
    if not rows:
        return
    table = pa.Table.from_pylist(rows, schema=PARQUET_SCHEMA)
    pq.write_to_dataset(
        table,
        root_path=str(dataset_dir),
        partition_cols=list(PARTITION_COLS),
        compression="zstd",
        existing_data_behavior="overwrite_or_ignore",
    )

# Below is post-processing to build the enriched parquet and heatmap JSON for the web app.

SUMMARY_FIELDS = [
    "material_id",
    "formula_pretty",
    "band_gap",
    "energy_above_hull",
    "formation_energy_per_atom",
]
SUMMARY_BATCH_SIZE = 1000
HEATMAP_CUTOFFS = [0.1, 0.2, 0.3, 0.4, 0.5]
GRID_ROWS_PER_MATERIAL = len(PH_VALUES) * len(V_VALUES)


def _fetch_summary_df(mp_ids: list[str]):
    """Pull SUMMARY_FIELDS for each mp_id; one row per material."""
    import pandas as pd

    rows: list[dict] = []
    with get_mpr() as mpr:
        for i in range(0, len(mp_ids), SUMMARY_BATCH_SIZE):
            batch = mp_ids[i : i + SUMMARY_BATCH_SIZE]
            docs = mpr.materials.summary.search(material_ids=batch, fields=SUMMARY_FIELDS)
            for doc in docs:
                rows.append(
                    {
                        "mp_id": str(doc.material_id),
                        "formula_pretty": doc.formula_pretty,
                        "band_gap": doc.band_gap,
                        "energy_above_hull": doc.energy_above_hull,
                        "formation_energy_per_atom": doc.formation_energy_per_atom,
                    }
                )
            logger.info("  summary %d/%d", min(i + SUMMARY_BATCH_SIZE, len(mp_ids)), len(mp_ids))

    if not rows:
        raise RuntimeError(
            f"summary search returned 0 docs for {len(mp_ids)} mp_ids — check MP_API_KEY / network."
        )
    return pd.DataFrame(rows)


def _write_heatmap_json(df, out_path: Path, cutoffs: list[float]) -> None:
    """Aggregate the in-memory frame into the heatmap JSON.

    For each (pH, V) cell, count materials with decomposition_energy <= cutoff,
    for every cutoff. Built from the frame we already have so we don't re-read
    the parquet.
    """
    count_cols = []
    for c in cutoffs:
        col = f"_le_{c}"
        df[col] = (df["decomposition_energy"] <= c).astype("int32")
        count_cols.append(col)

    agg = (
        df.groupby(["pH", "V"], as_index=False)[count_cols].sum().sort_values(["pH", "V"])
    )
    df.drop(columns=count_cols, inplace=True)  # remove temp columns again

    grid = [
        {
            "pH": float(r["pH"]),
            "V": float(r["V"]),
            "counts": {str(c): int(r[f"_le_{c}"]) for c in cutoffs},
        }
        for _, r in agg.iterrows()
    ]
    payload = {
        "ph_values": sorted(agg["pH"].unique().tolist()),
        "v_values": sorted(agg["V"].unique().tolist(), reverse=True),
        "cutoffs": cutoffs,
        "grid": grid,
    }
    out_path.write_text(json.dumps(payload, indent=2))
    logger.info("Wrote %s (%d cells, %d cutoffs)", out_path, len(grid), len(cutoffs))


def build_web_assets(
    parquet_path: Path = Path("reverse_pourbaix.parquet"),
    enriched_path: Path | None = None,
    heatmap_path: Path | None = None,
    cutoffs: list[float] | None = None,
) -> None:
    """Build the enriched parquet + heatmap JSON the web app reads.
    """
    import pandas as pd

    cutoffs = cutoffs or HEATMAP_CUTOFFS
    enriched_path = enriched_path or parquet_path.with_name(parquet_path.stem + "_enriched.parquet")
    heatmap_path = heatmap_path or parquet_path.with_name(parquet_path.stem + "_heatmap.json")

    logger.info("Post-processing: reading %s", parquet_path)
    df = pd.read_parquet(parquet_path)
    logger.info("  %d rows, %d unique mp_ids", len(df), df["mp_id"].nunique())

    #   if ion conc. and filter solids is ever brought back, need to edit below
    #   df = df[df["filter_solids"].astype(str) == "True"]
    #   df = df[df["ion_concentration"].astype(float) == DEFAULT_ION_CONCENTRATION]
    df = df.drop(columns=["filter_solids", "ion_concentration"], errors="ignore")

    # enrich data with attributes for AgGrid
    unique_ids = sorted(df["mp_id"].unique().tolist())
    summary_df = _fetch_summary_df(unique_ids)
    n_missing = len(unique_ids) - len(summary_df)
    if n_missing:
        logger.warning("  %d mp_ids had no summary doc (enrichment left null)", n_missing)

    enriched = df.merge(summary_df, on="mp_id", how="left")

    for col in ("band_gap", "energy_above_hull", "formation_energy_per_atom"):
        if col in enriched.columns:
            enriched[col] = enriched[col].astype("float32")
    if "formula_pretty" in enriched.columns:
        enriched["formula_pretty"] = enriched["formula_pretty"].astype("category")

    logger.info("Writing %s", enriched_path)
    table = pa.Table.from_pandas(enriched, preserve_index=False)
    pq.write_table(
        table,
        enriched_path,
        compression="zstd",
        use_dictionary=True,
        row_group_size=len(enriched) // GRID_ROWS_PER_MATERIAL + 1,
    )
    logger.info("  wrote %d rows, %.1f MB", len(enriched), enriched_path.stat().st_size / 1e6)

    # heatmap JSON
    _write_heatmap_json(enriched, heatmap_path, cutoffs)

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    start = datetime.now(timezone.utc)
    logger.info("Started: %s", start.isoformat())
    run(
        output_path=Path("reverse_pourbaix.parquet"),
        cache_dir=Path("pbx_cache"),
        num_procs=12,
    )
    
    build_web_assets(Path("reverse_pourbaix.parquet"))
    
    end = datetime.now(timezone.utc)
    logger.info("Ended: %s (duration %s)", end.isoformat(), end - start)
