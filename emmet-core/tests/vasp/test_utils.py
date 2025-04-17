"""Test VASP parsing utilities."""

from tempfile import TemporaryDirectory
from pathlib import Path

from emmet.core.vasp.utils import (
    recursive_discover_vasp_files,
    discover_and_sort_vasp_files,
    FileMeta,
)


def test_file_meta(tmp_dir):
    import hashlib
    from monty.io import zopen

    incar_bytes = """
ALGO = Normal
ENCUT = 500
EDIFF = 0.0001
IBRION = -1
""".encode()

    with zopen(file_name := "INCAR.bz2", "wb") as f:
        f.write(incar_bytes)

    file_meta = FileMeta(name="INCAR", path=file_name)
    assert Path(file_meta.path).exists()
    assert file_meta.md5 == hashlib.md5(incar_bytes).hexdigest()


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

        sorted_files = discover_and_sort_vasp_files(
            tmp_dir / "block_2025_02_30/launcher_2025_02_31/launcher_2025_02_31_0001"
        )

    assert set(sorted_files["contcar_file"]) == {"CONTCAR.relax1"}
    assert set(sorted_files["vasprun_file"]) == {"vasprun.xml.relax1"}
    assert set(sorted_files["outcar_file"]) == {"OUTCAR.relax1"}
    assert set(sorted_files["volumetric_files"]) == {"AECCAR0.bz2", "LOCPOT.gz"}
    assert set(sorted_files["elph_poscars"]) == {"POSCAR.T=300.gz", "POSCAR.T=1000.gz"}

    assert len(vasp_files) == len(
        directory_structure
    )  # should find all of the defined calculation directories
    for calc_dir, files in directory_structure.items():
        assert (base_path := tmp_dir / calc_dir) in vasp_files
        assert all(f in vasp_files[base_path] for f in files)

    # Should only find two valid calculation directories
    valid_calc_dirs = (
        "./neb_calc/01/",
        "block_2025_02_30/launcher_2025_02_31/launcher_2025_02_31_0001",
    )
    assert all(
        f in valid_vasp_files[tmp_dir / p]
        for p in valid_calc_dirs
        for f in directory_structure[p]
    )
