"""Test the experimental driver which parses launchers into Parquet tables."""

import shutil
import warnings
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from emmet.cli.legacy import parse_driver
from emmet.cli.legacy.parse_driver import (
    ParseDriverError,
    WorkItem,
    discover_launchers,
    load_identifier_map,
    max_identifier,
    normalize_identifier,
    parse_chunk,
    plan_parse,
    read_local_identifiers,
    read_local_task_ids,
    run_parse,
)
from emmet.core.testing_utils import TEST_FILES_DIR, DataArchive
from emmet.core.vasp.parse import ParsePolicy
from emmet.core.vasp.parsed import PARSED_TABLES, ParseOutcome, TrajectoryRow

from conftest import snapshot

warnings.filterwarnings("ignore")


def read_table(output_dir: Path, table: str) -> pa.Table:
    """Read a table, which is the Parquet files of a directory."""
    return pq.read_table(output_dir / table)


def names(paths) -> list[str]:
    return sorted(p.name for p in paths)


def write_tasks(output_dir: Path, identifiers: list[str], name: str = "old.parquet"):
    (output_dir / "tasks").mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.table({"task_id": identifiers}), output_dir / "tasks" / name)


class TestDiscovery:
    def test_finds_launchers(self, launchers):
        found = [
            Path(p).relative_to(launchers).as_posix()
            for p in discover_launchers(launchers)
        ]
        assert found == [
            "block_1/launcher_legacy",
            "block_1/launcher_single",
            "block_2/launcher_broken",
        ]

    def test_pattern_and_nmax(self, launchers):
        def find(**kwargs):
            return [Path(p).name for p in discover_launchers(launchers, **kwargs)]

        assert find(pattern="block_1") == ["launcher_legacy", "launcher_single"]
        assert find(pattern="block_2/launcher_*") == ["launcher_broken"]
        assert find(pattern="block_*/launcher_s*") == ["launcher_single"]
        assert find(pattern="nothing_*") == []
        assert len(find(nmax=2)) == 2
        assert find(nmax=0) == []
        # with no pattern every directory is searched
        assert len(find(pattern=None)) == 3

    def test_launchers_are_not_searched(self, launchers):
        nested = launchers / "block_1/launcher_single/inner"
        nested.mkdir()
        (nested / "INCAR").touch()
        assert len(list(discover_launchers(launchers))) == 3

    def test_nothing_is_changed(self, launchers):
        before = snapshot(launchers)
        list(discover_launchers(launchers))
        assert snapshot(launchers) == before


class TestIdentifiers:
    @pytest.mark.parametrize(
        "given, expected",
        [
            (1, "aaaaaaab"),
            ("aaaaaaab", "aaaaaaab"),
            ("mp-aaaaaaab", "aaaaaaab"),
            ("mp-1", "aaaaaaab"),
            ("1", "aaaaaaab"),
            (0, "aaaaaaaa"),
        ],
    )
    def test_normalize(self, given, expected):
        assert normalize_identifier(given) == expected

    def test_from_scratch(self, tmp_path):
        assert max_identifier() == 0
        assert max_identifier(tmp_path) == 0
        assert max_identifier(tmp_path / "does-not-exist") == 0

    def test_local_table(self, tmp_path):
        write_tasks(tmp_path, ["aaaaaaab", "aaaaaaaz", "aaaaaaac"])
        assert max_identifier(tmp_path) == 25
        # tasks from several runs, with and without prefixes
        write_tasks(tmp_path, ["mp-aaaaaabb", "aaaaaaad"], name="other.parquet")
        assert max_identifier(tmp_path) == int(
            parse_driver.AlphaID("aaaaaabb", padlen=8)
        )
        assert len(read_local_task_ids(tmp_path)) == 5

    def test_manifest_identifiers_are_used(self, tmp_path):
        """A calculation which could not be read has no task, but its identifier is taken."""
        write_tasks(tmp_path, ["aaaaaaac"])
        (tmp_path / "manifest").mkdir()
        pq.write_table(
            pa.table({"identifier": ["aaaaaaac", "aaaaaaaf"]}),
            tmp_path / "manifest" / "run.parquet",
        )
        assert sorted(read_local_identifiers(tmp_path).to_pylist()) == [
            "aaaaaaac",
            "aaaaaaac",
            "aaaaaaaf",
        ]
        assert read_local_task_ids(tmp_path).to_pylist() == ["aaaaaaac"]
        assert max_identifier(tmp_path) == 5

    def test_manifest_alone(self, tmp_path):
        (tmp_path / "manifest").mkdir()
        pq.write_table(
            pa.table({"identifier": ["aaaaaaad"]}),
            tmp_path / "manifest" / "run.parquet",
        )
        assert max_identifier(tmp_path) == 3

    def test_unfinished_files_are_not_tasks(self, tmp_path):
        write_tasks(tmp_path, ["aaaaaaac"])
        write_tasks(tmp_path, ["aaaaaabb"], name=".run.parquet.tmp")
        assert max_identifier(tmp_path) == 2

    def test_larger_of_local_and_delta(self, tmp_path, monkeypatch):
        write_tasks(tmp_path, ["aaaaaaaz"])  # 25
        monkeypatch.setattr(
            parse_driver,
            "read_delta_task_ids",
            lambda uri, options=None: pa.array(["aaaaaaab", "aaaaaabb"]),
        )
        assert max_identifier(tmp_path, delta_uri="s3://bucket/tasks") == int(
            parse_driver.AlphaID("aaaaaabb", padlen=8)
        )
        monkeypatch.setattr(
            parse_driver,
            "read_delta_task_ids",
            lambda uri, options=None: pa.array(["aaaaaaab"]),
        )
        assert max_identifier(tmp_path, delta_uri="s3://bucket/tasks") == 25
        # the Delta table alone
        assert max_identifier(delta_uri="s3://bucket/tasks") == 1

    def test_empty_delta_table(self, monkeypatch):
        monkeypatch.setattr(
            parse_driver,
            "read_delta_task_ids",
            lambda uri, options=None: pa.array([], type=pa.string()),
        )
        assert max_identifier(delta_uri="s3://bucket/tasks") == 0

    def test_real_delta_table(self, tmp_path):
        deltalake = pytest.importorskip("deltalake")
        table = tmp_path / "delta-tasks"
        deltalake.write_deltalake(
            str(table), pa.table({"task_id": ["aaaaaaab", "aaaaaaaz", "aaaaaaac"]})
        )
        assert max_identifier(delta_uri=str(table)) == 25

    def test_delta_needs_deltalake(self, monkeypatch):
        import builtins

        real_import = builtins.__import__

        def no_deltalake(name, *args, **kwargs):
            if name == "deltalake":
                raise ImportError("no deltalake")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", no_deltalake)
        with pytest.raises(ParseDriverError, match="pip install deltalake"):
            max_identifier(delta_uri="s3://bucket/tasks")


class TestPlan:
    def test_from_scratch(self, launchers):
        plan = plan_parse(discover_launchers(launchers))

        assert plan.launchers == 3 and plan.calculations == 4
        # the first identifier is 1
        assert [i.identifier for i in plan.items] == [
            "aaaaaaab",
            "aaaaaaac",
            "aaaaaaad",
            "aaaaaaae",
        ]
        assert [(Path(i.launcher).name, i.calc_suffix) for i in plan.items] == [
            ("launcher_legacy", "relax1"),
            ("launcher_legacy", "relax2"),
            ("launcher_single", "standard"),
            ("launcher_broken", "standard"),
        ]
        assert plan.layouts == {"suffixed": 1, "single": 2}
        assert (plan.first_identifier, plan.last_identifier) == ("aaaaaaab", "aaaaaaae")
        assert plan.empty_launchers == []

    def test_continues_from_existing_tasks(self, launchers, tmp_path):
        output = tmp_path / "out"
        write_tasks(output, ["aaaaaaab", "aaaaaaaz"])
        plan = plan_parse(discover_launchers(launchers), output_dir=output)
        assert plan.first_identifier == "aaaaaaba"  # 26 + 1
        assert plan.last_identifier == "aaaaaabd"

    def test_launchers_without_a_calculation(self, launchers):
        empty = launchers / "block_3" / "launcher_empty"
        empty.mkdir(parents=True)
        (empty / "INCAR").touch()
        plan = plan_parse(discover_launchers(launchers))
        assert plan.calculations == 4 and plan.launchers == 4
        assert plan.empty_launchers == [str(empty)]
        assert "no calculation with a vasprun.xml" in "\n".join(plan.report())

    def test_subdirectory_layout(self, launchers):
        legacy = launchers / "block_1" / "launcher_legacy"
        for suffix in ("relax1", "relax2"):
            (legacy / suffix).mkdir()
            for path in list(legacy.glob(f"*.{suffix}.gz")):
                stem = path.name.replace(f".{suffix}", "")
                path.rename(legacy / suffix / stem)
        plan = plan_parse([legacy])
        assert plan.layouts == {"subdirectory": 1}
        assert [i.calc_suffix for i in plan.items] == ["relax1", "relax2"]

    def test_suffixes(self, launchers):
        plan = plan_parse(discover_launchers(launchers), suffixes=("relax2",))
        legacy = [i for i in plan.items if "legacy" in i.launcher]
        assert [i.calc_suffix for i in legacy] == ["relax2"]

    def test_report(self, launchers):
        report = "\n".join(plan_parse(discover_launchers(launchers)).report())
        assert "3 launcher(s), 4 calculation(s)" in report
        assert "aaaaaaab to aaaaaaae" in report
        assert "2 single" in report and "1 suffixed" in report

    def test_nothing_is_changed(self, launchers):
        before = snapshot(launchers)
        plan_parse(discover_launchers(launchers))
        assert snapshot(launchers) == before

    class TestIdentifierFile:
        def test_keys(self):
            launchers = {
                "launcher_a": ["standard"],
                "launcher_b": ["relax1", "relax2"],
                "launcher_c": ["relax1", "relax2"],
            }
            assigned = load_identifier_map(
                {
                    "launcher_a": "mp-1",  # a launcher with one calculation
                    "launcher_b/relax1": "aaaaaaad",
                    "launcher_b/relax2": 4,
                    "launcher_c": "aaaaaaaf",  # not enough for two calculations
                },
                launchers,
            )
            assert assigned == {
                ("launcher_a", "standard"): "aaaaaaab",
                ("launcher_b", "relax1"): "aaaaaaad",
                ("launcher_b", "relax2"): "aaaaaaae",
            }

        def test_plan(self, launchers):
            plan = plan_parse(
                discover_launchers(launchers),
                task_ids={
                    "launcher_single": "mp-10",
                    "launcher_legacy/relax1": "mp-20",
                    "launcher_legacy/relax2": "mp-21",
                },
            )
            assert {
                (Path(i.launcher).name, i.calc_suffix): i.identifier for i in plan.items
            } == {
                ("launcher_single", "standard"): normalize_identifier(10),
                ("launcher_legacy", "relax1"): normalize_identifier(20),
                ("launcher_legacy", "relax2"): normalize_identifier(21),
            }
            # launchers which are not in the file are not parsed
            assert plan.unassigned == ["launcher_broken/standard"]
            assert "no identifier in the identifier file" in "\n".join(plan.report())

        def test_identifiers_must_be_unused(self, launchers, tmp_path):
            output = tmp_path / "out"
            write_tasks(output, [normalize_identifier(10)])
            with pytest.raises(ParseDriverError, match="already used"):
                plan_parse(
                    discover_launchers(launchers),
                    output_dir=output,
                    task_ids={"launcher_single": "mp-10"},
                )

        def test_identifiers_must_not_be_in_the_manifest(self, launchers, tmp_path):
            output = tmp_path / "out"
            (output / "manifest").mkdir(parents=True)
            pq.write_table(
                pa.table({"identifier": [normalize_identifier(10)]}),
                output / "manifest" / "run.parquet",
            )
            with pytest.raises(ParseDriverError, match="already used"):
                plan_parse(
                    discover_launchers(launchers),
                    output_dir=output,
                    task_ids={"launcher_single": "mp-10"},
                )

        def test_identifiers_must_be_unique(self, launchers):
            with pytest.raises(ParseDriverError, match="twice"):
                plan_parse(
                    discover_launchers(launchers),
                    task_ids={
                        "launcher_single": "mp-10",
                        "launcher_broken": "mp-10",
                    },
                )


@pytest.fixture
def items(launchers) -> list[WorkItem]:
    return plan_parse(discover_launchers(launchers)).items


class TestParseChunk:
    def test_writes_tables(self, items, tmp_path):
        output = tmp_path / "out"
        manifests = parse_chunk(items, output, run_id="r1", chunk_id=3)

        assert len(manifests) == 4
        by_id = {m.identifier: m for m in manifests}
        assert by_id["aaaaaaab"].outcome == ParseOutcome.PARSED  # relax1
        assert by_id["aaaaaaad"].outcome == ParseOutcome.PARSED  # single
        assert by_id["aaaaaaae"].outcome == ParseOutcome.ERROR  # broken

        # every table has one file for this chunk, and nothing else is left behind
        files = sorted(
            p.relative_to(output).as_posix() for p in output.rglob("*") if p.is_file()
        )
        assert files and all(f.endswith("/r1-00003.parquet") for f in files)
        assert not [p for p in output.rglob("*") if p.name.endswith(".tmp")]

        # a task and a trajectory for each calculation which could be read
        tasks = read_table(output, "tasks").to_pylist()
        assert sorted(t["task_id"] for t in tasks) == [
            "aaaaaaab",
            "aaaaaaac",
            "aaaaaaad",
        ]
        assert {t["calc_suffix"] for t in tasks} == {"relax1", "relax2", "standard"}
        trajectories = read_table(output, "trajectories")
        assert sorted(trajectories["identifier"].to_pylist()) == [
            "aaaaaaab",
            "aaaaaaac",
            "aaaaaaad",
        ]

        # the legacy launcher has a row for each calculation, which share a directory
        legacy = [t for t in tasks if t["calc_suffix"] in ("relax1", "relax2")]
        assert len({t["dir_name"] for t in legacy}) == 1
        relax1 = next(t for t in legacy if t["calc_suffix"] == "relax1")
        relax2 = next(t for t in legacy if t["calc_suffix"] == "relax2")
        assert relax1["orig_inputs"] is not None and relax2["orig_inputs"] is None

        # the electronic structure of the NSCF calculation is split from its projections
        for table in (
            "total-dos",
            "projected-dos",
            "bandstructures",
            "projected-bandstructures",
        ):
            assert read_table(output, table)["identifier"].to_pylist() == ["aaaaaaad"]

        # the manifest has every calculation, including the one that failed
        manifest = read_table(output, "manifest").to_pylist()
        assert sorted(m["identifier"] for m in manifest) == sorted(by_id)
        broken = next(m for m in manifest if m["identifier"] == "aaaaaaae")
        assert broken["outcome"] == "error" and "OUTCAR" in broken["errors"][0]
        assert next(m for m in manifest if m["identifier"] == "aaaaaaad")["tables"] == [
            "total-dos",
            "projected-dos",
            "bandstructures",
            "projected-bandstructures",
        ]

    def test_tables_have_their_schemas(self, items, tmp_path):
        from emmet.core.arrow import arrowize

        output = tmp_path / "out"
        parse_chunk(items, output)
        for table in output.iterdir():
            spec = PARSED_TABLES[table.name]
            expected = pa.schema(arrowize(spec.row_model))
            expected = pa.schema([expected.field(n) for n in spec.ordered_columns])
            for file in table.glob("*.parquet"):
                assert pq.read_schema(file).equals(
                    expected, check_metadata=False
                ), table.name

        # the trajectories have the columns and order of those in production
        assert pq.read_schema(
            next((output / "trajectories").glob("*.parquet"))
        ).names == (PARSED_TABLES["trajectories"].ordered_columns)

    def test_float32_columns_are_written_with_byte_stream_split(
        self, items, launchers, tmp_path
    ):
        """Checked in the files, as a writer ignores a path which is not a column."""
        # a launcher with a CHGCAR, which the others do not have
        with DataArchive.extract(TEST_FILES_DIR / "vasp" / "Si_static.json.gz") as d:
            shutil.copytree(d, launchers / "block_3" / "launcher_static")
        items = plan_parse(discover_launchers(launchers)).items

        output = tmp_path / "out"
        parse_chunk(items, output)
        written = {p.name for p in output.iterdir()}
        assert {"charge-density", "total-dos", "bandstructures"} <= written

        for table in output.iterdir():
            options = PARSED_TABLES[table.name].parquet_options
            for file in table.glob("*.parquet"):
                group = pq.ParquetFile(file).metadata.row_group(0)
                encodings = {
                    group.column(i).path_in_schema: group.column(i).encodings
                    for i in range(group.num_columns)
                }
                split = {p for p, e in encodings.items() if "BYTE_STREAM_SPLIT" in e}
                assert split == set(options["use_byte_stream_split"]), table.name

        # the grid of the charge density is among them
        group = pq.ParquetFile(
            next((output / "charge-density").glob("*.parquet"))
        ).metadata.row_group(0)
        by_path = {
            group.column(i).path_in_schema: group.column(i).encodings
            for i in range(group.num_columns)
        }
        assert "BYTE_STREAM_SPLIT" in by_path["total.list.element"]

    def test_rows_are_the_parsed_objects(self, items, tmp_path):
        output = tmp_path / "out"
        parse_chunk(items, output)
        row = read_table(output, "trajectories").to_pylist()[0]
        restored = TrajectoryRow(**row)
        assert restored.identifier in {"aaaaaaab", "aaaaaaac", "aaaaaaad"}
        assert restored.num_ionic_steps >= 1

    def test_policy(self, items, tmp_path):
        output = tmp_path / "out"
        policy = ParsePolicy(dos_task_types=(), bandstructure_task_types=())
        parse_chunk(items, output, policy)
        assert sorted(p.name for p in output.iterdir()) == [
            "manifest",
            "tasks",
            "trajectories",
        ]

    def test_batch_and_tags(self, items, tmp_path):
        output = tmp_path / "out"
        parse_chunk(items, output, batch_id="batch-1", tags=["tag-a"])
        for task in read_table(output, "tasks").to_pylist():
            assert task["batch_id"] == "batch-1" and "tag-a" in task["tags"]

    def test_a_changed_launcher_is_recorded(self, items, launchers, tmp_path):
        output = tmp_path / "out"
        for path in (launchers / "block_1/launcher_single").glob("*"):
            path.unlink()
        manifests = {m.identifier: m for m in parse_chunk(items, output)}
        assert manifests["aaaaaaad"].outcome == ParseOutcome.ERROR
        assert "may have been moved or changed" in manifests["aaaaaaad"].errors[0]
        assert manifests["aaaaaaab"].outcome == ParseOutcome.PARSED

    def test_one_bad_calculation_does_not_stop_the_chunk(
        self, items, tmp_path, monkeypatch
    ):
        """A problem while writing a calculation is recorded, and the rest go on."""
        original = parse_driver._write_calculation
        calls = []

        def failing(parsed, writers):
            calls.append(parsed.identifier)
            if parsed.identifier == "aaaaaaac":
                raise RuntimeError("could not write")
            return original(parsed, writers)

        monkeypatch.setattr(parse_driver, "_write_calculation", failing)
        manifests = {m.identifier: m for m in parse_chunk(items, tmp_path / "out")}
        assert manifests["aaaaaaac"].outcome == ParseOutcome.ERROR
        assert "could not write" in manifests["aaaaaaac"].errors[0]
        assert manifests["aaaaaaad"].outcome == ParseOutcome.PARSED

    def test_a_crash_leaves_no_files(self, items, tmp_path, monkeypatch):
        output = tmp_path / "out"

        def crash(self):
            raise OSError("disk full")

        # a failure which is not about any calculation: finishing the files
        monkeypatch.setattr(parse_driver._TableWriters, "commit", crash)
        with pytest.raises(OSError, match="disk full"):
            parse_chunk(items, output)
        left = [p for p in output.rglob("*") if p.is_file()]
        assert left == []

    def test_files_are_not_visible_until_complete(self, items, tmp_path, monkeypatch):
        """While a chunk is being written its files have no final name."""
        output = tmp_path / "out"
        seen = []
        original = parse_driver._TableWriters.write

        def spying(self, table, row):
            original(self, table, row)
            seen.append(sorted(p.name for p in output.rglob("*.parquet")))

        monkeypatch.setattr(parse_driver._TableWriters, "write", spying)
        parse_chunk(items, output, run_id="r1")
        assert seen and all(names == [] for names in seen)
        assert output.joinpath("tasks", "r1-00000.parquet").exists()

    def test_large_rows_are_written_one_at_a_time(self, launchers, tmp_path):
        """The row groups of a large table are rows, so they can be freed as they go."""
        output = tmp_path / "out"
        items = plan_parse([launchers / "block_1" / "launcher_single"]).items
        parse_chunk(items, output)
        metadata = pq.ParquetFile(
            next((output / "projected-bandstructures").glob("*.parquet"))
        ).metadata
        assert metadata.num_row_groups == metadata.num_rows == 1

    def test_small_rows_are_buffered(self, items, tmp_path):
        output = tmp_path / "out"
        parse_chunk(items, output)
        metadata = pq.ParquetFile(next((output / "tasks").glob("*.parquet"))).metadata
        assert metadata.num_rows == 3 and metadata.num_row_groups == 1

    def test_sources_are_not_changed(self, items, launchers, tmp_path):
        before = snapshot(launchers)
        parse_chunk(items, tmp_path / "out")
        assert snapshot(launchers) == before


class TestRun:
    @pytest.fixture
    def client(self):
        from distributed import Client, LocalCluster

        cluster = LocalCluster(
            n_workers=1, threads_per_worker=2, processes=False, dashboard_address=None
        )
        client = Client(cluster)
        yield client
        client.close()
        cluster.close()

    def test_run(self, items, launchers, tmp_path, client):
        output = tmp_path / "out"
        before = snapshot(launchers)
        result = run_parse(
            items,
            output,
            client=client,
            chunk_size=2,
            run_id="run-a",
            batch_id="batch-1",
        )

        assert result.failed_chunks == {}
        assert len(result.manifests) == 4
        assert sorted(p.name for p in (output / "tasks").glob("*.parquet")) == [
            "run-a-00000.parquet",
            "run-a-00001.parquet",
        ]
        assert read_table(output, "tasks").num_rows == 3
        assert read_table(output, "manifest").num_rows == 4
        assert snapshot(launchers) == before

        summary = "\n".join(result.summary())
        assert (
            "4 calculation(s)" in summary
            and "3 parsed" in summary
            and "1 error" in summary
        )
        assert "error(s) are recorded in the manifest" in summary

    def test_a_second_run_continues_the_identifiers(self, launchers, tmp_path, client):
        output = tmp_path / "out"
        first = plan_parse(discover_launchers(launchers), output_dir=output)
        run_parse(first.items, output, client=client, run_id="run-a")

        second = plan_parse(discover_launchers(launchers), output_dir=output)
        assert second.first_identifier == "aaaaaaaf"
        run_parse(second.items, output, client=client, run_id="run-b")

        ids = read_table(output, "tasks")["task_id"].to_pylist()
        assert len(ids) == 6 and len(set(ids)) == 6
        assert max_identifier(output) == 8

    def test_a_failed_chunk_does_not_stop_the_others(
        self, items, tmp_path, client, monkeypatch
    ):
        original = parse_driver.parse_chunk

        def sometimes_failing(items, output_dir, policy, run_id, chunk_id, *args):
            if chunk_id == 1:
                raise MemoryError("worker was out of memory")
            return original(items, output_dir, policy, run_id, chunk_id, *args)

        monkeypatch.setattr(parse_driver, "parse_chunk", sometimes_failing)
        output = tmp_path / "out"
        result = run_parse(items, output, client=client, chunk_size=2, run_id="run-a")

        assert list(result.failed_chunks) == [1]
        assert "out of memory" in result.failed_chunks[1]
        assert len(result.manifests) == 2
        assert [p.name for p in (output / "manifest").glob("*.parquet")] == [
            "run-a-00000.parquet"
        ]
        assert "Chunk 1 failed and wrote nothing" in "\n".join(result.summary())

    def test_nothing_to_parse(self, tmp_path, client):
        output = tmp_path / "out"
        result = run_parse([], output, client=client)
        assert result.manifests == []
        assert not output.exists()

    def test_chunk_size(self, items, tmp_path, client):
        with pytest.raises(ParseDriverError, match="at least 1"):
            run_parse(items, tmp_path / "out", client=client, chunk_size=0)

    def test_local_cluster_by_default(self, items, tmp_path, monkeypatch):
        """Without a cluster one is started on this machine, and is stopped afterwards."""
        from distributed import Client, LocalCluster

        started = []

        def make_client(*args, **kwargs):
            cluster = LocalCluster(
                n_workers=1,
                threads_per_worker=1,
                processes=False,
                dashboard_address=None,
            )
            started.append(cluster)
            return Client(cluster)

        monkeypatch.setattr(parse_driver, "make_client", make_client)
        output = tmp_path / "out"
        result = run_parse(items[:2], output, chunk_size=2)
        assert len(result.manifests) == 2 and len(started) == 1
        assert started[0].status.name in ("closed", "closing")
