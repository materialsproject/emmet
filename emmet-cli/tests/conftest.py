import os
from pathlib import Path
from click.testing import CliRunner
from emmet.cli.submission import Submission
from emmet.cli.submit import submit
import pytest


@pytest.fixture(scope="session")
def tmp_dir(tmp_path_factory):
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
            "GARBAGE",
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
    tmp_dir = tmp_path_factory.mktemp("neb_test_dir")

    for calc_dir, files in directory_structure.items():
        p = tmp_dir / calc_dir
        if not p.exists():
            p.mkdir(parents=True, exist_ok=True)
        for f in files:
            (p / f).touch()

    return tmp_dir


@pytest.fixture(scope="session")
def sub_file(tmp_dir, tmp_path_factory):
    runner = CliRunner()
    result = runner.invoke(submit, ["create", str(tmp_dir)])

    matches = [word for word in result.output.split() if "submission-" in word]
    assert len(matches) == 1

    sub = Submission.load(Path(matches[0]))

    # clean up side-effect of calling create
    os.remove(matches[0])

    output_file = tmp_path_factory.mktemp("sub_test_dir") / "sub.json"
    sub.save(output_file)

    return str(output_file)
