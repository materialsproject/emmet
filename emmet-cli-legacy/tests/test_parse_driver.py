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
from emmet.core.arrow import arrowize
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
            "block_1/launcher_double_relax",
            "block_1/launcher_single",
            "block_2/launcher_broken",
        ]

    def test_pattern_and_nmax(self, launchers):
        def find(**kwargs):
            return [Path(p).name for p in discover_launchers(launchers, **kwargs)]

        assert find(pattern="block_1") == ["launcher_double_relax", "launcher_single"]
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
            ("launcher_double_relax", "relax1"),
            ("launcher_double_relax", "relax2"),
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
        double_relax = launchers / "block_1" / "launcher_double_relax"
        for suffix in ("relax1", "relax2"):
            (double_relax / suffix).mkdir()
            for path in list(double_relax.glob(f"*.{suffix}.gz")):
                stem = path.name.replace(f".{suffix}", "")
                path.rename(double_relax / suffix / stem)
        plan = plan_parse([double_relax])
        assert plan.layouts == {"subdirectory": 1}
        assert [i.calc_suffix for i in plan.items] == ["relax1", "relax2"]

    def test_suffixes(self, launchers):
        plan = plan_parse(discover_launchers(launchers), suffixes=("relax2",))
        double_relax = [i for i in plan.items if "double_relax" in i.launcher]
        assert [i.calc_suffix for i in double_relax] == ["relax2"]

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
                    "launcher_double_relax/relax1": "mp-20",
                    "launcher_double_relax/relax2": "mp-21",
                },
            )
            assert {
                (Path(i.launcher).name, i.calc_suffix): i.identifier for i in plan.items
            } == {
                ("launcher_single", "standard"): normalize_identifier(10),
                ("launcher_double_relax", "relax1"): normalize_identifier(20),
                ("launcher_double_relax", "relax2"): normalize_identifier(21),
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

        # the double-relax launcher has a row for each calculation, which share a directory
        double_relax = [t for t in tasks if t["calc_suffix"] in ("relax1", "relax2")]
        assert len({t["dir_name"] for t in double_relax}) == 1
        relax1 = next(t for t in double_relax if t["calc_suffix"] == "relax1")
        relax2 = next(t for t in double_relax if t["calc_suffix"] == "relax2")
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

        assert pq.read_schema(
            next((output / "trajectories").glob("*.parquet"))
        ).names == (PARSED_TABLES["trajectories"].ordered_columns)

    def test_statistics_are_written_for_the_columns_which_have_them(
        self, items, tmp_path
    ):
        """Checked in the files: the JSON strings of the tasks have no min and max."""
        output = tmp_path / "out"
        parse_chunk(items, output)

        for table in output.iterdir():
            spec = PARSED_TABLES[table.name]
            wanted = set(spec.statistics_columns)
            for file in table.glob("*.parquet"):
                metadata = pq.ParquetFile(file).metadata
                for group in range(metadata.num_row_groups):
                    for i in range(metadata.num_columns):
                        column = metadata.row_group(group).column(i)
                        has = bool(
                            column.statistics is not None
                            and column.statistics.has_min_max
                        )
                        if column.path_in_schema not in wanted:
                            assert not has, (table.name, column.path_in_schema)
        group = pq.ParquetFile(
            next((output / "tasks").glob("*.parquet"))
        ).metadata.row_group(0)
        by_path = {
            group.column(i).path_in_schema: group.column(i)
            for i in range(group.num_columns)
        }
        assert by_path["task_id"].statistics.has_min_max
        assert by_path["input.parameters"].statistics is None or not (
            by_path["input.parameters"].statistics.has_min_max
        )

    def test_a_calculation_without_stress_is_parsed(self, launchers, tmp_path):
        """ISIF = 0 calculations have no stress, and are parsed."""
        with DataArchive.extract(TEST_FILES_DIR / "vasp" / "defect_run.json.gz") as d:
            shutil.copytree(d, launchers / "block_3" / "launcher_fixed_cell")
        items = plan_parse(discover_launchers(launchers)).items

        output = tmp_path / "out"
        manifests = parse_chunk(items, output)
        fixed = next(m for m in manifests if "launcher_fixed_cell" in m.dir_name)
        assert fixed.outcome == ParseOutcome.PARSED and fixed.errors == []
        trajectories = read_table(output, "trajectories").to_pylist()
        row = TrajectoryRow(
            **next(t for t in trajectories if t["identifier"] == fixed.identifier)
        )
        assert row.stress is None and row.forces is not None and row.isif == 0
        assert fixed.identifier in read_table(output, "tasks")["task_id"].to_pylist()

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


class TestRealCalculations:
    """Calculations of real runs, written to Parquet and read back from the files."""

    @pytest.fixture(scope="class")
    def written(self, tmp_path_factory):
        root = tmp_path_factory.mktemp("real")
        launchers = root / "launchers"
        for name, fixture in (
            ("block_1/launcher_static", "magnetic_static_volumetric"),
            ("block_1/launcher_line", "spin_nscf_line"),
            ("block_2/launcher_triple", "scan_triple_relax"),
        ):
            with DataArchive.extract(
                TEST_FILES_DIR / "vasp" / f"{fixture}.json.gz"
            ) as d:
                shutil.copytree(d, launchers / name)
        output = root / "out"
        plan = plan_parse(discover_launchers(launchers))
        manifests = parse_chunk(plan.items, output)
        by_launcher = {Path(m.dir_name).name: [] for m in manifests}
        for manifest in manifests:
            by_launcher[Path(manifest.dir_name).name].append(manifest)
        return output, by_launcher

    def rows(self, output, table, launcher, written_by):
        identifiers = {m.identifier for m in written_by[launcher]}
        return [
            r
            for r in read_table(output, table).to_pylist()
            if r.get("identifier", r.get("task_id")) in identifiers
        ]

    def test_everything_is_parsed(self, written):
        _, by_launcher = written
        assert {k: len(v) for k, v in by_launcher.items()} == {
            "launcher_static": 1,
            "launcher_line": 1,
            "launcher_triple": 3,
        }
        for manifests in by_launcher.values():
            for manifest in manifests:
                assert manifest.outcome == ParseOutcome.PARSED
                assert manifest.errors == []
        assert set(by_launcher["launcher_static"][0].tables) == {
            "total-dos",
            "projected-dos",
            "bandstructures",
            "charge-density",
            "valence-density",
            "local-potential",
            "electron-localization",
        }

    def test_the_files_have_the_schemas_and_encodings_of_their_tables(self, written):
        output, _ = written
        for table in output.iterdir():
            spec = PARSED_TABLES[table.name]
            expected = pa.schema(arrowize(spec.row_model))
            expected = pa.schema([expected.field(n) for n in spec.ordered_columns])
            options = spec.parquet_options
            for file in table.glob("*.parquet"):
                assert pq.read_schema(file).equals(expected, check_metadata=False)
                group = pq.ParquetFile(file).metadata.row_group(0)
                split = {
                    group.column(i).path_in_schema
                    for i in range(group.num_columns)
                    if "BYTE_STREAM_SPLIT" in group.column(i).encodings
                }
                assert split == set(options["use_byte_stream_split"]), table.name
        # the grids are among them, as are the bands
        for table, column in (
            ("charge-density", "total.list.element"),
            ("charge-density", "magnetization.list.element"),
            ("local-potential", "spin_up.list.element"),
            ("electron-localization", "elf_down.list.element"),
        ):
            group = pq.ParquetFile(
                next((output / table).glob("*.parquet"))
            ).metadata.row_group(0)
            encodings = {
                group.column(i).path_in_schema: group.column(i).encodings
                for i in range(group.num_columns)
            }
            assert "BYTE_STREAM_SPLIT" in encodings[column], (table, column)

    def test_the_magnetization_is_that_of_the_outcar(self, written):
        """What is read back from the file integrates to the total magnetization of the OUTCAR."""
        output, by_launcher = written
        (row,) = self.rows(output, "charge-density", "launcher_static", by_launcher)
        cells = row["grid_shape"][0] * row["grid_shape"][1] * row["grid_shape"][2]
        assert len(row["magnetization"]) == cells == 64**3
        assert sum(row["magnetization"]) / cells == pytest.approx(-6.9975, abs=1e-3)
        assert sum(row["total"]) / cells == pytest.approx(23.0, abs=1e-3)

    def test_the_spins_of_the_files_are_in_their_columns(self, written):
        """Up is up: what is in the file is pymatgen's block for each spin, which are not equal."""
        from emmet.core.io.pymatgen import Elfcar, Locpot, Vasprun, Spin

        output, by_launcher = written
        (potential,) = self.rows(
            output, "local-potential", "launcher_static", by_launcher
        )
        (elf,) = self.rows(
            output, "electron-localization", "launcher_static", by_launcher
        )
        assert potential["spin_mode"] == elf["spin_mode"] == "collinear"
        with DataArchive.extract(
            TEST_FILES_DIR / "vasp" / "magnetic_static_volumetric.json.gz"
        ) as d:
            locpot = Locpot.from_file(d / "LOCPOT.gz")
            elfcar = Elfcar.from_file(d / "ELFCAR.gz")
            vasprun = Vasprun(
                d / "vasprun.xml.gz",
                parse_potcar_file=False,
                parse_projected_eigen=False,
            )
        for column, spin in (("spin_up", "spin_up"), ("spin_down", "spin_down")):
            assert potential[column] == pytest.approx(
                locpot.data[spin].ravel().tolist(), rel=1e-6
            )
        for column, spin in (("elf_up", "spin_up"), ("elf_down", "spin_down")):
            assert elf[column] == pytest.approx(
                elfcar.data[spin].ravel().tolist(), rel=1e-6
            )
        assert (
            max(
                abs(u - d) for u, d in zip(potential["spin_up"], potential["spin_down"])
            )
            > 20
        )
        # and the density of states, which is up and down of the eigenvalues
        (dos,) = self.rows(output, "total-dos", "launcher_static", by_launcher)
        up = vasprun.complete_dos.densities[Spin.up]
        down = vasprun.complete_dos.densities[Spin.down]
        assert dos["density_up"] == pytest.approx(up.tolist(), rel=1e-5, abs=1e-6)
        assert dos["density_down"] == pytest.approx(down.tolist(), rel=1e-5, abs=1e-6)
        assert max(abs(u - d) for u, d in zip(up, down)) > 1.0

    def test_the_path_of_the_line(self, written):
        output, by_launcher = written
        (bands,) = self.rows(output, "bandstructures", "launcher_line", by_launcher)
        assert bands["path_convention"] == "setyawan_curtarolo"
        assert bands["shape"] == [64, 75]
        assert sum(label is not None for label in bands["kpoint_labels"]) == 12
        (trajectory,) = self.rows(output, "trajectories", "launcher_line", by_launcher)
        assert trajectory["magmoms"] == pytest.approx([0.114])

    def test_the_calculations_of_a_directory(self, written):
        output, by_launcher = written
        tasks = {
            t["calc_suffix"]: t
            for t in self.rows(output, "tasks", "launcher_triple", by_launcher)
        }
        assert sorted(tasks) == ["relax1", "relax2", "relax3"]
        assert len({t["dir_name"] for t in tasks.values()}) == 1
        # the original inputs are those of the first calculation
        assert tasks["relax1"]["orig_inputs"] is not None
        assert tasks["relax2"]["orig_inputs"] is None
        assert tasks["relax3"]["orig_inputs"] is None
        # a trajectory is told from the others by its identifier, which the manifest has
        # with the suffix: the trajectories table has no suffix of its own
        suffix_of = {
            m.identifier: m.calc_suffix for m in by_launcher["launcher_triple"]
        }
        steps = {
            suffix_of[t["identifier"]]: len(t["energy"])
            for t in self.rows(output, "trajectories", "launcher_triple", by_launcher)
        }
        assert steps == {"relax1": 3, "relax2": 1, "relax3": 60}
        # the moments of relax1 are those of each of its steps in the OUTCAR, which change
        by_suffix = {
            suffix_of[t["identifier"]]: t
            for t in self.rows(output, "trajectories", "launcher_triple", by_launcher)
        }
        assert by_suffix["relax1"]["total_magnetization"] == pytest.approx(
            [-0.2593305, -0.2607894, -0.2605008]
        )
        assert by_suffix["relax1"]["magmoms"][:7] == pytest.approx(
            [0.049, -0.044, -0.049, -0.044, -0.049, -0.044, -0.044]
        )
        assert by_suffix["relax1"]["magmoms"][7:14] == pytest.approx(
            [0.045, -0.044, -0.049, -0.044, -0.049, -0.044, -0.044]
        )


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
