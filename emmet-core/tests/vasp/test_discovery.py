"""Test the discovery of VASP calculations and their files in directories."""

from pathlib import Path

import pytest

from emmet.core.tasks import _find_vasp_files
from emmet.core.vasp.utils import (
    DEFAULT_CALC_SUFFIXES,
    CalculationFiles,
    CalculationLocator,
    check_vasp_file_name,
    discover_and_sort_vasp_files,
    discover_calculations,
    discover_vasp_files,
    parse_vasp_file_name,
    recursive_discover_calculations,
    recursive_discover_vasp_files,
)

MODERN_FILES = [
    "AECCAR0",
    "AECCAR1",
    "AECCAR2",
    "CHGCAR",
    "CONTCAR",
    "DOSCAR",
    "EIGENVAL",
    "INCAR",
    "INCAR.orig",
    "OSZICAR",
    "OUTCAR",
    "POSCAR",
    "POSCAR.orig",
    "POTCAR",
    "POTCAR.orig",
    "vasp.out",
    "vaspout.h5",
    "vasprun.xml",
]

# The files of a double-relax launcher from the legacy layout
LEGACY_FILES = [
    *[
        f"{name}.{suffix}.gz"
        for suffix in ("relax1", "relax2")
        for name in (
            "CHGCAR",
            "CHG",
            "CONTCAR",
            "DOSCAR",
            "EIGENVAL",
            "IBZKPT",
            "INCAR",
            "KPOINTS",
            "OSZICAR",
            "OUTCAR",
            "POSCAR",
            "PROCAR",
            "vasp.out",
            "vasprun.xml",
            "WAVECAR",
        )
    ],
    "custodian.json.gz",
    "FW_job-28702541.error.gz",
    "FW_job-28702541.out.gz",
    "FW.json.gz",
    "FW_submit.script.gz",
    "FW--ZrZnN2-elastic_structure_optimization.gz",
    "INCAR.orig.gz",
    "KPOINTS.orig.gz",
    "PCDAT.gz",
    "POSCAR.orig.gz",
    "POTCAR.gz",
    "POTCAR.orig.gz",
    "REPORT.gz",
    "std_err.txt.gz",
    "XDATCAR.gz",
]


def make_files(directory: Path, names: list[str]) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    for name in names:
        (directory / name).touch()
    return directory


def names(paths) -> set[str]:
    return {p.name for p in paths}


@pytest.mark.parametrize(
    "file_name, expected",
    [
        # (file type, category, calc suffix, is_orig)
        ("INCAR", ("INCAR", "input", None, False)),
        ("INCAR.gz", ("INCAR", "input", None, False)),
        ("INCAR.orig", ("INCAR", "input", None, True)),
        ("INCAR.orig.gz", ("INCAR", "input", None, True)),
        ("INCAR.relax1.gz", ("INCAR", "input", "relax1", False)),
        ("INCAR.orig.relax2", ("INCAR", "input", "relax2", True)),
        ("INCAR.relax2.orig", ("INCAR", "input", "relax2", True)),
        ("KPOINTS_OPT", ("KPOINTS_OPT", "input", None, False)),
        ("POTCAR", ("POTCAR", "input", None, False)),
        ("POTCAR.spec", ("POTCAR.spec", "input", None, False)),
        ("POTCAR.spec.relax1", ("POTCAR.spec", "input", "relax1", False)),
        ("POTCAR.bz2", ("POTCAR", "input", None, False)),
        ("vasprun.xml", ("vasprun.xml", "output", None, False)),
        ("vasprun.xml.gz", ("vasprun.xml", "output", None, False)),
        ("vasprun.xml.relax1.gz", ("vasprun.xml", "output", "relax1", False)),
        ("vasprun.xml.static", ("vasprun.xml", "output", "static", False)),
        ("vaspout.h5", ("vaspout.h5", "output", None, False)),
        ("OUTCAR.precondition", ("OUTCAR", "output", "precondition", False)),
        ("XDATCAR.gz", ("XDATCAR", "output", None, False)),
        ("DOSCAR.relax1.gz", ("DOSCAR", "electronic_structure", "relax1", False)),
        ("EIGENVAL", ("EIGENVAL", "electronic_structure", None, False)),
        ("CHGCAR", ("CHGCAR", "volumetric", None, False)),
        ("CHGCAR.relax1.gz", ("CHGCAR", "volumetric", "relax1", False)),
        ("CHG.relax2.gz", ("CHG", "volumetric", "relax2", False)),
        ("PARCHG", ("PARCHG", "volumetric", None, False)),
        ("PARCHG.0001.0002", ("PARCHG", "volumetric", None, False)),
        ("AECCAR0.bz2", ("AECCAR0", "volumetric", None, False)),
        ("LOCPOT", ("LOCPOT", "volumetric", None, False)),
        ("ELFCAR.gz", ("ELFCAR", "volumetric", None, False)),
        ("POT", ("POT", "volumetric", None, False)),
        ("POSCAR.T=300.gz", ("POSCAR.T", "input", None, False)),
        ("custodian.json.gz", ("custodian.json", "workflow", None, False)),
        ("FW.json", ("FW.json", "workflow", None, False)),
        ("transformations.json.gz", ("transformations.json", "workflow", None, False)),
    ],
)
def test_parse_vasp_file_name(file_name, expected):
    parsed = parse_vasp_file_name(file_name)
    assert parsed is not None
    assert tuple(parsed)[:4] == expected
    assert parsed.unrecognized == ()
    # parent directories are ignored
    assert parse_vasp_file_name(f"/some/dir/{file_name}") == parsed


@pytest.mark.parametrize(
    "file_name",
    [
        "vasp.out",
        "vasp.out.relax1.gz",
        "WAVECAR",
        "WAVECAR.relax1.gz",
        "std_err.txt.gz",
        "FW_job-28702541.error.gz",
        "FW_submit.script.gz",
        "FW--ZrZnN2-elastic_structure_optimization.gz",
        # names which only contain the name of a VASP file
        "my_vasprun.xml",
        "CHGCAR_backup",
        "OLD_INCAR",
        "POTCAR_copy",
        "vasprun.json",
        "README",
    ],
)
def test_parse_vasp_file_name_not_vasp_file(file_name):
    assert parse_vasp_file_name(file_name) is None


def test_parse_vasp_file_name_suffixes():
    # unknown suffixes are reported, or can be configured
    parsed = parse_vasp_file_name("vasprun.xml.mine")
    assert parsed.calc_suffix is None
    assert parsed.unrecognized == ("mine",)

    parsed = parse_vasp_file_name("vasprun.xml.mine", ("mine",))
    assert parsed.calc_suffix == "mine"
    assert parsed.unrecognized == ()

    parsed = parse_vasp_file_name("vasprun.xml.relax1", ("mine",))
    assert parsed.calc_suffix is None
    assert parsed.unrecognized == ("relax1",)

    # other parts of the name are reported too
    assert parse_vasp_file_name("INCAR.bak").unrecognized == ("bak",)
    assert parse_vasp_file_name("CHGCAR.relax1.old.gz").unrecognized == ("old",)
    # but are understood in the names of some files
    assert parse_vasp_file_name("PARCHG.0001.0002").unrecognized == ()
    assert parse_vasp_file_name("CHGCAR.0001").unrecognized == ("0001",)


def test_unrecognized_files_are_not_taken_to_be_standard(tmp_path):
    """A file with an unknown suffix must not be merged with unsuffixed files."""
    make_files(tmp_path, ["vasprun.xml", "OUTCAR", "OUTCAR.bak", "vasprun.xml.relax10"])
    (calc,) = discover_calculations(tmp_path).values()
    assert calc.calc_suffix == "standard"
    assert calc.vasprun.name == "vasprun.xml"
    assert calc.outcar.name == "OUTCAR"

    # unless the suffix is configured
    calcs = discover_calculations(tmp_path, ("relax10",))
    assert [loc.modifier for loc in calcs] == ["relax10", "standard"]


def test_default_suffixes():
    assert DEFAULT_CALC_SUFFIXES == (
        "precondition",
        *(f"relax{i}" for i in range(1, 10)),
        "static",
    )


def test_modern_layout(tmp_path):
    make_files(tmp_path, MODERN_FILES)

    calcs = discover_calculations(tmp_path)
    assert list(calcs) == [CalculationLocator(path=tmp_path, modifier="standard")]
    files = next(iter(calcs.values()))

    assert isinstance(files, CalculationFiles)
    assert files.calc_suffix == "standard"
    assert files.directory == tmp_path.resolve()
    assert files.is_first and files.is_last

    assert files.vasprun.name == "vasprun.xml"
    assert files.outcar.name == "OUTCAR"
    assert files.contcar.name == "CONTCAR"
    assert files.oszicar.name == "OSZICAR"
    assert "vaspout.h5" in files.outputs
    assert set(files.volumetric) == {"AECCAR0", "AECCAR1", "AECCAR2", "CHGCAR"}
    assert set(files.electronic_structure) == {"DOSCAR", "EIGENVAL"}
    assert set(files.inputs) == {"INCAR", "POSCAR", "POTCAR"}
    # a calculation with no suffix is the first calculation, and has .orig inputs
    assert set(files.orig_inputs) == {"INCAR", "POSCAR", "POTCAR"}
    assert files.orig_inputs["INCAR"].name == "INCAR.orig"
    assert files.workflow == {}

    # unrecognized files, e.g., vasp.out, are not included
    all_names = names(
        [
            *files.inputs.values(),
            *files.orig_inputs.values(),
            *files.outputs.values(),
            *files.volumetric.values(),
            *files.electronic_structure.values(),
        ]
    )
    assert "vasp.out" not in all_names


def test_legacy_layout(tmp_path):
    make_files(tmp_path, LEGACY_FILES)

    calcs = discover_calculations(tmp_path)
    assert [loc.modifier for loc in calcs] == ["relax1", "relax2"]
    assert {loc.path for loc in calcs} == {tmp_path.resolve()}
    relax1, relax2 = calcs.values()

    assert (relax1.is_first, relax1.is_last) == (True, False)
    assert (relax2.is_first, relax2.is_last) == (False, True)

    for files, suffix in ((relax1, "relax1"), (relax2, "relax2")):
        assert files.calc_suffix == suffix
        assert files.vasprun.name == f"vasprun.xml.{suffix}.gz"
        assert files.outcar.name == f"OUTCAR.{suffix}.gz"
        assert files.contcar.name == f"CONTCAR.{suffix}.gz"
        assert files.oszicar.name == f"OSZICAR.{suffix}.gz"
        assert names(files.volumetric.values()) == {
            f"CHGCAR.{suffix}.gz",
            f"CHG.{suffix}.gz",
        }
        assert names(files.electronic_structure.values()) == {
            f"DOSCAR.{suffix}.gz",
            f"EIGENVAL.{suffix}.gz",
        }
        assert files.inputs["INCAR"].name == f"INCAR.{suffix}.gz"
        assert files.inputs["KPOINTS"].name == f"KPOINTS.{suffix}.gz"

        # shared, unsuffixed files: the POTCAR goes to every calculation
        assert files.inputs["POTCAR"].name == "POTCAR.gz"
        # and workflow files, which describe the whole directory
        assert set(files.workflow) == {"custodian.json", "FW.json"}

    # the original inputs describe the first calculation only
    assert names(relax1.orig_inputs.values()) == {
        "INCAR.orig.gz",
        "KPOINTS.orig.gz",
        "POSCAR.orig.gz",
        "POTCAR.orig.gz",
    }
    assert relax2.orig_inputs == {}

    # unsuffixed output files go to the last calculation
    assert names(relax2.outputs.values()) >= {
        "PCDAT.gz",
        "REPORT.gz",
        "XDATCAR.gz",
    }
    assert not names(relax1.outputs.values()) & {"PCDAT.gz", "REPORT.gz", "XDATCAR.gz"}

    # unrecognized files do not appear anywhere
    found = set()
    for files in calcs.values():
        for group in (
            files.inputs,
            files.orig_inputs,
            files.outputs,
            files.volumetric,
            files.electronic_structure,
            files.workflow,
        ):
            found |= names(group.values())
    assert not found & {
        "FW_job-28702541.error.gz",
        "FW_submit.script.gz",
        "std_err.txt.gz",
        "vasp.out.relax1.gz",
        "WAVECAR.relax1.gz",
    }


def test_unsuffixed_volumetric_files_go_to_last_calculation(tmp_path):
    make_files(
        tmp_path,
        [
            "vasprun.xml.relax1",
            "vasprun.xml.relax2",
            "CHGCAR",
            "LOCPOT.gz",
            "CHGCAR.relax1",
            "POSCAR.T=300.gz",
        ],
    )
    relax1, relax2 = discover_calculations(tmp_path).values()

    # relax1 has its own CHGCAR, which the unsuffixed one doesn't replace
    assert names(relax1.volumetric.values()) == {"CHGCAR.relax1"}
    assert names(relax2.volumetric.values()) == {"CHGCAR", "LOCPOT.gz"}
    assert relax1.elph_poscars == []
    assert names(relax2.elph_poscars) == {"POSCAR.T=300.gz"}


def test_explicit_orig_inputs_stay_with_their_calculation(tmp_path):
    make_files(
        tmp_path,
        [
            "vasprun.xml.relax1",
            "vasprun.xml.relax2",
            "INCAR.orig",
            "INCAR.orig.relax2",
            "POSCAR.orig",
        ],
    )
    relax1, relax2 = discover_calculations(tmp_path).values()

    assert names(relax1.orig_inputs.values()) == {"INCAR.orig", "POSCAR.orig"}
    # a suffixed .orig file was explicitly made for that calculation
    assert names(relax2.orig_inputs.values()) == {"INCAR.orig.relax2"}


def test_static_suffix(tmp_path):
    make_files(
        tmp_path,
        [
            "vasprun.xml.relax1",
            "vasprun.xml.relax2",
            "vasprun.xml.static",
            "INCAR.orig",
            "XDATCAR",
        ],
    )
    calcs = discover_calculations(tmp_path)
    assert [loc.modifier for loc in calcs] == ["relax1", "relax2", "static"]
    assert [f.is_last for f in calcs.values()] == [False, False, True]
    assert (
        "XDATCAR" in calcs[CalculationLocator(path=tmp_path, modifier="static")].outputs
    )
    assert "INCAR" in next(iter(calcs.values())).orig_inputs


def test_suffix_order_is_the_order_of_the_caller(tmp_path):
    make_files(
        tmp_path,
        [
            "vasprun.xml.a",
            "vasprun.xml.b",
            "vasprun.xml.c",
            "INCAR.orig",
            "XDATCAR",
        ],
    )

    def modifiers(*suffixes):
        return [loc.modifier for loc in discover_calculations(tmp_path, suffixes)]

    # the default suffixes are not found in these names
    assert modifiers() == []
    assert modifiers("a", "b", "c") == ["a", "b", "c"]
    # not alphabetical
    assert modifiers("c", "a", "b") == ["c", "a", "b"]

    calcs = discover_calculations(tmp_path, ("c", "a", "b"))
    first, _, last = calcs.values()
    assert first.calc_suffix == "c" and "INCAR" in first.orig_inputs
    assert last.calc_suffix == "b" and "XDATCAR" in last.outputs

    # suffixes which are not present are skipped, and "standard" is implicit
    assert modifiers("x", "b", "standard", "a") == ["b", "a"]


def test_subdirectory_layout(tmp_path):
    make_files(
        tmp_path / "relax1", ["INCAR.gz", "vasprun.xml.gz", "OUTCAR.gz", "CHGCAR.gz"]
    )
    make_files(
        tmp_path / "relax2",
        ["INCAR.gz", "vasprun.xml.gz", "OUTCAR.gz", "CONTCAR.gz", "INCAR.orig.gz"],
    )
    make_files(tmp_path, ["POTCAR.spec", "custodian.json.gz", "INCAR.orig"])
    # not calculations
    make_files(tmp_path / "scratch", ["vasprun.xml"])
    make_files(tmp_path / "relax3", ["INCAR"])

    calcs = discover_calculations(tmp_path)
    assert [loc.modifier for loc in calcs] == ["relax1", "relax2"]
    # a calculation in a subdirectory is located by the directory with its siblings
    assert {loc.path for loc in calcs} == {tmp_path.resolve()}

    relax1, relax2 = calcs.values()
    assert relax1.directory == (tmp_path / "relax1").resolve()
    assert relax2.directory == (tmp_path / "relax2").resolve()

    # files in the subdirectory belong to the calculation, and have no suffix
    assert relax1.vasprun.parent == relax1.directory
    assert relax1.vasprun.name == "vasprun.xml.gz"
    assert names(relax1.volumetric.values()) == {"CHGCAR.gz"}
    assert relax2.contcar.name == "CONTCAR.gz"
    assert relax2.volumetric == {}

    # shared files come from the parent directory
    assert (
        relax1.potcar_spec == relax2.potcar_spec == (tmp_path / "POTCAR.spec").resolve()
    )
    assert set(relax1.workflow) == set(relax2.workflow) == {"custodian.json"}
    assert names(relax1.orig_inputs.values()) == {"INCAR.orig"}
    assert names(relax2.orig_inputs.values()) == {"INCAR.orig.gz"}


def test_files_with_a_suffix_take_priority_over_subdirectories(tmp_path):
    make_files(tmp_path, ["vasprun.xml.relax1", "INCAR.relax1"])
    make_files(tmp_path / "relax1", ["vasprun.xml"])
    (calc,) = discover_calculations(tmp_path).values()
    assert calc.vasprun == (tmp_path / "vasprun.xml.relax1").resolve()
    assert calc.directory == tmp_path.resolve()


def test_calculations_need_a_vasprun(tmp_path):
    assert discover_calculations(tmp_path) == {}

    make_files(tmp_path, ["INCAR", "POSCAR", "POTCAR", "OUTCAR"])
    assert discover_calculations(tmp_path) == {}

    make_files(tmp_path, ["vasprun.xml.relax2", "INCAR.relax1", "OUTCAR.relax1"])
    calcs = discover_calculations(tmp_path)
    assert [loc.modifier for loc in calcs] == ["relax2"]
    # the shared files are given to the only calculation
    (calc,) = calcs.values()
    assert calc.is_first and calc.is_last
    assert "OUTCAR" in calc.outputs


def test_unsuffixed_calculation_with_suffixed_ones(tmp_path):
    """A final calculation with no suffix is last, and has its own files."""
    make_files(
        tmp_path,
        [
            "vasprun.xml.relax1",
            "vasprun.xml",
            "OUTCAR",
            "POTCAR",
            "INCAR.orig",
            "custodian.json",
        ],
    )
    calcs = discover_calculations(tmp_path)
    assert [loc.modifier for loc in calcs] == ["relax1", "standard"]
    relax1, standard = calcs.values()
    assert relax1.outcar is None
    assert standard.outcar.name == "OUTCAR"
    assert relax1.inputs["POTCAR"].name == standard.inputs["POTCAR"].name == "POTCAR"
    # .orig inputs describe the first calculation, and not the last
    assert "INCAR" in relax1.orig_inputs
    assert standard.orig_inputs == {}
    assert "custodian.json" in relax1.workflow and "custodian.json" in standard.workflow


def test_calculation_kwargs(tmp_path):
    make_files(tmp_path, [*MODERN_FILES, "POTCAR.spec", "POSCAR.T=300.gz"])
    (files,) = discover_calculations(tmp_path).values()

    kwargs = files.to_calculation_kwargs()
    assert set(kwargs) == {
        "vasprun_file",
        "outcar_file",
        "contcar_file",
        "oszicar_file",
        "potcar_spec_file",
        "volumetric_files",
        "elph_poscars",
    }
    assert kwargs["vasprun_file"] == (tmp_path / "vasprun.xml").resolve()
    assert names(kwargs["volumetric_files"]) == {
        "AECCAR0",
        "AECCAR1",
        "AECCAR2",
        "CHGCAR",
    }
    assert names(kwargs["elph_poscars"]) == {"POSCAR.T=300.gz"}

    # only the files which exist are included
    (sparse,) = discover_calculations(
        make_files(tmp_path / "s", ["vasprun.xml"])
    ).values()
    assert set(sparse.to_calculation_kwargs()) == {"vasprun_file"}


def test_symlinks_are_resolved_only_when_asked(tmp_path):
    target = make_files(tmp_path / "target", ["vasprun.xml"])
    link_dir = tmp_path / "link"
    link_dir.mkdir()
    (link_dir / "vasprun.xml").symlink_to(target / "vasprun.xml")

    (files,) = discover_calculations(link_dir).values()
    # discovery keeps the path of the link, with the name of the file as it is in the directory
    assert files.vasprun == link_dir.resolve() / "vasprun.xml"
    assert files.vasprun.is_symlink()
    assert (
        files.to_calculation_kwargs()["vasprun_file"]
        == (target / "vasprun.xml").resolve()
    )
    assert files.to_calculation_kwargs(resolve=False)["vasprun_file"].is_symlink()


class TestCompatibility:
    def test_find_vasp_files(self, tmp_path):
        make_files(tmp_path, LEGACY_FILES)
        task_files = _find_vasp_files(tmp_path)
        assert list(task_files) == ["relax1", "relax2"]
        assert (
            task_files["relax1"]["vasprun_file"]
            == (tmp_path / "vasprun.xml.relax1.gz").resolve()
        )
        assert set(task_files["relax1"]) == {
            "vasprun_file",
            "outcar_file",
            "contcar_file",
            "oszicar_file",
            "volumetric_files",
        }

    def test_find_vasp_files_task_names(self, tmp_path):
        make_files(tmp_path, ["vasprun.xml.a", "vasprun.xml.b", "vasprun.xml.relax1"])
        assert list(_find_vasp_files(tmp_path, task_names=["b", "a"])) == ["b", "a"]
        assert list(_find_vasp_files(tmp_path, task_names=("relax1",))) == ["relax1"]

    def test_find_vasp_files_subdirectories(self, tmp_path):
        """Files in subdirectories are assigned to their own calculations."""
        make_files(tmp_path / "relax1", ["vasprun.xml.gz", "OUTCAR.gz", "CONTCAR.gz"])
        make_files(tmp_path / "relax2", ["vasprun.xml.gz", "OUTCAR.gz", "CONTCAR.gz"])
        make_files(tmp_path, ["POTCAR.spec"])

        task_files = _find_vasp_files(tmp_path)
        assert list(task_files) == ["relax1", "relax2"]
        assert task_files["relax1"]["vasprun_file"].parent.name == "relax1"
        assert task_files["relax2"]["vasprun_file"].parent.name == "relax2"
        assert all("potcar_spec_file" in files for files in task_files.values())

    def test_find_vasp_files_static_suffix(self, tmp_path):
        make_files(tmp_path, ["vasprun.xml.relax2", "vasprun.xml.static"])
        assert list(_find_vasp_files(tmp_path)) == ["relax2", "static"]

    def test_discover_vasp_files_names(self, tmp_path):
        make_files(
            tmp_path,
            ["PARCHG", "CHG.relax1", "POTCAR", "POT", "my_vasprun.xml", "vasprun.xml"],
        )
        found = discover_vasp_files(tmp_path)
        assert names(f.path for fs in found.values() for f in fs) == {
            "PARCHG",
            "CHG.relax1",
            "POTCAR",
            "POT",
            "vasprun.xml",
        }

    def test_discover_and_sort_vasp_files(self, tmp_path):
        make_files(
            tmp_path,
            [
                "PARCHG",
                "POTCAR.spec",
                "POTCAR.spec.orig",
                "POTCAR",
                "POT",
                "vasprun.xml",
                "CONTCAR.relax1",
            ],
        )
        sorted_files = discover_and_sort_vasp_files(tmp_path)
        standard = sorted_files["standard"]
        assert standard["vasprun_file"].name == "vasprun.xml"
        # original files are not taken to be the spec, and a POTCAR is not a volumetric file
        assert standard["potcar_spec_file"].name == "POTCAR.spec"
        assert names(standard["volumetric_files"]) == {"PARCHG", "POT"}
        assert sorted_files["relax1"]["contcar_file"].name == "CONTCAR.relax1"

    def test_recursive_discovery(self, tmp_path):
        make_files(
            tmp_path / "launcher_1", ["INCAR", "vasprun.xml", "PARCHG", "POTCAR"]
        )
        make_files(tmp_path / "launcher_2", LEGACY_FILES)
        calcs = recursive_discover_vasp_files(tmp_path)
        assert {(loc.path.name, loc.modifier) for loc in calcs} == {
            ("launcher_1", "standard"),
            ("launcher_2", "standard"),
            ("launcher_2", "relax1"),
            ("launcher_2", "relax2"),
        }
        launcher_1 = next(
            files for loc, files in calcs.items() if loc.path.name == "launcher_1"
        )
        assert names(f.path for f in launcher_1) == {
            "INCAR",
            "vasprun.xml",
            "PARCHG",
            "POTCAR",
        }


class TestCheckVaspFileName:
    @pytest.mark.parametrize(
        "file_name, file_type, calc_suffix",
        [
            ("INCAR", "INCAR", None),
            ("vasprun.xml.relax1.gz", "vasprun.xml", "relax1"),
            ("/some/dir/INCAR.orig.static", "INCAR", "static"),
            ("PARCHG.0001.0002", "PARCHG", None),
        ],
    )
    def test_accepted(self, file_name, file_type, calc_suffix):
        parsed = check_vasp_file_name(file_name)
        assert parsed.file_type == file_type
        assert parsed.calc_suffix == calc_suffix

    @pytest.mark.parametrize(
        "file_name, part",
        [
            ("vasprun.xml.relax10.gz", "relax10"),
            ("CHGCAR.bak.gz", "bak"),
            ("OUTCAR.old", "old"),
        ],
    )
    def test_unrecognized_parts(self, file_name, part):
        with pytest.raises(ValueError, match=f"'{part}'") as exc:
            check_vasp_file_name(file_name)
        # the message says what to do about it
        assert file_name in str(exc.value)
        assert "Rename the file, or leave it out" in str(exc.value)

    def test_not_a_vasp_file(self):
        with pytest.raises(ValueError, match="not a recognized VASP file"):
            check_vasp_file_name("my_vasprun.xml")

    def test_custom_suffixes(self):
        with pytest.raises(ValueError, match="'nscf'"):
            check_vasp_file_name("INCAR.nscf")
        assert check_vasp_file_name("INCAR.nscf", ("nscf",)).calc_suffix == "nscf"
        # the default suffixes are no longer allowed
        with pytest.raises(ValueError, match="'relax1'"):
            check_vasp_file_name("INCAR.relax1", ("nscf",))


class TestFilePaths:
    def test_all_files_of_a_calculation(self, tmp_path):
        make_files(tmp_path, LEGACY_FILES)
        relax1, relax2 = discover_calculations(tmp_path).values()
        paths_1, paths_2 = relax1.file_paths(), relax2.file_paths()

        for paths in (paths_1, paths_2):
            assert len(paths) == len(set(paths))
        # own files
        assert (tmp_path / "vasprun.xml.relax1.gz").resolve() in paths_1
        assert (tmp_path / "vasprun.xml.relax1.gz").resolve() not in paths_2
        # shared files are in every calculation, orig inputs only in the first
        shared = (tmp_path / "POTCAR.gz").resolve()
        assert shared in paths_1 and shared in paths_2
        orig = (tmp_path / "INCAR.orig.gz").resolve()
        assert orig in paths_1 and orig not in paths_2
        assert (tmp_path / "custodian.json.gz").resolve() in paths_1 + paths_2

    def test_all_parchg_files_are_kept(self, tmp_path):
        parchgs = ["PARCHG.0001.0002", "PARCHG.0001.0003", "PARCHG.0002.0001"]
        make_files(tmp_path, ["vasprun.xml", "INCAR", *parchgs])
        (calc,) = discover_calculations(tmp_path).values()
        assert names(calc.file_paths()) >= set(parchgs)
        assert len(calc.extra_parchg) == 2
        # the parser still gets one
        assert list(calc.volumetric) == ["PARCHG"]

    def test_parchg_files_are_shared_with_the_last_calculation(self, tmp_path):
        parchgs = ["PARCHG.0001.0002", "PARCHG.0001.0003"]
        make_files(
            tmp_path, ["vasprun.xml.relax1", "vasprun.xml.relax2", "INCAR.relax1"]
        )
        make_files(tmp_path, parchgs)
        relax1, relax2 = discover_calculations(tmp_path).values()
        assert names(relax2.file_paths()) >= set(parchgs)
        assert not names(relax1.file_paths()) & set(parchgs)


class TestRecursiveDiscoverCalculations:
    def test_layouts(self, tmp_path):
        make_files(tmp_path / "launcher_1", ["INCAR", "vasprun.xml", "POTCAR"])
        make_files(tmp_path / "launcher_2", LEGACY_FILES)
        make_files(tmp_path / "launcher_3" / "relax1", ["vasprun.xml.gz", "INCAR"])
        make_files(tmp_path / "launcher_3" / "relax2", ["vasprun.xml.gz", "INCAR"])
        calcs = recursive_discover_calculations(tmp_path)
        assert {(loc.path.name, loc.modifier) for loc in calcs} == {
            ("launcher_1", "standard"),
            ("launcher_2", "relax1"),
            ("launcher_2", "relax2"),
            ("launcher_3", "relax1"),
            ("launcher_3", "relax2"),
        }

    def test_suffix_subdirectories_are_not_launchers(self, tmp_path):
        make_files(tmp_path / "launcher" / "relax1", ["vasprun.xml.gz", "INCAR"])
        make_files(tmp_path / "launcher" / "relax2", ["vasprun.xml.gz", "INCAR"])
        calcs = recursive_discover_calculations(tmp_path)
        assert {loc.path for loc in calcs} == {(tmp_path / "launcher").resolve()}
        assert len(calcs) == 2

    def test_nested_directories_of_a_calculation_are_searched(self, tmp_path):
        make_files(tmp_path / "neb", ["INCAR", "vasprun.xml"])
        make_files(tmp_path / "neb" / "01", ["INCAR", "vasprun.xml"])
        calcs = recursive_discover_calculations(tmp_path)
        assert {
            loc.path.relative_to(tmp_path.resolve()).as_posix() for loc in calcs
        } == {
            "neb",
            "neb/01",
        }

    def test_max_depth(self, tmp_path):
        make_files(tmp_path, ["INCAR", "vasprun.xml"])
        make_files(tmp_path / "a", ["INCAR", "vasprun.xml"])
        make_files(tmp_path / "a" / "b", ["INCAR", "vasprun.xml"])
        assert len(recursive_discover_calculations(tmp_path, max_depth=0)) == 1
        assert len(recursive_discover_calculations(tmp_path, max_depth=1)) == 2
        assert len(recursive_discover_calculations(tmp_path)) == 3
        with pytest.raises(ValueError, match="non-negative"):
            recursive_discover_calculations(tmp_path, max_depth=-1)

    def test_require_vasprun(self, tmp_path):
        # not run yet: inputs only
        make_files(tmp_path / "inputs_only", ["INCAR", "KPOINTS", "POSCAR", "POTCAR"])
        # a double relax which only ran once
        make_files(
            tmp_path / "legacy",
            ["INCAR.relax1", "vasprun.xml.relax1", "INCAR.relax2", "POTCAR"],
        )
        # only workflow files
        make_files(tmp_path / "other", ["custodian.json", "FW.json"])

        strict = recursive_discover_calculations(tmp_path)
        assert {(loc.path.name, loc.modifier) for loc in strict} == {
            ("legacy", "relax1")
        }

        lenient = recursive_discover_calculations(tmp_path, require_vasprun=False)
        assert {(loc.path.name, loc.modifier) for loc in lenient} == {
            ("inputs_only", "standard"),
            ("legacy", "relax1"),
            ("legacy", "relax2"),
        }

    def test_unsuffixed_files_are_shared_with_suffixed_calculations(self, tmp_path):
        make_files(
            tmp_path,
            ["INCAR.relax1", "INCAR.relax2", "LOCPOT", "POTCAR", "CONTCAR.relax2"],
        )
        calcs = discover_calculations(tmp_path, require_vasprun=False)
        assert [loc.modifier for loc in calcs] == ["relax1", "relax2"]
        relax1, relax2 = calcs.values()
        assert "LOCPOT" in relax2.volumetric and "LOCPOT" not in relax1.volumetric
        assert "POTCAR" in relax1.inputs and "POTCAR" in relax2.inputs

    def test_symlinked_directories_are_not_followed(self, tmp_path):
        make_files(tmp_path / "real", ["INCAR", "vasprun.xml"])
        (tmp_path / "link").symlink_to(tmp_path / "real", target_is_directory=True)
        assert len(recursive_discover_calculations(tmp_path)) == 1
