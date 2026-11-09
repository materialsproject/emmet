import gzip
import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path

import h5py
import orjson
import pytest
from monty.io import zopen

from conftest import archive_metadata

from emmet.archival.utils import zpath
from emmet.archival.vasp.raw import RawArchive, raw_archive_hierarchy_from_files
from emmet.core.tasks import TaskDoc
from emmet.core.utils import get_hash_blocked
from emmet.core.vasp.utils import FileMetadata


def test_from_directory(tmp_dir, test_dir):
    vasp_files_dir = test_dir / "raw_vasp"
    archivers = RawArchive.from_directory(vasp_files_dir)
    assert len(archivers) == 1
    archivers[0].to_archive("archive.h5", archive_metadata())

    with h5py.File("archive.h5", "r") as f:
        for calc_type in f:
            for fname in f[calc_type]:
                if computed_md5 := f[calc_type][fname].attrs.get("md5"):
                    # the original name is relative, it does not reveal where the file was
                    original_name = f[calc_type][fname].attrs["original_name"]
                    assert not Path(original_name).is_absolute()
                    assert computed_md5 == get_hash_blocked(
                        vasp_files_dir / original_name
                    )
                    assert "file_path" not in f[calc_type][fname].attrs

                if "POTCAR" in fname:
                    potcar_data = orjson.loads(RawArchive._readout(f[calc_type], fname))
                    assert isinstance(potcar_data, list)
                    assert all(
                        isinstance(potcar_spec, dict)
                        and potcar_spec.get("summary_stats", {}).get("keywords")
                        and potcar_spec.get("summary_stats", {}).get("stats")
                        for potcar_spec in potcar_data
                    )

    raw_data = RawArchive.extract("archive.h5")
    for file_meta in raw_data:
        if "potcar" in file_meta.name.lower():
            fname = file_meta.name.split(".")[0]
        else:
            fname = file_meta.name

        orig_file = zpath(vasp_files_dir / fname)
        # check that original file exists
        assert orig_file.exists()

        # for non-POTCAR data, check that roundtrip returns the same data
        if not any(f in fname.lower() for f in ("potcar", ".h5")):
            with zopen(orig_file, "rt") as f_orig, zopen(file_meta.path, "rt") as f_new:
                assert f_orig.read() == f_new.read()

    # Test validation from RawArchive
    for valid_method in ("validate", "fast_validate"):
        valid_doc = getattr(RawArchive, valid_method)("archive.h5")
        assert not valid_doc.valid
        assert len(valid_doc.reasons) == 1
        assert any(
            "PSEUDOPOTENTIALS --> Incorrect POTCAR files" in r
            for r in valid_doc.reasons
        )
        assert valid_doc.vasp_files.run_type == "relax"
        assert valid_doc.vasp_files.functional == "r2scan"
        assert valid_doc.vasp_files.valid_input_set_name == "MP24RelaxSet"

    # Test round trip TaskDoc
    # Note that some fields (those with datetimes or with POTCAR info stripped)
    # will differ in resultant RawArchive
    expected_diff_keys = {
        "builder_meta",
        "dir_name",
        "calcs_reversed",
        "orig_inputs",
        "input",
        "last_updated",
        "completed_at",
        "entry",
    }
    orig_task_dict = TaskDoc.from_directory(test_dir / "raw_vasp").model_dump()
    extracted_task_dict = RawArchive.to_task_doc("archive.h5").model_dump()
    assert all(
        orig_task_dict[k] == extracted_task_dict[k]
        for k in set(TaskDoc.model_fields).difference(expected_diff_keys)
    )


def _make_files(directory: Path, contents: dict[str, bytes | str]) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    for name, data in contents.items():
        (directory / name).write_bytes(
            data if isinstance(data, bytes) else data.encode()
        )
    return directory


def _file_metas(directory: Path, names: list[str]) -> list[FileMetadata]:
    return [FileMetadata(name=n, path=directory / n) for n in names]


@pytest.mark.parametrize(
    "file_name, key",
    [
        ("INCAR", "input/INCAR"),
        ("INCAR.gz", "input/INCAR"),
        ("INCAR.orig", "input/INCAR.orig"),
        ("INCAR.orig.relax1.gz", "input/INCAR.orig"),
        # an uncompressed vasprun.xml used to be dropped
        ("vasprun.xml", "output/vasprun.xml"),
        ("vasprun.xml.relax1.gz", "output/vasprun.xml"),
        ("vaspout.h5", "output/vaspout.h5"),
        # raw POTCARs are archived as specs, and specs stay specs
        ("POTCAR", "input/POTCAR.spec"),
        ("POTCAR.orig.gz", "input/POTCAR.spec.orig"),
        ("POTCAR.spec", "input/POTCAR.spec"),
        ("POTCAR.spec.gz", "input/POTCAR.spec"),
        # PARCHG is not CHG, and its indices keep files apart
        ("PARCHG", "volumetric/PARCHG"),
        ("PARCHG.0001.0002.gz", "volumetric/PARCHG.0001.0002"),
        ("PARCHG.0001.ALLK", "volumetric/PARCHG.0001.ALLK"),
        ("PARCHG.ALLB.0002.relax1.gz", "volumetric/PARCHG.ALLB.0002"),
        ("CHG", "volumetric/CHG"),
        ("POT", "volumetric/POT"),
        ("POSCAR.T=300.gz", "input/POSCAR.T=300"),
        ("DOSCAR", "electronic_structure/DOSCAR"),
        ("custodian.json.gz", "workflow/custodian.json"),
    ],
)
def test_archive_keys(file_name, key):
    hierarchy = raw_archive_hierarchy_from_files(
        _file_metas(Path("/calc"), [file_name])
    )
    assert list(hierarchy) == [key]


def test_files_with_distinct_names_do_not_overwrite_each_other():
    names = [
        "PARCHG.0001.0002",
        "PARCHG.0001.0003",
        "PARCHG.0001.ALLK",
        "PARCHG.ALLB.0003",
        "POSCAR.T=300",
        "POSCAR.T=1000",
    ]
    hierarchy = raw_archive_hierarchy_from_files(_file_metas(Path("/calc"), names))
    assert len(hierarchy) == 6


class TestFileChecks:
    @pytest.mark.parametrize(
        "file_name, match",
        [
            ("vasprun.xml.relax10.gz", "'relax10'"),
            ("CHGCAR.bak", "'bak'"),
            ("my_vasprun.xml", "not a recognized VASP file"),
        ],
    )
    def test_unrecognized_names_raise(self, tmp_path, file_name, match):
        files = _make_files(tmp_path, {"INCAR": "x", file_name: "x"})
        with pytest.raises(ValueError, match=match):
            RawArchive.from_files(_file_metas(files, ["INCAR", file_name]))

    def test_key_collisions_raise(self, tmp_path):
        files = _make_files(
            tmp_path, {"vasprun.xml": "x", "vasprun.xml.gz": b"x", "INCAR": "x"}
        )
        with pytest.raises(ValueError, match="both output/vasprun.xml") as exc:
            RawArchive.from_files(
                _file_metas(files, ["vasprun.xml", "vasprun.xml.gz", "INCAR"])
            )
        assert "vasprun.xml.gz" in str(exc.value)

        # a raw POTCAR and a POTCAR spec are both the spec
        with pytest.raises(ValueError, match="input/POTCAR.spec"):
            raw_archive_hierarchy_from_files(
                _file_metas(files, ["POTCAR", "POTCAR.spec"])
            )

        # a suffixed and an unsuffixed file are the same file of the calculation
        with pytest.raises(ValueError, match="input/INCAR"):
            raw_archive_hierarchy_from_files(
                _file_metas(files, ["INCAR", "INCAR.relax1"]), calc_suffix="relax1"
            )

    def test_suffix_of_another_calculation_raises(self, tmp_path):
        files = _make_files(tmp_path, {"vasprun.xml.relax2.gz": b"x"})
        with pytest.raises(ValueError, match="'relax2'.*'relax1'"):
            RawArchive.from_files(
                _file_metas(files, ["vasprun.xml.relax2.gz"]), calc_suffix="relax1"
            )
        # files without a suffix are shared, and fine
        RawArchive.from_files(
            _file_metas(files, ["vasprun.xml.relax2.gz"]), calc_suffix="relax2"
        )
        hierarchy = raw_archive_hierarchy_from_files(
            _file_metas(Path("/calc"), ["POTCAR.spec", "INCAR.relax1"]),
            calc_suffix="relax1",
        )
        assert set(hierarchy) == {"input/POTCAR.spec", "input/INCAR"}

    def test_nothing_is_written_if_any_file_is_rejected(self, tmp_path, tmp_dir):
        files = _make_files(tmp_path, {"INCAR": "x", "OUTCAR.old": "x"})
        with pytest.raises(ValueError):
            RawArchive.from_files(
                _file_metas(files, ["INCAR", "OUTCAR.old"])
            ).to_archive("archive.h5", archive_metadata())
        assert not Path("archive.h5").exists()

    def test_custom_suffixes(self, tmp_path):
        files = _make_files(tmp_path, {"INCAR.nscf": "x", "vasprun.xml.nscf": "x"})
        names = ["INCAR.nscf", "vasprun.xml.nscf"]
        with pytest.raises(ValueError, match="'nscf'"):
            RawArchive.from_files(_file_metas(files, names), calc_suffix="nscf")

        archive = RawArchive.from_files(
            _file_metas(files, names), calc_suffix="nscf", suffixes=("nscf",)
        )
        assert set(archive.file_paths) == {"input/INCAR", "output/vasprun.xml"}


def _legacy_directory(root: Path) -> Path:
    spec = '[{"titel": "PAW_PBE Si 05Jan2001"}]'
    return _make_files(
        root,
        {
            "INCAR.relax1.gz": b"",  # empty files are skipped
            "INCAR.relax2": "ENCUT = 520",
            "INCAR.orig": "ENCUT = 400",
            "vasprun.xml.relax1": "<modeling>1</modeling>",
            "vasprun.xml.relax2": "<modeling>2</modeling>",
            "POTCAR.spec": spec,
            "custodian.json": "[]",
            "CHGCAR.relax2": "chg",
            "PARCHG.0001.0002": "p1",
            "PARCHG.0001.0003": "p2",
        },
    )


def test_one_archive_per_calculation(tmp_path):
    calc_dir = _legacy_directory(tmp_path)
    relax1, relax2 = RawArchive.from_directory(calc_dir)
    assert (relax1.calc_suffix, relax2.calc_suffix) == ("relax1", "relax2")

    # every calculation keeps its own vasprun, they no longer overwrite each other
    assert relax1.file_paths["output/vasprun.xml"].path.name == "vasprun.xml.relax1"
    assert relax2.file_paths["output/vasprun.xml"].path.name == "vasprun.xml.relax2"

    # shared files are in both, original inputs only in the first
    for archive in (relax1, relax2):
        assert "input/POTCAR.spec" in archive.file_paths
        assert "workflow/custodian.json" in archive.file_paths
    assert "input/INCAR.orig" in relax1.file_paths
    assert "input/INCAR.orig" not in relax2.file_paths
    # unsuffixed outputs and volumetric files are the last calculation's
    assert "volumetric/CHGCAR" in relax2.file_paths
    assert "volumetric/CHGCAR" not in relax1.file_paths
    assert {"volumetric/PARCHG.0001.0002", "volumetric/PARCHG.0001.0003"} <= set(
        relax2.file_paths
    )


def test_subdirectory_layout(tmp_path):
    _make_files(
        tmp_path / "relax1", {"vasprun.xml.gz": gzip.compress(b"x"), "INCAR": "a"}
    )
    _make_files(
        tmp_path / "relax2", {"vasprun.xml.gz": gzip.compress(b"y"), "INCAR": "b"}
    )
    _make_files(tmp_path, {"POTCAR.spec": "[]"})

    archives = RawArchive.from_directory(tmp_path)
    assert [a.calc_suffix for a in archives] == ["relax1", "relax2"]
    for archive in archives:
        archive.to_archive(f"{tmp_path}/{archive.calc_suffix}.h5", archive_metadata())
    with h5py.File(tmp_path / "relax1.h5") as f:
        assert f["output/vasprun.xml"].attrs["original_name"] == "relax1/vasprun.xml.gz"
        assert f["input/POTCAR.spec"].attrs["original_name"] == "POTCAR.spec"


def test_file_attributes_round_trip(tmp_path):
    calc_dir = _legacy_directory(tmp_path / "calc")
    relax2 = RawArchive.from_directory(calc_dir)[1]
    archive_name = str(tmp_path / "archive.h5")
    relax2.to_archive(archive_name, archive_metadata())

    with RawArchive._open_hdf5_like(archive_name, mode="r") as group:
        for key, file_meta in relax2.file_paths.items():
            attrs = group[key].attrs
            assert "file_path" not in attrs

            # the name is relative to the directory
            assert attrs["original_name"] == file_meta.path.name

            # the time is ISO-8601, in UTC
            mtime = datetime.fromisoformat(attrs["mtime"])
            assert mtime.utcoffset() == timedelta(0)
            assert mtime == datetime.fromtimestamp(
                file_meta.path.stat().st_mtime, tz=UTC
            )

            # the md5 is of the original file, and content_md5 of what is stored
            assert attrs["md5"] == get_hash_blocked(file_meta.path)
            stored = RawArchive._readout(group, key)
            assert attrs["content_md5"] == hashlib.md5(stored).hexdigest()
            assert stored == file_meta.path.read_bytes()


def test_content_md5_is_of_decompressed_data(tmp_path):
    original = b"ENCUT = 520\n" * 50
    path = tmp_path / "INCAR.gz"
    path.write_bytes(gzip.compress(original))
    archive_name = str(tmp_path / "archive.h5")
    RawArchive.from_files(
        _file_metas(tmp_path, ["INCAR.gz"]), root=tmp_path
    ).to_archive(archive_name, archive_metadata())
    with h5py.File(archive_name) as f:
        attrs = f["input/INCAR"].attrs
        assert attrs["original_name"] == "INCAR.gz"
        assert attrs["content_md5"] == hashlib.md5(original).hexdigest()
        # the md5 of the file on disk is of the compressed file
        assert attrs["md5"] == get_hash_blocked(path)
        assert attrs["md5"] != attrs["content_md5"]
