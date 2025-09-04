"""Test VASP parsing utilities."""

from tempfile import TemporaryDirectory
from pathlib import Path
import pytest

from emmet.core.vasp.utils import (
    recursive_discover_vasp_files,
    discover_and_sort_vasp_files,
    FileMetadata,
)


def test_file_meta(tmp_dir):
    import blake3

    incar_bytes = """
ALGO = Normal
ENCUT = 500
EDIFF = 0.0001
IBRION = -1
""".encode()

    with open(file_name := "INCAR.bz2", "wb") as f:
        f.write(incar_bytes)

    file_meta = FileMetadata(name="INCAR.bz2", path=file_name)
    file_meta.compute_hash()
    assert Path(file_meta.path).exists()
    assert file_meta.hash == blake3.blake3(incar_bytes).hexdigest()


def test_file_discovery():
    directory_structure = {
        "./neb_calc/00/": ["INCAR.gz", "KPOINTS", "POSCAR.gz"],
        "./neb_calc/01/": [
            "INCAR.gz",
            "CHGCAR",
            "CONTCAR.gz",
            "KPOINTS",
            "OUTCAR",
            "POSCAR.gz",
            "POTCAR.bz2",
            "vasprun.xml",
        ],
        "./neb_calc/02/": ["INCAR.gz", "KPOINTS", "POSCAR.gz"],
        "neb_calc": ["INCAR.gz", "KPOINTS", "POSCAR.gz", "POTCAR.lzma"],
        "block_2025_02_30/launcher_2025_02_31/launcher_2025_02_31_0001": [
            "AECCAR0.bz2",
            "LOCPOT.gz",
            "CONTCAR.relax1",
            "OUTCAR.relax1",
            "vasprun.xml.relax1",
            "POSCAR.T=300.gz",
            "POSCAR.T=1000.gz",
        ],
    }
    for idx in range(1, 3):
        directory_structure[
            "block_2025_02_30/launcher_2025_02_31/launcher_2025_02_31_0001"
        ].extend(
            [
                f"INCAR.relax{idx}",
                f"INCAR.orig.relax{idx}",
                f"POSCAR.relax{idx}",
                f"POSCAR.orig.relax{idx}",
                f"POTCAR.relax{idx}",
                f"POTCAR.orig.relax{idx}",
            ]
        )

    with TemporaryDirectory() as _tmp_dir:
        tmp_dir = Path(_tmp_dir).resolve()
        for calc_dir, files in directory_structure.items():
            p = tmp_dir / calc_dir
            if not p.exists():
                p.mkdir(parents=True, exist_ok=True)
            for f in files:
                (p / f).touch()
        vasp_files = recursive_discover_vasp_files(tmp_dir)
        valid_vasp_files = recursive_discover_vasp_files(tmp_dir, only_valid=True)

        assert len(recursive_discover_vasp_files(tmp_dir, max_depth=2)) == 4
        assert len(recursive_discover_vasp_files(tmp_dir, max_depth=1)) == 1

        files_by_calc_suffix = discover_and_sort_vasp_files(
            tmp_dir / "block_2025_02_30/launcher_2025_02_31/launcher_2025_02_31_0001"
        )

        for max_depth in (-1, 1.5):
            with pytest.raises(ValueError, match="non-negative integer"):
                _ = recursive_discover_vasp_files(tmp_dir, max_depth=max_depth)

    assert files_by_calc_suffix["relax1"]["contcar_file"].name == "CONTCAR.relax1"
    assert files_by_calc_suffix["relax1"]["vasprun_file"].name == "vasprun.xml.relax1"
    assert files_by_calc_suffix["relax1"]["outcar_file"].name == "OUTCAR.relax1"
    assert {b.name for b in files_by_calc_suffix["standard"]["volumetric_files"]} == {
        "AECCAR0.bz2",
        "LOCPOT.gz",
    }
    assert {b.name for b in files_by_calc_suffix["standard"]["elph_poscars"]} == {
        "POSCAR.T=300.gz",
        "POSCAR.T=1000.gz",
    }

    # should find all of the defined calculation directories + suffixes within those
    assert len(vasp_files) == 7

    found_files = set()
    ref_files = set()
    for calc_dir, files in directory_structure.items():
        ref_files.update({tmp_dir / calc_dir / file for file in files})
    for file_metas in vasp_files.values():
        found_files.update({file_meta.path for file_meta in file_metas})

    assert found_files == ref_files

    # Should only find two valid calculation directory / suffix pairs
    valid_calc_dirs = (
        "neb_calc/01/",
        "block_2025_02_30/launcher_2025_02_31/launcher_2025_02_31_0001",
    )

    assert len(valid_vasp_files) == 2
    found_valid_dirs = {calc_loc.path for calc_loc in valid_vasp_files}
    assert {tmp_dir / valid_dir for valid_dir in valid_calc_dirs} == found_valid_dirs
