"""Test the parsing of calculations of real VASP runs, each chosen for something in particular."""

import gzip
import re

import numpy as np
import pytest

from emmet.core import ARROW_COMPATIBLE
from emmet.core.band_theory import BSPathType
from emmet.core.io.pymatgen import Outcar, Spin, Vasprun
from emmet.core.tasks import CoreTaskDoc, _get_max_force
from emmet.core.testing_utils import TEST_FILES_DIR, DataArchive
from emmet.core.vasp.calc_types.enums import RunType, TaskType
from emmet.core.vasp.calculation import Calculation
from emmet.core.vasp.parse import DirectorySource, parse_calculation
from emmet.core.vasp.parsed import PARSED_TABLES, SpinMode

if ARROW_COMPATIBLE:
    import pyarrow as pa

    from emmet.core.arrow import arrowize


def parse_all(fixture):
    """Every calculation of a fixture: by suffix, the parsed calculation and its rows."""
    out = {}
    with DataArchive.extract(TEST_FILES_DIR / "vasp" / f"{fixture}.json.gz") as d:
        for source in DirectorySource.from_directory(d):
            parsed = parse_calculation(source, "aaaaaaab")
            out[source.calc_suffix] = (parsed, dict(parsed.objects()))
            assert parsed.errors == [], parsed.errors
    return out


def vasprun_of(fixture, name="vasprun.xml.gz", **kwargs):
    with DataArchive.extract(TEST_FILES_DIR / "vasp" / f"{fixture}.json.gz") as d:
        return Vasprun(d / name, parse_potcar_file=False, **kwargs)


@pytest.fixture(scope="module")
def optic():
    return parse_all("optic")["standard"]


@pytest.fixture(scope="module")
def dfpt():
    return parse_all("dfpt_piezo")["standard"]


@pytest.fixture(scope="module")
def spin_line():
    return parse_all("spin_nscf_line")["standard"]


@pytest.fixture(scope="module")
def magnetic_static():
    return parse_all("magnetic_static_volumetric")["standard"]


@pytest.fixture(scope="module")
def magnetic_relax():
    return parse_all("magnetic_relax")["standard"]


@pytest.fixture(scope="module")
def hse():
    return parse_all("hse_static")["standard"]


@pytest.fixture(scope="module")
def triple():
    return parse_all("scan_triple_relax")


class TestOptic:
    """An LOPTICS calculation: the absorption coefficient is calculated when it is parsed."""

    def test_the_task(self, optic):
        parsed, _ = optic
        assert parsed.task.task_type == TaskType.Optic
        assert parsed.task.output.frequency_dependent_dielectric is not None

    def test_the_coefficient_is_that_of_pymatgen(self, optic):
        """It is pymatgen's property of the vasprun, as it is, on the dielectric function stored."""
        parsed, _ = optic
        vasprun = vasprun_of("optic", parse_dos=False, parse_eigen=False)
        assert list(vasprun.dielectric_data) == ["density", "velocity"]
        assert parsed.task.output.optical_absorption_coeff == (
            vasprun.optical_absorption_coeff
        )
        # of the density-density function, which is what is stored
        energy, real, imaginary = vasprun.dielectric_data["density"]
        stored = parsed.task.output.frequency_dependent_dielectric
        assert stored.energy == list(energy)
        np.testing.assert_array_equal(stored.real, real)
        np.testing.assert_array_equal(stored.imaginary, imaginary)

    def test_the_values_are_per_cm(self, optic):
        """An insulator absorbs up to 1e5 to 1e7 per cm."""
        coefficient = np.array(optic[0].task.output.optical_absorption_coeff)
        assert len(coefficient) == 2001 and coefficient[0] == 0.0
        assert 1e5 < coefficient.max() < 1e8
        # no absorption below the band gap
        energy = np.array(optic[0].task.output.frequency_dependent_dielectric.energy)
        gap = optic[0].task.output.bandgap
        assert np.all(coefficient[energy < 0.5 * gap] < 0.01 * coefficient.max())

    def test_it_is_set_for_the_calculation_and_the_full_task_document(self):
        from emmet.core.tasks import TaskDoc

        with DataArchive.extract(TEST_FILES_DIR / "vasp" / "optic.json.gz") as d:
            calc, _ = Calculation.from_vasp_files(
                d,
                "standard",
                vasprun_file="vasprun.xml.gz",
                outcar_file="OUTCAR.gz",
                contcar_file="CONTCAR.gz",
            )
            doc = TaskDoc.from_directory(d)
        expected = vasprun_of(
            "optic", parse_dos=False, parse_eigen=False
        ).optical_absorption_coeff
        assert calc.output.optical_absorption_coeff == expected
        assert doc.calcs_reversed[0].output.optical_absorption_coeff == expected

    @pytest.mark.skipif(
        not ARROW_COMPATIBLE, reason="pyarrow must be installed to run this test."
    )
    def test_it_survives_arrow(self, optic):
        task = optic[0].task
        schema = pa.schema(arrowize(CoreTaskDoc))
        table = pa.Table.from_pylist(
            [task.model_dump(context={"format": "arrow"})], schema=schema
        )
        restored = CoreTaskDoc(**table.to_pylist(maps_as_pydicts="strict")[0])
        np.testing.assert_allclose(
            restored.output.optical_absorption_coeff,
            task.output.optical_absorption_coeff,
        )
        assert len(restored.output.frequency_dependent_dielectric.energy) == 2001


class TestDfpt:
    """A LEPSILON calculation: the tensors of the OUTCAR, and a dielectric function that is not optics."""

    TENSORS = (
        "piezo_tensor",
        "piezo_ionic_tensor",
        "born",
        "dielectric_tensor",
        "dielectric_ionic_tensor",
        "internal_strain_tensor",
    )

    def test_the_task(self, dfpt):
        parsed, _ = dfpt
        assert parsed.task.task_type == TaskType.DFPT_Dielectric
        assert parsed.trajectory.num_ionic_steps == 1

    def test_the_outcar_has_the_tensors(self, dfpt):
        outcar = dfpt[0].task.output.outcar
        shapes = {k: np.shape(outcar[k]) for k in self.TENSORS}
        assert shapes == {
            "piezo_tensor": (3, 6),
            "piezo_ionic_tensor": (3, 6),
            "born": (24, 3, 3),
            "dielectric_tensor": (3, 3),
            "dielectric_ionic_tensor": (3, 3),
            "internal_strain_tensor": (24, 3, 6),
        }
        assert np.abs(np.array(outcar["piezo_tensor"])).max() > 0

    def test_they_are_what_pymatgen_reads(self, dfpt):
        with DataArchive.extract(TEST_FILES_DIR / "vasp" / "dfpt_piezo.json.gz") as d:
            outcar = Outcar(d / "OUTCAR.gz")
        stored = dfpt[0].task.output.outcar
        np.testing.assert_allclose(stored["piezo_tensor"], outcar.piezo_tensor)
        np.testing.assert_allclose(
            stored["piezo_ionic_tensor"], outcar.piezo_ionic_tensor
        )
        np.testing.assert_allclose(stored["born"], outcar.born)

    def test_the_epsilon_are_set(self, dfpt):
        output = dfpt[0].task.output
        assert np.shape(output.epsilon_static) == (3, 3)
        assert np.shape(output.epsilon_ionic) == (3, 3)
        assert output.bandgap > 0

    @pytest.mark.skipif(
        not ARROW_COMPATIBLE, reason="pyarrow must be installed to run this test."
    )
    def test_the_tensors_survive_arrow(self, dfpt):
        task = dfpt[0].task
        schema = pa.schema(arrowize(CoreTaskDoc))
        table = pa.Table.from_pylist(
            [task.model_dump(context={"format": "arrow"})], schema=schema
        )
        restored = CoreTaskDoc(**table.to_pylist(maps_as_pydicts="strict")[0])
        for key in self.TENSORS:
            np.testing.assert_allclose(
                restored.output.outcar[key], task.output.outcar[key], err_msg=key
            )

    def test_the_dielectric_function_is_not_an_optical_spectrum(self, dfpt):
        """LEPSILON writes a density dielectric function to 244 eV; it has a coefficient, but is not optics."""
        output = dfpt[0].task.output
        assert output.frequency_dependent_dielectric is not None
        assert len(output.frequency_dependent_dielectric.energy) == 2000
        assert output.optical_absorption_coeff is not None


def directory_of(fixture):
    return DataArchive.extract(TEST_FILES_DIR / "vasp" / f"{fixture}.json.gz")


class TestSpinPolarizedLine:
    """A non-self-consistent band structure along a path, of a spin-polarized calculation with a gap.

    Calculation fixture is one sodium atom in a cube of 7 A, which is close to an isolated atom with
    one unpaired electron: its gap is that between atomic-like levels, and it has one site.
    """

    def test_the_task_is_read_along_its_path(self, spin_line):
        parsed, rows = spin_line
        assert parsed.task.task_type == TaskType.NSCF_Line
        bands = rows["bandstructures"]
        assert bands.path_convention == BSPathType.setyawan_curtarolo
        assert bands.spin_mode == SpinMode.COLLINEAR
        assert bands.shape == [64, 75] and len(bands.qpoints) == 75
        assert bands.kpoint_weights is None
        assert bands.kpath == ["\\Gamma", "X", "M", "\\Gamma", "R", "X", "M", "R"]

    def test_the_k_points_and_labels_are_those_of_the_kpoints_file(self, spin_line):
        from emmet.core.io.pymatgen import Kpoints

        with directory_of("spin_nscf_line") as d:
            kpoints = Kpoints.from_file(d / "KPOINTS.gz")
        bands = spin_line[1]["bandstructures"]
        assert kpoints.style.name == "Reciprocal" and len(kpoints.kpts) == 75
        np.testing.assert_allclose(bands.qpoints, kpoints.kpts, atol=1e-6)
        assert bands.kpoint_labels == [label or None for label in kpoints.labels]
        assert sum(label is not None for label in bands.kpoint_labels) == 12

    def test_the_gap_is_that_of_the_bands(self, spin_line):
        """The gap of the task is that of the band structure, which is built from the row."""
        parsed, rows = spin_line
        rebuilt = rows["bandstructures"].to_pmg(rows["projected-bandstructures"])
        gap = rebuilt.get_band_gap()
        assert gap["energy"] == pytest.approx(1.1475, abs=1e-4)
        assert gap["transition"] == "R-X" and not gap["direct"]
        assert parsed.task.output.bandgap == pytest.approx(gap["energy"], abs=1e-4)
        assert not rebuilt.is_metal()

    def test_the_spins_have_their_own_bands(self, spin_line):
        bands = spin_line[1]["bandstructures"]
        with directory_of("spin_nscf_line") as d:
            vasprun = Vasprun(
                d / "vasprun.xml.gz",
                parse_potcar_file=False,
                parse_projected_eigen=True,
            )
        up, down = (
            np.asarray(vasprun.eigenvalues[s])[:, :, 0].T for s in (Spin.up, Spin.down)
        )
        np.testing.assert_allclose(np.reshape(bands.bands_up, bands.shape), up)
        np.testing.assert_allclose(np.reshape(bands.bands_down, bands.shape), down)
        near = np.minimum(up, down) < vasprun.efermi + 3.0
        assert np.abs(up - down)[near].max() > 1.0

    def test_the_projections_of_each_spin(self, spin_line):
        _, rows = spin_line
        projections = rows["projected-bandstructures"]
        assert projections.shape == [64, 75, 9, 1]
        assert projections.orbitals == [
            "s",
            "py",
            "pz",
            "px",
            "dxy",
            "dyz",
            "dz2",
            "dxz",
            "dx2_y2",
        ]
        assert projections.spin_mode == SpinMode.COLLINEAR
        rebuilt = rows["bandstructures"].to_pmg(projections)
        up, down = rebuilt.projections[Spin.up], rebuilt.projections[Spin.down]
        assert up.shape == down.shape == (64, 75, 9, 1)
        assert not np.allclose(up, down)

    def test_the_moment_of_the_one_atom(self, spin_line):
        """VASP writes no sum of the atoms for one atom, which the moments are read in spite of."""
        parsed, _ = spin_line
        assert parsed.errors == []
        trajectory = parsed.trajectory
        assert trajectory.spin_mode == SpinMode.COLLINEAR
        with directory_of("spin_nscf_line") as d:
            outcar = Outcar(d / "OUTCAR.gz")
        assert trajectory.magmoms == pytest.approx(
            [m["tot"] for m in outcar.magnetization]
        )
        assert trajectory.magmoms == pytest.approx([0.114])
        assert trajectory.total_magnetization == pytest.approx([outcar.total_mag])

    def test_the_original_inputs(self, spin_line):
        orig = spin_line[0].task.orig_inputs
        assert orig is not None and orig.incar["ICHARG"] == 11
        assert orig.kpoints is None


class TestMagneticStatic:
    """Fixture is a static calculation of EuO, magnetic, with every volumetric file the policy keeps."""

    @pytest.fixture(scope="class")
    def references(self):
        """The volumetric files and the OUTCAR, as pymatgen reads them."""
        from emmet.core.io.pymatgen import Chgcar, Elfcar, Locpot

        with directory_of("magnetic_static_volumetric") as d:
            return {
                "chgcar": Chgcar.from_file(d / "CHGCAR.gz"),
                "aeccar2": Chgcar.from_file(d / "AECCAR2.gz"),
                "locpot": Locpot.from_file(d / "LOCPOT.gz"),
                "elfcar": Elfcar.from_file(d / "ELFCAR.gz"),
                "outcar": Outcar(d / "OUTCAR.gz"),
            }

    def test_the_tables(self, magnetic_static):
        parsed, rows = magnetic_static
        assert parsed.errors == []
        assert parsed.task.task_type == TaskType.Static
        assert parsed.task.run_type == RunType.r2SCAN
        assert {
            "charge-density",
            "valence-density",
            "local-potential",
            "electron-localization",
        } <= set(rows)
        # the CHGCAR is parsed too, as the policy keeps it
        assert rows["charge-density"].file_name == "CHGCAR.gz"
        assert rows["valence-density"].file_name == "AECCAR2.gz"

    def test_the_magnetization_is_that_of_the_outcar(self, magnetic_static, references):
        """The magnetization block integrates to the total magnetization, which is -7 and not +10."""
        density = magnetic_static[1]["charge-density"]
        total = references["outcar"].total_mag
        assert total == pytest.approx(-6.9975089)
        assert density.spin_mode == SpinMode.COLLINEAR
        cells = np.prod(density.grid_shape)
        assert np.sum(density.magnetization) / cells == pytest.approx(total, abs=1e-4)
        assert np.sum(density.total) / cells == pytest.approx(23.0, abs=1e-4)

    def test_the_values_are_those_of_pymatgen(self, magnetic_static, references):
        _, rows = magnetic_static
        density = rows["charge-density"]
        np.testing.assert_allclose(
            density.total, references["chgcar"].data["total"].ravel(), rtol=1e-6
        )
        np.testing.assert_allclose(
            density.magnetization, references["chgcar"].data["diff"].ravel(), rtol=1e-6
        )
        potential = rows["local-potential"]
        assert potential.potential is None and potential.potential_kind == "total"
        np.testing.assert_allclose(
            potential.spin_up, references["locpot"].data["spin_up"].ravel(), rtol=1e-6
        )
        np.testing.assert_allclose(
            potential.spin_down,
            references["locpot"].data["spin_down"].ravel(),
            rtol=1e-6,
        )
        elf = rows["electron-localization"]
        np.testing.assert_allclose(
            elf.elf_up, references["elfcar"].data["spin_up"].ravel(), rtol=1e-6
        )
        np.testing.assert_allclose(
            elf.elf_down, references["elfcar"].data["spin_down"].ravel(), rtol=1e-6
        )

    def test_the_spins_are_not_the_same(self, magnetic_static):
        """Neither of the spins is a copy of the other, nor swapped (the values above are in order)."""
        _, rows = magnetic_static
        potential, elf = rows["local-potential"], rows["electron-localization"]
        for up, down in (
            (potential.spin_up, potential.spin_down),
            (elf.elf_up, elf.elf_down),
        ):
            up, down = np.asarray(up), np.asarray(down)
            assert np.abs(up - down).max() > 0.2 * np.abs(up).max()
        assert (
            np.abs(
                np.asarray(potential.spin_up) - np.asarray(potential.spin_down)
            ).max()
            > 20
        )
        assert (
            elf.elf is None and 0.0 <= min(elf.elf_up) and max(elf.elf_up) <= 1.0 + 1e-6
        )

    def test_the_all_electron_density_has_one_block(self, magnetic_static, references):
        """AECCAR2 has the total density only."""
        valence = magnetic_static[1]["valence-density"]
        assert list(references["aeccar2"].data) == ["total"]
        assert valence.spin_mode == SpinMode.UNPOLARIZED
        assert valence.total is not None and valence.magnetization is None

    def test_the_grids_of_the_files(self, magnetic_static):
        """The density is on the fine grid, and the localization function on the coarse one."""
        _, rows = magnetic_static
        assert rows["charge-density"].grid_shape == [64, 64, 64]
        assert rows["local-potential"].grid_shape == [64, 64, 64]
        assert rows["valence-density"].grid_shape == [64, 64, 64]
        assert rows["electron-localization"].grid_shape == [32, 32, 32]
        assert len(rows["electron-localization"].elf_up) == 32**3
        # the cell is the same in all of them
        structure = rows["charge-density"].structure
        assert (
            rows["electron-localization"].structure.composition == structure.composition
        )
        assert structure.composition.reduced_formula == "EuO"

    def test_the_electronic_structure_has_both_spins(self, magnetic_static):
        _, rows = magnetic_static
        dos, bands = rows["total-dos"], rows["bandstructures"]
        assert dos.spin_mode == bands.spin_mode == SpinMode.COLLINEAR
        assert bands.path_convention == BSPathType.uniform
        assert bands.shape == [20, 328] and len(bands.kpoint_weights) == 328
        assert np.abs(np.subtract(dos.density_up, dos.density_down)).max() > 0.5 * max(
            dos.density_up
        )
        assert not np.allclose(bands.bands_up, bands.bands_down)
        assert rows["projected-dos"].shape == [2, 16, 301]

    def test_the_moments(self, magnetic_static, references):
        parsed, _ = magnetic_static
        assert parsed.trajectory.magmoms == pytest.approx(
            [m["tot"] for m in references["outcar"].magnetization]
        )
        assert parsed.trajectory.magmoms[0] < -6.0
        assert parsed.trajectory.total_magnetization == pytest.approx([-6.9975089])

    def test_the_original_inputs(self, magnetic_static):
        """The calculation has the INCAR and POSCAR it was started with, and no KPOINTS (it has KSPACING)."""
        task = magnetic_static[0].task
        assert task.orig_inputs is not None
        assert task.orig_inputs.incar["MAGMOM"] == [10.0, 0.6]
        assert task.orig_inputs.kpoints is None
        assert task.orig_inputs.poscar is not None
        assert task.input.incar["KSPACING"] == 0.1

    @pytest.mark.skipif(
        not ARROW_COMPATIBLE, reason="pyarrow must be installed to run this test."
    )
    def test_the_rows_fit_their_tables(self, magnetic_static):
        for table in (
            "charge-density",
            "valence-density",
            "local-potential",
            "electron-localization",
        ):
            spec = PARSED_TABLES[table]
            schema = pa.schema(arrowize(spec.row_model))
            row = magnetic_static[1][table]
            arrow = pa.Table.from_pylist(
                [row.model_dump(context={"format": "arrow"})], schema=schema
            )
            restored = type(row)(**arrow.to_pylist(maps_as_pydicts="strict")[0])
            for column in spec.row_model.BLOCK_COLUMNS:
                if getattr(row, column) is None:
                    assert getattr(restored, column) is None, column
                    continue
                # the grids are stored as float32
                np.testing.assert_allclose(
                    getattr(restored, column),
                    getattr(row, column),
                    rtol=1e-6,
                    err_msg=column,
                )


class TestHse:
    """Fixture is an HSE06 static on a uniform mesh."""

    def test_the_run_type(self, hse):
        parsed, rows = hse
        assert parsed.task.run_type == RunType.HSE06
        assert parsed.task.task_type == TaskType.Static

    def test_the_mesh_has_its_weights(self, hse):
        bands = hse[1]["bandstructures"]
        vasprun = vasprun_of("hse_static", parse_dos=False, parse_eigen=False)
        assert bands.path_convention == BSPathType.uniform
        assert bands.kpoint_labels is None and bands.kpath is None
        assert len(bands.qpoints) == len(bands.kpoint_weights) == 20
        assert sum(bands.kpoint_weights) == pytest.approx(1.0)
        np.testing.assert_allclose(bands.kpoint_weights, vasprun.actual_kpoints_weights)
        assert bands.spin_mode == SpinMode.COLLINEAR

    def test_the_settings(self, hse):
        trajectory = hse[0].trajectory
        assert trajectory.ediff == pytest.approx(1e-4)
        assert hse[0].task.input.parameters["LHFCALC"] is True
        assert hse[0].task.input.parameters["HFSCREEN"] == 0.2


def step_moments(outcar_text, num_sites):
    """The moments and the total magnetization after each ionic step, with regular expressions.

    This does not use the reader of emmet: a step is what comes before a line of energies, and
    its moments are the first rows of the last block of moments in it.
    """
    # s, p, d and tot, and f when a species has f electrons
    row = re.compile(r"^\s*\d+(?:\s+-?\d+\.\d+){4,5}\s*$", re.MULTILINE)
    total = re.compile(r"number of electron\s+\S+\s+magnetization\s+(\S+)")
    moments, totals = [], []
    for chunk in outcar_text.split("FREE ENERGIE OF THE ION-ELECTRON SYSTEM")[:-1]:
        block = chunk[chunk.rindex("magnetization (x)") :]
        moments.append([float(r.split()[-1]) for r in row.findall(block)[:num_sites]])
        totals.append(float(total.findall(chunk)[-1]))
    return np.array(moments), np.array(totals)


class TestMagneticRelaxation:
    """A relaxation of YCo, with moments of 1 mu_B that change along the 10 steps."""

    @pytest.fixture(scope="class")
    def reference(self):
        with directory_of("magnetic_relax") as d:
            text = gzip.open(d / "OUTCAR.gz", "rt").read()
            vasprun = Vasprun(
                d / "vasprun.xml.gz",
                parse_potcar_file=False,
                parse_dos=False,
                parse_eigen=False,
            )
        return text, vasprun

    def test_the_task(self, magnetic_relax):
        parsed, rows = magnetic_relax
        assert parsed.task.task_type == TaskType.Structure_Optimization
        assert parsed.task.run_type == RunType.r2SCAN
        assert parsed.trajectory.num_ionic_steps == 10
        assert rows == {}

    def test_the_moments_of_every_step(self, magnetic_relax, reference):
        trajectory = magnetic_relax[0].trajectory
        moments, totals = step_moments(reference[0], 4)
        assert moments.shape == (10, 4)
        np.testing.assert_allclose(np.reshape(trajectory.magmoms, (10, 4)), moments)
        np.testing.assert_allclose(trajectory.total_magnetization, totals)

    def test_the_moments_change(self, magnetic_relax):
        """A step read for another would show here: the moments move by 0.2 mu_B and the total by 0.1."""
        trajectory = magnetic_relax[0].trajectory
        moments = np.reshape(trajectory.magmoms, (10, 4))
        assert np.abs(moments - moments[0]).max() > 0.2
        assert moments[0] == pytest.approx([-0.381, -0.381, 1.101, 1.101])
        assert moments[-1] == pytest.approx([-0.400, -0.400, 1.238, 1.238])
        assert trajectory.total_magnetization[0] == pytest.approx(1.0069988)
        assert trajectory.total_magnetization[-1] == pytest.approx(1.1224108)
        # the sites are in pairs, as the structure is
        assert moments[:, 0] == pytest.approx(moments[:, 1], abs=1e-3)
        assert moments[:, 2] == pytest.approx(moments[:, 3], abs=1e-3)

    def test_the_last_step_is_what_pymatgen_reads(self, magnetic_relax, reference):
        trajectory = magnetic_relax[0].trajectory
        with directory_of("magnetic_relax") as d:
            outcar = Outcar(d / "OUTCAR.gz")
        np.testing.assert_allclose(
            np.reshape(trajectory.magmoms, (10, 4))[-1],
            [m["tot"] for m in outcar.magnetization],
        )
        assert trajectory.total_magnetization[-1] == pytest.approx(outcar.total_mag)

    def test_the_forces_and_the_cell(self, magnetic_relax, reference):
        trajectory = magnetic_relax[0].trajectory
        vasprun = reference[1]
        forces = np.array([s["forces"] for s in vasprun.ionic_steps])
        np.testing.assert_allclose(
            trajectory.max_force, np.linalg.norm(forces, axis=2).max(axis=1)
        )
        assert trajectory.ediffg == pytest.approx(-0.02)
        assert trajectory.max_force[0] == pytest.approx(0.23, abs=0.01)
        assert trajectory.max_force[-1] < 0.02
        lattice = np.reshape(trajectory.lattice, (10, 3, 3))
        assert not np.allclose(lattice[0], lattice[-1])
        np.testing.assert_allclose(
            lattice[-1], vasprun.ionic_steps[-1]["structure"].lattice.matrix
        )
        assert len(trajectory.energy_convergence()) == sum(trajectory.num_scf_steps)

    def test_the_inputs(self, magnetic_relax):
        """INCAR and POSCAR were corrected, and the KPOINTS are those the run made from KSPACING."""
        task = magnetic_relax[0].task
        assert task.orig_inputs is not None
        assert (
            task.orig_inputs.incar["KSPACING"] == 0.22 == task.input.incar["KSPACING"]
        )
        assert task.orig_inputs.kpoints is None
        assert task.input.kpoints.style.name == "Gamma"
        assert task.input.kpoints.kpts == [(8.0, 8.0, 6.0)]

    @pytest.mark.skipif(
        not ARROW_COMPATIBLE, reason="pyarrow must be installed to run this test."
    )
    def test_the_trajectory_survives_arrow(self, magnetic_relax):
        row = magnetic_relax[0].trajectory
        schema = pa.schema(arrowize(PARSED_TABLES["trajectories"].row_model))
        table = pa.Table.from_pylist(
            [row.model_dump(context={"format": "arrow"})], schema=schema
        )
        restored = type(row)(**table.to_pylist(maps_as_pydicts="strict")[0])
        np.testing.assert_array_equal(restored.magmoms, row.magmoms)
        np.testing.assert_array_equal(
            restored.total_magnetization, row.total_magnetization
        )


class TestTripleRelaxation:
    """Fixture is a directory of three calculations: two relaxations, with a static between them."""

    def test_the_calculations(self, triple):
        assert list(triple) == ["relax1", "relax2", "relax3"]
        assert triple["relax1"][0].task.task_type == TaskType.Structure_Optimization
        assert triple["relax2"][0].task.task_type == TaskType.Static
        assert triple["relax3"][0].task.task_type == TaskType.Structure_Optimization
        assert triple["relax3"][0].task.run_type == RunType.SCAN
        assert triple["relax1"][0].task.run_type == RunType.GGA
        # one directory, a task each, and only the static has electronic structure
        assert len({p.task.dir_name for p, _ in triple.values()}) == 1
        assert set(triple["relax2"][1]) >= {"total-dos", "bandstructures"}
        assert triple["relax1"][1] == {} and triple["relax3"][1] == {}

    def test_the_steps(self, triple):
        steps = {k: p.trajectory.num_ionic_steps for k, (p, _) in triple.items()}
        assert steps == {"relax1": 3, "relax2": 1, "relax3": 60}

    def test_the_scan_calculation_is_nonmagnetic(self, triple):
        """Its moments are zero at all 60 steps, which is a value and not a missing one."""
        trajectory = triple["relax3"][0].trajectory
        assert trajectory.magmoms is not None and len(trajectory.magmoms) == 60 * 7
        assert np.allclose(trajectory.magmoms, 0.0)
        assert np.allclose(trajectory.total_magnetization, 0.0)

    def test_the_forces_and_convergence(self, triple):
        parsed, _ = triple["relax3"]
        trajectory = parsed.trajectory
        vasprun = vasprun_of(
            "scan_triple_relax",
            "vasprun.xml.relax3.gz",
            parse_dos=False,
            parse_eigen=False,
        )
        forces = np.array([s["forces"] for s in vasprun.ionic_steps])
        np.testing.assert_allclose(
            trajectory.max_force, np.linalg.norm(forces, axis=2).max(axis=1)
        )
        # the relaxation ends below the force it was asked to reach (EDIFFG = -0.02)
        assert trajectory.ediffg == pytest.approx(-0.02)
        assert trajectory.max_force[-1] < 0.02 + 1e-9
        assert trajectory.max_force[0] > trajectory.max_force[-1]
        convergence = trajectory.energy_convergence()
        assert (
            len(convergence) == sum(trajectory.num_scf_steps) and convergence[-1] == 0.0
        )
        assert sum(trajectory.num_scf_steps) > 60
        # the cell relaxes: ISIF = 3, so every step has its own lattice
        lattice = np.reshape(trajectory.lattice, (60, 3, 3))
        assert not np.allclose(lattice[0], lattice[-1])

    def test_the_max_force_is_that_of_the_task(self, triple):
        parsed, _ = triple["relax3"]
        vasprun = vasprun_of(
            "scan_triple_relax",
            "vasprun.xml.relax3.gz",
            parse_dos=False,
            parse_eigen=False,
        )
        from types import SimpleNamespace

        calc = SimpleNamespace(
            output=SimpleNamespace(
                ionic_steps=[
                    SimpleNamespace(forces=vasprun.ionic_steps[-1]["forces"].tolist())
                ],
                structure=vasprun.final_structure,
            )
        )
        assert parsed.trajectory.max_force[-1] == pytest.approx(_get_max_force(calc))

    @pytest.mark.skipif(
        not ARROW_COMPATIBLE, reason="pyarrow must be installed to run this test."
    )
    def test_the_long_trajectory_survives_arrow(self, triple):
        row = triple["relax3"][0].trajectory
        spec = PARSED_TABLES["trajectories"]
        schema = pa.schema(arrowize(spec.row_model))
        table = pa.Table.from_pylist(
            [row.model_dump(context={"format": "arrow"})], schema=schema
        )
        restored = type(row)(**table.to_pylist(maps_as_pydicts="strict")[0])
        np.testing.assert_array_equal(restored.forces, row.forces)
        np.testing.assert_array_equal(restored.magmoms, row.magmoms)
        assert restored.num_scf_steps == row.num_scf_steps

    def test_each_calculation_has_its_files(self):
        """The inputs and the custodian file are the calculation's own, the original inputs the first one's."""
        from emmet.core.vasp.utils import discover_calculations

        with directory_of("scan_triple_relax") as d:
            found = {
                locator.modifier: files
                for locator, files in discover_calculations(d).items()
            }
            assert list(found) == ["relax1", "relax2", "relax3"]
            for suffix, files in found.items():
                assert sorted(files.inputs) == ["INCAR", "POSCAR"]
                assert files.inputs["INCAR"].name.startswith(f"INCAR.{suffix}")
                assert files.inputs["POSCAR"].name.startswith(f"POSCAR.{suffix}")
                assert files.workflow["custodian.json"].name.startswith(
                    f"custodian.json.{suffix}"
                )
            assert sorted(found["relax1"].orig_inputs) == ["INCAR", "POSCAR"]
            assert found["relax2"].orig_inputs == found["relax3"].orig_inputs == {}

    def test_the_original_inputs_are_those_of_the_first_calculation(self, triple):
        """They are the inputs of the SCAN workflow, which the first calculation, a GGA relaxation, was not."""
        tasks = {k: p.task for k, (p, _) in triple.items()}
        assert tasks["relax2"].orig_inputs is None
        assert tasks["relax3"].orig_inputs is None

        orig = tasks["relax1"].orig_inputs
        assert orig is not None
        assert orig.kpoints is None and orig.potcar_spec is None
        assert orig.incar["METAGGA"] == "Scan" and orig.incar["EDIFFG"] == -0.02
        assert orig.incar["KSPACING"] == 0.22 and orig.incar["NSW"] == 99
        assert orig.incar["MAGMOM"] == [0.0] * 7
        # the structure it was started with
        with directory_of("scan_triple_relax") as d:
            vasprun = Vasprun(
                d / "vasprun.xml.relax1.gz",
                parse_potcar_file=False,
                parse_dos=False,
                parse_eigen=False,
            )
        assert len(orig.structure) == 7
        np.testing.assert_allclose(
            orig.structure.lattice.matrix,
            vasprun.initial_structure.lattice.matrix,
            atol=1e-5,
        )
        np.testing.assert_allclose(
            orig.structure.frac_coords, vasprun.initial_structure.frac_coords, atol=1e-5
        )
        # and what ran was not that: a pre-relaxation without SCAN, to a looser force
        ran = tasks["relax1"].input.incar
        assert ran["METAGGA"] == "None" and ran["EDIFFG"] == -0.05
        assert tasks["relax1"].run_type == RunType.GGA

    def test_the_inputs_of_each_calculation(self, triple):
        """What the vasprun has of each: they change from one calculation to the next."""
        expected = {
            "relax1": ("None", 0.22, 2, 99, [0.0] * 7, (7, 7, 7)),
            "relax2": ("None", 0.3113214, -5, 0, [5.0] + [0.6] * 6, (5, 5, 5)),
            "relax3": ("Scan", 0.3113214, -5, 99, [5.0] + [0.6] * 6, (5, 5, 5)),
        }
        for suffix, (metagga, kspacing, ismear, nsw, magmom, mesh) in expected.items():
            task = triple[suffix][0].task
            incar = task.input.incar
            assert incar["METAGGA"] == metagga, suffix
            assert incar["KSPACING"] == pytest.approx(kspacing), suffix
            assert (incar["ISMEAR"], incar["NSW"]) == (ismear, nsw), suffix
            assert incar["MAGMOM"] == magmom, suffix
            # no KPOINTS file: the mesh is the one VASP made of KSPACING
            assert task.input.kpoints.style.name == "Gamma"
            assert tuple(int(k) for k in task.input.kpoints.kpts[0]) == mesh, suffix
            # it is what VASP read, and not the INCAR file (which has NCORE, a setting of the machine)
            assert "NCORE" not in incar

    def test_the_input_files_are_those_of_their_calculation(self, triple):
        """`INCAR.relaxN` agrees with the INCAR that the vasprun recorded, apart from the machine's settings."""
        from emmet.core.io.pymatgen import Incar

        with directory_of("scan_triple_relax") as d:
            for suffix in ("relax1", "relax2", "relax3"):
                written = Incar.from_file(d / f"INCAR.{suffix}.gz")
                recorded = triple[suffix][0].task.input.incar
                for key in ("METAGGA", "EDIFFG", "NSW", "ISMEAR", "SIGMA", "MAGMOM"):
                    assert written[key] == recorded[key], (suffix, key)
                assert written["KSPACING"] == pytest.approx(recorded["KSPACING"])
                assert written["NCORE"] == 4

    @pytest.mark.skipif(
        not ARROW_COMPATIBLE, reason="pyarrow must be installed to run this test."
    )
    def test_the_original_inputs_survive_arrow(self, triple):
        task = triple["relax1"][0].task
        schema = pa.schema(arrowize(CoreTaskDoc))
        table = pa.Table.from_pylist(
            [task.model_dump(context={"format": "arrow"})], schema=schema
        )
        restored = CoreTaskDoc(**table.to_pylist(maps_as_pydicts="strict")[0])
        assert restored.orig_inputs.incar == task.orig_inputs.incar
        assert restored.orig_inputs.incar["METAGGA"] == "Scan"
        assert len(restored.orig_inputs.structure) == 7
        np.testing.assert_allclose(
            restored.orig_inputs.structure.lattice.matrix,
            task.orig_inputs.structure.lattice.matrix,
        )
