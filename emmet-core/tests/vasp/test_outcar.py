"""Test reading the magnetization of each ionic step from an OUTCAR."""

import gzip

import numpy as np
import pytest

from emmet.core.io.pymatgen import Outcar
from emmet.core.testing_utils import TEST_FILES_DIR, DataArchive
from emmet.core.vasp.outcar import StepMagnetization, read_step_magnetization

BLOCK = """
 magnetization (x)

# of ion       s       p       d       tot
------------------------------------------
    1        {a}   0.100   0.100   {a1}
    2        0.003   0.152   0.222   {b1}
------------------------------------------
tot          0.009   0.421   0.616   1.046

"""
STEP = """
 number of electron      {n} magnetization      {m}
 FREE ENERGIE OF THE ION-ELECTRON SYSTEM (eV)
"""


def write(tmp_path, text, name="OUTCAR"):
    path = tmp_path / name
    path.write_text(text)
    return path


def test_each_step_has_the_last_block_before_its_energies(tmp_path):
    text = (
        # the first step has two blocks: the last is its own
        BLOCK.format(a="0.001", a1="9.000", b1="9.000")
        + " number of electron      8.0000000 magnetization      0.1000000\n"
        + BLOCK.format(a="0.002", a1="0.292", b1="0.377")
        + STEP.format(n="8.0000000", m="0.6690000")
        + BLOCK.format(a="0.003", a1="0.392", b1="0.477")
        + STEP.format(n="8.0000000", m="0.8690000")
        # what follows the last step belongs to no step
        + BLOCK.format(a="0.004", a1="5.000", b1="5.000")
        + " number of electron      8.0000000 magnetization      7.0000000\n"
    )
    result = read_step_magnetization(write(tmp_path, text))

    assert result.num_ionic_steps == 2
    np.testing.assert_allclose(result.magmoms[0], [0.292, 0.377])
    np.testing.assert_allclose(result.magmoms[1], [0.392, 0.477])
    np.testing.assert_allclose(result.total[0], [0.669])
    np.testing.assert_allclose(result.total[1], [0.869])


def test_nothing_is_carried_from_one_step_to_the_next(tmp_path):
    """A step without moments has none, and not those of the step before it."""
    text = (
        BLOCK.format(a="0.001", a1="0.292", b1="0.377")
        + STEP.format(n="8.0", m="0.669")
        + STEP.format(n="8.0", m="")
    )
    result = read_step_magnetization(write(tmp_path, text))
    assert result.num_ionic_steps == 2
    assert result.magmoms[0] is not None and result.total[0] is not None
    assert result.magmoms[1] is None and result.total[1] is None


def test_no_moments_for_a_calculation_without_them(tmp_path):
    """No blocks are written without LORBIT, or without spin, but there are steps."""
    text = STEP.format(n="8.0000000", m="") + STEP.format(n="8.0000000", m="")
    result = read_step_magnetization(write(tmp_path, text))
    assert result.num_ionic_steps == 2
    assert result.magmoms == [None, None] and result.total == [None, None]


def test_noncollinear_moments_have_three_components(tmp_path):
    def block(component, values):
        rows = "\n".join(
            f"    {i + 1}   0.0   0.0   0.0   {v}" for i, v in enumerate(values)
        )
        return (
            f" magnetization ({component})\n\n# of ion       s       p       d       tot\n"
            f"-----\n{rows}\n-----\ntot  0.0  0.0  0.0  0.0\n\n"
        )

    text = (
        block("x", [1.0, 2.0])
        + block("y", [3.0, 4.0])
        + block("z", [5.0, 6.0])
        + " number of electron      8.0000000 magnetization      0.1  0.2  0.3\n"
        + " FREE ENERGIE OF THE ION-ELECTRON SYSTEM (eV)\n"
    )
    result = read_step_magnetization(write(tmp_path, text))
    np.testing.assert_allclose(result.magmoms[0], [[1.0, 3.0, 5.0], [2.0, 4.0, 6.0]])
    np.testing.assert_allclose(result.total[0], [0.1, 0.2, 0.3])


def test_incomplete_components_are_not_moments(tmp_path):
    text = BLOCK.format(a="0.001", a1="1.000", b1="1.000").replace(
        "(x)", "(y)"
    ) + STEP.format(n="8.0", m="0.0")
    assert read_step_magnetization(write(tmp_path, text)).magmoms == [None]


def test_numbers_which_run_into_each_other(tmp_path):
    """The columns of the OUTCAR have a fixed width, and large values have no space between."""
    text = BLOCK.format(a="0.001", a1="-10.292", b1="-10.377").replace(
        "0.100   0.100   -10.292", "0.100  -0.100-10.292"
    ) + STEP.format(n="8.0", m="0.5")
    result = read_step_magnetization(write(tmp_path, text))
    np.testing.assert_allclose(result.magmoms[0], [-10.292, -10.377])


ONE_SITE = """
 magnetization ({component})

# of ion       s       p       d       tot
------------------------------------------
    1        0.114  -0.001   0.000   {value}

 LATTICE
 7.046241000  0.000000000  0.000000000     0.141919642  0.000000000  0.000000000
 0.000000000  7.046241000  0.000000000     0.000000000  0.141919642  0.000000000

 total drift:                                0.000030      0.000041     -0.000012
"""


def test_a_block_of_one_atom_has_no_sum(tmp_path):
    """VASP only writes the sum of the atoms after the rows if there is more than one atom."""
    text = ONE_SITE.format(component="x", value="0.114") + STEP.format(n="7.0", m="1.0")
    result = read_step_magnetization(write(tmp_path, text))
    np.testing.assert_allclose(result.magmoms[0], [0.114])
    np.testing.assert_allclose(result.total[0], [1.0])


def test_noncollinear_blocks_of_one_atom(tmp_path):
    text = (
        ONE_SITE.format(component="x", value="1.0")
        + ONE_SITE.format(component="y", value="2.0")
        + ONE_SITE.format(component="z", value="3.0")
        + STEP.format(n="7.0", m="1.0  2.0  3.0")
    )
    result = read_step_magnetization(write(tmp_path, text))
    np.testing.assert_allclose(result.magmoms[0], [[1.0, 2.0, 3.0]])


def test_a_block_of_one_atom_at_the_end_of_the_file(tmp_path):
    """The block can be the last thing in the file, which is the case for the one after the last step."""
    text = (
        ONE_SITE.format(component="x", value="0.114")
        + STEP.format(n="7.0", m="1.0")
        + " magnetization (x)\n\n# of ion       s       p       d       tot\n"
        + "------------------------------------------\n    1   0.1  0.0  0.0  0.2\n"
    )
    result = read_step_magnetization(write(tmp_path, text))
    assert result.num_ionic_steps == 1
    np.testing.assert_allclose(result.magmoms[0], [0.114])


def test_a_block_ends_at_the_first_line_which_is_not_a_row(tmp_path):
    """Whatever follows the rows is not a moment, also a line which starts with a number."""
    text = (
        " magnetization (x)\n\n# of ion       s       p       d       tot\n"
        "------------------------------------------\n"
        "    1        0.114  -0.001   0.000   0.114\n"
        "    2        0.100   0.000   0.000   0.100\n"
        "7.046241000  0.000000000  0.000000000     0.141919642\n"
        "3 atoms and 2.5 volumes\n"
    ) + STEP.format(n="7.0", m="1.0")
    result = read_step_magnetization(write(tmp_path, text))
    np.testing.assert_allclose(result.magmoms[0], [0.114, 0.100])


def test_a_compressed_outcar(tmp_path):
    path = tmp_path / "OUTCAR.gz"
    with gzip.open(path, "wt") as file:
        file.write(
            BLOCK.format(a="0.001", a1="0.292", b1="0.377")
            + STEP.format(n="8", m="1.5")
        )
    assert read_step_magnetization(path).num_ionic_steps == 1


def test_an_empty_outcar(tmp_path):
    assert read_step_magnetization(write(tmp_path, "")) == StepMagnetization()


@pytest.mark.parametrize(
    "fixture, files",
    [
        ("r2scan_relax", ["OUTCAR.gz"]),
        ("magnetic_run", ["OUTCAR.gz"]),
        ("Si_old_double_relax", ["OUTCAR.relax1.gz", "OUTCAR.relax2.gz"]),
        ("Si_static", ["OUTCAR.gz"]),
    ],
)
def test_the_last_step_is_what_pymatgen_reads(fixture, files):
    """pymatgen reads the moments of the last step, and so does the last item here."""
    with DataArchive.extract(
        TEST_FILES_DIR / "vasp" / f"{fixture}.json.gz"
    ) as directory:
        for name in files:
            result = read_step_magnetization(directory / name)
            outcar = Outcar(directory / name)
            np.testing.assert_allclose(
                result.magmoms[-1], [site["tot"] for site in outcar.magnetization]
            )
            np.testing.assert_allclose(result.total[-1], [outcar.total_mag])
            # the OUTCAR has one set of moments more than it has ionic steps
            assert len(result.magmoms) == sum(
                "FREE ENERGIE OF THE ION-ELECTRON SYSTEM" in line
                for line in gzip.open(directory / name, "rt")
            )
