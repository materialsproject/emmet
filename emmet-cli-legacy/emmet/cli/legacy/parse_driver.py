"""Parse VASP launchers into Parquet tables. EXPERIMENTAL.

This module is the execution side of parsing: finding calculations, giving them
identifiers, running the parser on a Dask cluster, and writing what comes out.
What is parsed, and the tables it goes into, are defined by emmet-core, in
`emmet.core.vasp.parse` and `emmet.core.vasp.parsed`. This module is meant to be
replaceable, and can be removed without affecting emmet-core.

It does not import click, Mongo, or any of the other dependencies of the command
line interface, and it never modifies the directories it parses.

The steps are:

1. `discover_launchers` finds the directories with calculations in them.
2. `plan_parse` finds the calculations in the launchers, and gives each an
    identifier which continues from the highest identifier already used.
3. `run_parse` splits the calculations into chunks and parses them on a Dask
    cluster. Each worker writes its own Parquet files, and returns only a small
    manifest of what it did.

The output is a directory with one sub-directory for each table, named as in
`emmet.core.vasp.parsed.PARSED_TABLES`, each with Parquet files named
`<run_id>-<chunk>.parquet`. The tables are not partitioned: the partition
columns are columns of every row, and the data can be partitioned when it
is loaded into its final home.
"""

from __future__ import annotations

import logging
import os
import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from fnmatch import fnmatch
from pathlib import Path
from typing import TYPE_CHECKING

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from emmet.core.mpid import AlphaID
from emmet.core.vasp.parse import (
    DEFAULT_POLICY,
    DirectorySource,
    ParsedCalculation,
    ParsePolicy,
    parse_calculation,
)
from emmet.core.vasp.parsed import (
    PARSED_TABLES,
    ManifestRow,
    ParseOutcome,
)
from emmet.core.vasp.utils import DEFAULT_CALC_SUFFIXES, STANDARD_CALC_SUFFIX

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator, Mapping, Sequence

    from pydantic import BaseModel

    from distributed import Client

logger = logging.getLogger("emmet")

ID_PADLEN = 8
"""The length of identifiers."""

SMALL_TABLES = ("tasks", "trajectories", "manifest")
"""Tables of small rows, which are buffered. The other tables have a row group for each row."""

SMALL_TABLE_BUFFER = 256


class ParseDriverError(Exception):
    """A problem with the request to parse, as opposed to with a calculation."""


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


def _is_launcher(files: Iterable[str]) -> bool:
    """Whether a directory with these files is a launcher of VASP calculations."""
    return any(f.startswith("INCAR") for f in files)


def discover_launchers(
    directory: str | Path,
    pattern: str | None = "block_*",
    nmax: int | None = None,
) -> Iterator[str]:
    """Find the launchers in a directory. Nothing is changed.

    A launcher is a directory with an INCAR in it, and is not searched further, so
    the sub-directories of a launcher with a `relax1/` layout are not launchers.

    Parameters
    -----------
    directory : str or Path
        The directory to search.
    pattern : str or None
        A pattern for the names of the directories to search, one for each level
        below `directory`, separated by `os.sep`, e.g., `block_*/launcher_*`.
        Levels below those in the pattern are not restricted.
    nmax : int or None
        The most launchers to find.

    Yields
    -----------
    str
        The path of each launcher.
    """
    base_path = str(directory).rstrip(os.sep)
    base_depth = len(base_path.split(os.sep))
    pattern_levels = pattern.split(os.sep) if pattern else []

    found = 0
    for root, dirs, files in os.walk(base_path, topdown=True):
        if nmax is not None and found >= nmax:
            return

        level = len(root.split(os.sep)) - base_depth
        if dirs and len(pattern_levels) > level:
            dirs[:] = sorted(d for d in dirs if fnmatch(d, pattern_levels[level]))
        else:
            dirs.sort()

        if _is_launcher(files):
            dirs[:] = []
            found += 1
            yield root


# ---------------------------------------------------------------------------
# Identifiers
# ---------------------------------------------------------------------------


def normalize_identifier(identifier: str | int) -> str:
    """The form of an identifier that is stored: an AlphaID with no prefix."""
    return str(AlphaID(identifier, padlen=ID_PADLEN)).split("-")[-1]


def _max_of_column(ids: pa.ChunkedArray | pa.Array) -> int | None:
    """The highest identifier in a column of identifiers, which may have prefixes."""
    ids = ids.drop_null()
    if len(ids) == 0:
        return None
    # identifiers of the same length sort as the numbers they stand for
    without_prefix = pc.replace_substring_regex(ids, pattern="^.*-", replacement="")
    return int(AlphaID(pc.max(without_prefix).as_py(), padlen=ID_PADLEN))


def _read_local_column(
    output_dir: str | Path | None, table: str, column: str
) -> pa.Array:
    """A column of a table of an output directory. Files still being written are skipped."""
    table_dir = Path(output_dir) / table if output_dir else None
    if table_dir is None or not table_dir.exists():
        return pa.array([], type=pa.string())
    files = sorted(p for p in table_dir.glob("*.parquet") if not p.name.startswith("."))
    if not files:
        return pa.array([], type=pa.string())
    columns = [pq.read_table(f, columns=[column])[column] for f in files]
    return pa.chunked_array(
        [chunk for col in columns for chunk in col.chunks], type=pa.string()
    ).combine_chunks()


def read_local_task_ids(output_dir: str | Path | None) -> pa.Array:
    """The identifiers in the tasks table of an output directory."""
    return _read_local_column(output_dir, "tasks", "task_id")


def read_local_identifiers(output_dir: str | Path | None) -> pa.Array:
    """The identifiers which have been used in an output directory.

    These are the identifiers of the tasks, and also of the manifest, which has
    the calculations which could not be read and so have no task. An identifier
    must not be used again for another calculation, whether or not it has a task.
    """
    return pa.concat_arrays(
        [
            read_local_task_ids(output_dir),
            _read_local_column(output_dir, "manifest", "identifier"),
        ]
    )


def read_delta_task_ids(
    uri: str, storage_options: Mapping[str, str] | None = None
) -> pa.Array:
    """The identifiers in a Delta table of tasks.

    Requires deltalake, which is an optional dependency: `pip install deltalake`.
    """
    try:
        from deltalake import DeltaTable
    except ImportError as exc:
        raise ParseDriverError(
            "Reading the identifiers of a Delta table needs deltalake, which is an "
            "optional dependency. Install it with `pip install deltalake`."
        ) from exc

    table = DeltaTable(uri, storage_options=dict(storage_options or {}))
    return (
        table.to_pyarrow_dataset()
        .to_table(columns=["task_id"])["task_id"]
        .combine_chunks()
    )


def max_identifier(
    output_dir: str | Path | None = None,
    delta_uri: str | None = None,
    delta_storage_options: Mapping[str, str] | None = None,
) -> int:
    """The highest identifier used in the output directory and in the Delta table of tasks.

    The identifiers used in the output directory are those of its tasks and of its
    manifest. This is 0, which is the identifier before the first, if there are none
    in either, or if neither exists. That is how a new collection of tasks is begun.

    The identifiers must be AlphaIDs of the same length.

    Parameters
    -----------
    output_dir : str, Path or None
        The directory the parsed tables are written to, whose tables may exist.
    delta_uri : str or None
        The location of a Delta table of tasks, e.g., in S3.
    delta_storage_options : mapping of str to str
        Options for access to the Delta table.

    Returns
    -----------
    int
        The identifier as an integer: AlphaID("aaaaaaab") is 1.
    """
    highest = [0]
    for ids in (
        read_local_identifiers(output_dir),
        read_delta_task_ids(delta_uri, delta_storage_options) if delta_uri else None,
    ):
        if ids is not None and (value := _max_of_column(ids)) is not None:
            highest.append(value)
    return max(highest)


# ---------------------------------------------------------------------------
# Planning
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WorkItem:
    """A calculation to parse: small enough to send to a worker cheaply."""

    launcher: str
    calc_suffix: str
    identifier: str


@dataclass
class ParsePlan:
    """What is to be parsed, and the identifiers it will be given."""

    items: list[WorkItem] = field(default_factory=list)
    launchers: int = 0
    layouts: Counter = field(default_factory=Counter)
    empty_launchers: list[str] = field(default_factory=list)
    unassigned: list[str] = field(default_factory=list)
    first_identifier: str | None = None
    last_identifier: str | None = None

    @property
    def calculations(self) -> int:
        return len(self.items)

    def report(self) -> list[str]:
        """A description of the plan."""
        lines = [
            f"{self.launchers} launcher(s), {self.calculations} calculation(s) to parse.",
        ]
        if self.layouts:
            lines.append(
                "Layouts: "
                + ", ".join(
                    f"{count} {name}" for name, count in sorted(self.layouts.items())
                )
                + "."
            )
        if self.first_identifier:
            lines.append(
                f"Identifiers: {self.first_identifier} to {self.last_identifier}."
            )
        if self.empty_launchers:
            lines.append(
                f"{len(self.empty_launchers)} launcher(s) have no calculation with a "
                f"vasprun.xml, e.g., {self.empty_launchers[0]}."
            )
        if self.unassigned:
            lines.append(
                f"{len(self.unassigned)} calculation(s) have no identifier in the "
                f"identifier file, e.g., {self.unassigned[0]}."
            )
        return lines


def _layout(sources: Sequence[DirectorySource]) -> str:
    if any(
        Path(s.files.directory).resolve() != Path(s.locator.path).resolve()
        for s in sources
    ):
        return "subdirectory"
    if all(s.calc_suffix == STANDARD_CALC_SUFFIX for s in sources):
        return "single"
    return "suffixed"


def load_identifier_map(
    task_ids: Mapping[str, str], launchers_to_suffixes: Mapping[str, Sequence[str]]
) -> dict[tuple[str, str], str]:
    """Match the identifiers of an identifier file to calculations.

    A key is `launcher/calc_suffix`, where the launcher is the name of its directory.
    A key which is only the launcher is accepted for a launcher with a single
    calculation.

    Returns
    -----------
    dict of (launcher name, calc suffix) to identifier
        Only those found in `launchers_to_suffixes`.
    """
    assigned: dict[tuple[str, str], str] = {}
    for launcher, suffixes in launchers_to_suffixes.items():
        for suffix in suffixes:
            if (key := f"{launcher}/{suffix}") in task_ids:
                assigned[(launcher, suffix)] = normalize_identifier(task_ids[key])
            elif len(suffixes) == 1 and launcher in task_ids:
                assigned[(launcher, suffix)] = normalize_identifier(task_ids[launcher])
    return assigned


def plan_parse(
    launchers: Iterable[str | Path],
    *,
    suffixes: Sequence[str] = DEFAULT_CALC_SUFFIXES,
    output_dir: str | Path | None = None,
    delta_uri: str | None = None,
    delta_storage_options: Mapping[str, str] | None = None,
    task_ids: Mapping[str, str] | None = None,
) -> ParsePlan:
    """Find the calculations in launchers and decide their identifiers.

    Only files are listed: nothing is parsed, and nothing is written.

    Without `task_ids`, calculations are given the identifiers following the
    highest in the tasks table of `output_dir`, and in the Delta table, in the
    order they are found, or from 1 if there are none. With `task_ids`, each
    calculation has the identifier it has in it, which is an error if it is already
    used. Calculations which are not in it are not parsed, and are listed in the plan.

    Parameters
    -----------
    launchers : iterable of str or Path
        The directories of the launchers, see `discover_launchers`.
    suffixes : sequence of str
        The suffixes of the calculations in a launcher, in the order they were run.
    output_dir : str, Path or None
        The directory the parsed tables are written to.
    delta_uri : str or None
        A Delta table of tasks, whose identifiers are not to be used again.
    delta_storage_options : mapping of str to str
        Options for access to the Delta table.
    task_ids : mapping of str to str or None
        Identifiers for specific calculations, see `load_identifier_map`.

    Returns
    -----------
    ParsePlan
    """
    plan = ParsePlan()
    sources_by_launcher: dict[str, list[DirectorySource]] = {}
    for launcher in launchers:
        plan.launchers += 1
        sources = DirectorySource.from_directory(launcher, suffixes)
        if not sources:
            plan.empty_launchers.append(str(launcher))
            continue
        sources_by_launcher[str(launcher)] = sources
        plan.layouts[_layout(sources)] += 1

    if task_ids is not None:
        by_name = {Path(p).name: p for p in sources_by_launcher}
        if len(by_name) != len(sources_by_launcher):
            raise ParseDriverError(
                "Launchers need unique names to be matched with an identifier file."
            )
        assigned = load_identifier_map(
            task_ids,
            {
                name: [s.calc_suffix for s in sources_by_launcher[path]]
                for name, path in by_name.items()
            },
        )
        identifiers = list(assigned.values())
        if len(set(identifiers)) != len(identifiers):
            raise ParseDriverError("The identifier file gives some identifiers twice.")
        used = {
            normalize_identifier(i)
            for ids in (
                read_local_identifiers(output_dir),
                (
                    read_delta_task_ids(delta_uri, delta_storage_options)
                    if delta_uri
                    else pa.array([], type=pa.string())
                ),
            )
            for i in ids.to_pylist()
            if i
        }
        if clashes := sorted(used.intersection(identifiers)):
            raise ParseDriverError(
                f"{len(clashes)} identifier(s) are already used, in a tasks table or "
                f"the manifest, e.g., {clashes[0]}."
            )
        for name, path in by_name.items():
            for source in sources_by_launcher[path]:
                if (identifier := assigned.get((name, source.calc_suffix))) is None:
                    plan.unassigned.append(f"{name}/{source.calc_suffix}")
                    continue
                plan.items.append(WorkItem(path, source.calc_suffix, identifier))
    else:
        next_id = max_identifier(output_dir, delta_uri, delta_storage_options) + 1
        for path, sources in sources_by_launcher.items():
            for source in sources:
                plan.items.append(
                    WorkItem(path, source.calc_suffix, normalize_identifier(next_id))
                )
                next_id += 1

    if plan.items:
        plan.first_identifier = plan.items[0].identifier
        plan.last_identifier = plan.items[-1].identifier
    return plan


# ---------------------------------------------------------------------------
# The worker
# ---------------------------------------------------------------------------


class _TableWriters:
    """Writes the rows of tables to Parquet files, which exist when they are complete.

    Rows are written to a hidden temporary file, which is renamed once the file is
    closed without a problem, so a file with its final name is always whole.
    Tables of small rows are buffered, and the rest write each row as
    a row group as soon as it is given, so that it can be released.
    """

    def __init__(self, output_dir: Path, file_name: str) -> None:
        self.output_dir = output_dir
        self.file_name = file_name
        self.rows_written: Counter = Counter()
        self._schemas: dict[str, pa.Schema] = {}
        self._writers: dict[str, pq.ParquetWriter] = {}
        self._buffers: dict[str, list[BaseModel]] = {}

    def _schema(self, table: str) -> pa.Schema:
        if table not in self._schemas:
            self._schemas[table] = PARSED_TABLES[table].arrow_schema
        return self._schemas[table]

    def _tmp_path(self, table: str) -> Path:
        return self.output_dir / table / f".{self.file_name}.tmp"

    def _final_path(self, table: str) -> Path:
        return self.output_dir / table / self.file_name

    def write(self, table: str, row: BaseModel) -> None:
        if table in SMALL_TABLES:
            buffer = self._buffers.setdefault(table, [])
            buffer.append(row)
            if len(buffer) >= SMALL_TABLE_BUFFER:
                self._flush(table)
        else:
            self._write_rows(table, [row])

    def _flush(self, table: str) -> None:
        if rows := self._buffers.pop(table, []):
            self._write_rows(table, rows)

    def _write_rows(self, table: str, rows: list[BaseModel]) -> None:
        schema = self._schema(table)
        arrow_table = PARSED_TABLES[table].to_arrow(rows)
        del rows
        if table not in self._writers:
            self._tmp_path(table).parent.mkdir(parents=True, exist_ok=True)
            self._writers[table] = pq.ParquetWriter(
                str(self._tmp_path(table)),
                schema,
                compression="ZSTD",
                **PARSED_TABLES[table].parquet_options,
            )
        self._writers[table].write_table(arrow_table)
        self.rows_written[table] += arrow_table.num_rows

    def commit(self) -> None:
        """Finish the files, and give them their final names."""
        for table in list(self._buffers):
            self._flush(table)
        writers, self._writers = self._writers, {}
        for table, writer in writers.items():
            writer.close()
            os.replace(self._tmp_path(table), self._final_path(table))

    def abort(self) -> None:
        """Throw away what has been written."""
        self._buffers.clear()
        writers, self._writers = self._writers, {}
        for table, writer in writers.items():
            try:
                writer.close()
            finally:
                self._tmp_path(table).unlink(missing_ok=True)


def _error_manifest(item: WorkItem, exc: Exception) -> ManifestRow:
    return ManifestRow(
        identifier=item.identifier,
        dir_name=item.launcher,
        calc_suffix=item.calc_suffix,
        outcome=ParseOutcome.ERROR,  # type: ignore[arg-type]
        errors=[f"{type(exc).__name__}: {exc}"],
    )


def _find_source(item: WorkItem, suffixes: Sequence[str]) -> DirectorySource:
    for source in DirectorySource.from_directory(item.launcher, suffixes):
        if source.calc_suffix == item.calc_suffix:
            return source
    raise FileNotFoundError(
        f"No calculation {item.calc_suffix} in {item.launcher}: it may have been "
        "moved or changed since it was found."
    )


def _write_calculation(
    parsed: ParsedCalculation, writers: _TableWriters
) -> ManifestRow:
    """Write everything about a parsed calculation, and give its manifest row."""
    if parsed.task is not None:
        writers.write("tasks", parsed.task)
    if parsed.trajectory is not None:
        writers.write("trajectories", parsed.trajectory)
    for table, row in parsed.objects():
        writers.write(table, row)
    return parsed.manifest_row()


def parse_chunk(
    items: Sequence[WorkItem],
    output_dir: str | Path,
    policy: ParsePolicy = DEFAULT_POLICY,
    run_id: str = "run",
    chunk_id: int = 0,
    batch_id: str | None = None,
    tags: Sequence[str] = (),
    suffixes: Sequence[str] = DEFAULT_CALC_SUFFIXES,
) -> list[ManifestRow]:
    """Parse calculations and write their rows to Parquet files. Runs on a worker.

    Each calculation is parsed on its own, so one that cannot be read does not
    affect the others: it gets a row in the manifest that says what went wrong.

    The files written have the name `<run_id>-<chunk_id>.parquet`, in the directory
    of each table. If this raises an exception, none of the files exist.

    Parameters
    -----------
    items : sequence of WorkItem
        The calculations.
    output_dir : str or Path
        The directory of the tables.
    policy : ParsePolicy
        Which large objects to parse.
    run_id : str
        Names the files of everything parsed by one run.
    chunk_id : int
        Names the files of this chunk of the run.
    batch_id : str or None
        The batch identifier of the tasks.
    tags : sequence of str
        The tags of the tasks.
    suffixes : sequence of str
        The suffixes of the calculations in a launcher, in the order they were run.

    Returns
    -----------
    list of ManifestRow
        One for each calculation. They are also written to the manifest table.
    """
    writers = _TableWriters(Path(output_dir), f"{run_id}-{chunk_id:05d}.parquet")
    manifests: list[ManifestRow] = []
    try:
        for item in items:
            try:
                parsed = parse_calculation(
                    _find_source(item, suffixes),
                    item.identifier,
                    policy,
                    batch_id=batch_id,
                    tags=tags,
                )
                manifest = _write_calculation(parsed, writers)
            except Exception as exc:
                logger.exception(f"Failed to parse {item}")
                manifest = _error_manifest(item, exc)
            manifests.append(manifest)
            writers.write("manifest", manifest)
        writers.commit()
    except BaseException:
        writers.abort()
        raise
    return manifests


# ---------------------------------------------------------------------------
# Running
# ---------------------------------------------------------------------------


@dataclass
class ParseResult:
    """What came of running the parser."""

    run_id: str
    manifests: list[ManifestRow] = field(default_factory=list)
    failed_chunks: dict[int, str] = field(default_factory=dict)

    def summary(self) -> list[str]:
        """A description of the result."""
        outcomes = Counter(m.outcome.value for m in self.manifests)
        tables = Counter(t for m in self.manifests for t in m.tables)
        lines = [
            f"Run {self.run_id}: parsed {len(self.manifests)} calculation(s): "
            + (", ".join(f"{n} {o}" for o, n in sorted(outcomes.items())) or "none")
            + "."
        ]
        if tables:
            lines.append(
                "Rows of large objects: "
                + ", ".join(f"{n} {t}" for t, n in sorted(tables.items()))
                + "."
            )
        if n_errors := sum(len(m.errors) for m in self.manifests):
            lines.append(f"{n_errors} error(s) are recorded in the manifest.")
        for chunk_id, error in sorted(self.failed_chunks.items()):
            lines.append(f"Chunk {chunk_id} failed and wrote nothing: {error}")
        return lines


def new_run_id() -> str:
    """An identifier for a run, which sorts by time."""
    return f"{datetime.now(UTC):%Y%m%dT%H%M%S}-{uuid.uuid4().hex[:6]}"


def make_client(
    scheduler_address: str | None = None,
    scheduler_file: str | None = None,
    nworkers: int | None = None,
) -> Client:
    """Connect to a Dask cluster, or start one on this machine.

    Parameters
    -----------
    scheduler_address : str or None
        The address of a running scheduler.
    scheduler_file : str or None
        The file a running scheduler wrote its address to.
    nworkers : int or None
        The number of processes if a cluster is started here.
    """
    from distributed import Client, LocalCluster

    if scheduler_address:
        return Client(scheduler_address)
    if scheduler_file:
        return Client(scheduler_file=scheduler_file)
    return Client(LocalCluster(n_workers=nworkers, threads_per_worker=1))


def run_parse(
    items: Sequence[WorkItem],
    output_dir: str | Path,
    policy: ParsePolicy = DEFAULT_POLICY,
    *,
    client: Client | None = None,
    chunk_size: int = 20,
    run_id: str | None = None,
    batch_id: str | None = None,
    tags: Sequence[str] = (),
    suffixes: Sequence[str] = DEFAULT_CALC_SUFFIXES,
) -> ParseResult:
    """Parse calculations on a Dask cluster.

    The calculations are split into chunks, each of which is parsed by a
    worker, which writes its own files. The workers must be able to write to
    `output_dir`, which usually means that they share a file system with it.

    A chunk which fails as a whole, for example because its worker was
    killed, is reported in the result and does not stop the others.

    Parameters
    -----------
    items : sequence of WorkItem
        The calculations, see `plan_parse`.
    output_dir : str or Path
        The directory of the tables.
    policy : ParsePolicy
        Which large objects to parse.
    client : distributed.Client or None
        The cluster to use. A cluster on this machine is made and closed if None.
    chunk_size : int
        The number of calculations each worker parses at a time.
    run_id : str or None
        Names the files of this run. A new one is made by default.
    batch_id : str or None
        The batch identifier of the tasks.
    tags : sequence of str
        The tags of the tasks.
    suffixes : sequence of str
        The suffixes of the calculations in a launcher.

    Returns
    -----------
    ParseResult
    """
    from distributed import as_completed

    if chunk_size < 1:
        raise ParseDriverError("The chunk size must be at least 1.")
    result = ParseResult(run_id=run_id or new_run_id())
    if not items:
        return result

    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    chunks = [items[i : i + chunk_size] for i in range(0, len(items), chunk_size)]

    own_client = client is None
    client = client or make_client()
    try:
        futures = {
            client.submit(
                parse_chunk,
                chunk,
                str(output_dir),
                policy,
                result.run_id,
                chunk_id,
                batch_id,
                tuple(tags),
                tuple(suffixes),
                pure=False,
                key=f"parse-{result.run_id}-{chunk_id}",
            ): chunk_id
            for chunk_id, chunk in enumerate(chunks)
        }
        done = 0
        for future in as_completed(futures):
            chunk_id = futures[future]
            try:
                result.manifests.extend(future.result())
            except Exception as exc:
                logger.error(f"Chunk {chunk_id} failed: {exc}")
                result.failed_chunks[chunk_id] = f"{type(exc).__name__}: {exc}"
            done += 1
            logger.info(f"{done}/{len(chunks)} chunks done.")
    finally:
        if own_client:
            cluster = getattr(client, "cluster", None)
            client.close()
            if cluster is not None:
                cluster.close()
    return result
