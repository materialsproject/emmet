"""Test choosing the task that the dielectric, piezoelectric and absorption builders use."""

import gzip
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import numpy as np
import pytest

from emmet.builders.materials.absorption_spectrum import (
    obtain_blessed_absorption_builder_input,
)
from emmet.builders.materials.linear_response import (
    DielectricBuilderInput,
    PiezoelectricBuilderInput,
    obtain_blessed_linear_builder_input,
)
from emmet.core.io.pymatgen import Vasprun
from emmet.core.testing_utils import DataArchive
from emmet.core.vasp.calc_types.enums import TaskType
from emmet.core.vasp.calculation import FrequencyDependentDielectric
from emmet.core.vasp.parse import DirectorySource, parse_calculation

PIEZO = ((1.0, 0, 0, 0, 0, 0), (0, 2.0, 0, 0, 0, 0), (0, 0, 3.0, 0, 0, 0))
PIEZO_IONIC = ((0.5, 0, 0, 0, 0, 0), (0, 0.5, 0, 0, 0, 0), (0, 0, 0.5, 0, 0, 0))
EPSILON = [[10.0, 0, 0], [0, 10.0, 0], [0, 0, 10.0]]


@pytest.fixture(scope="module")
def base_task(test_dir):
    with DataArchive.extract(test_dir / "vasp" / "Si_static.json.gz") as directory:
        parsed = parse_calculation(
            DirectorySource.from_directory(directory)[0], "aaaaaaab"
        )
    return parsed.task


@pytest.fixture(scope="module")
def dielectric(test_dir):
    data = json.load(gzip.open(test_dir / "sample_absorptions.json.gz", "rt"))
    return FrequencyDependentDielectric(
        **data["calcs_reversed"][0]["output"]["frequency_dependent_dielectric"]
    )


def with_output(task, task_id, **output):
    """A copy of a task with changes to its output."""
    return task.model_copy(
        update={
            "task_id": task_id,
            "output": task.output.model_copy(update=output),
        }
    )


class TestPiezoelectric:
    def outcar(self, task, **tensors):
        return {**(task.output.outcar or {}), **tensors}

    def test_the_tensors_are_those_of_the_outcar(self, base_task):
        """The OUTCAR names the tensors piezo_tensor and piezo_ionic_tensor."""
        task = with_output(
            base_task,
            "aaaaaaab",
            bandgap=0.5,
            outcar=self.outcar(
                base_task, piezo_tensor=PIEZO, piezo_ionic_tensor=PIEZO_IONIC
            ),
        )
        doc = obtain_blessed_linear_builder_input(
            [task], "piezoelectric", PiezoelectricBuilderInput, material_id="mp-1"
        )
        assert doc.piezo_static == PIEZO
        assert doc.piezo_ionic == PIEZO_IONIC
        assert doc.origins[0].name == "piezoelectric"

    def test_tasks_without_the_tensors_are_skipped(self, base_task):
        without = with_output(base_task, "aaaaaaab", bandgap=0.5)
        with_tensors = with_output(
            base_task,
            "aaaaaaac",
            bandgap=0.5,
            outcar=self.outcar(
                base_task, piezo_tensor=PIEZO, piezo_ionic_tensor=PIEZO_IONIC
            ),
        )
        doc = obtain_blessed_linear_builder_input(
            [without, with_tensors], "piezoelectric", PiezoelectricBuilderInput
        )
        assert doc.origins[0].task_id == "aaaaaaac"

    def test_a_metal_is_skipped(self, base_task):
        metal = with_output(
            base_task,
            "aaaaaaab",
            bandgap=0.0,
            outcar=self.outcar(
                base_task, piezo_tensor=PIEZO, piezo_ionic_tensor=PIEZO_IONIC
            ),
        )
        with pytest.raises(ValueError, match="piezoelectric"):
            obtain_blessed_linear_builder_input(
                [metal], "piezoelectric", PiezoelectricBuilderInput
            )

    def test_no_task_is_a_clear_error(self, base_task):
        with pytest.raises(ValueError, match="output.piezo_static"):
            obtain_blessed_linear_builder_input(
                [with_output(base_task, "aaaaaaab", bandgap=0.5)],
                "piezoelectric",
                PiezoelectricBuilderInput,
            )
        with pytest.raises(ValueError, match="output.epsilon_static"):
            obtain_blessed_linear_builder_input(
                [], "dielectric", DielectricBuilderInput
            )


class TestDielectric:
    def test_epsilon_is_from_the_output(self, base_task):
        task = with_output(
            base_task,
            "aaaaaaab",
            bandgap=0.5,
            epsilon_static=EPSILON,
            epsilon_ionic=EPSILON,
        )
        doc = obtain_blessed_linear_builder_input(
            [task], "dielectric", DielectricBuilderInput
        )
        assert [list(row) for row in doc.epsilon_static] == EPSILON
        assert doc.origins[0].name == "dielectric"


def absorption_of(dielectric):
    """The coefficient that is stored with a dielectric function: pymatgen's, as the parser stores it."""
    stub = SimpleNamespace(
        dielectric_data={
            "density": (dielectric.energy, dielectric.real, dielectric.imaginary)
        }
    )
    return Vasprun.optical_absorption_coeff.fget(stub)


class TestAbsorption:
    def task(self, base_task, dielectric, task_id, **output):
        output.setdefault("optical_absorption_coeff", absorption_of(dielectric))
        optics = with_output(
            base_task,
            task_id,
            bandgap=0.5,
            frequency_dependent_dielectric=dielectric,
            **output,
        )
        return optics.model_copy(update={"task_type": TaskType.Optic})

    def test_the_stored_coefficient_is_used(self, base_task, dielectric):
        stored = [1.0] * len(dielectric.energy)
        doc = obtain_blessed_absorption_builder_input(
            [
                self.task(
                    base_task, dielectric, "aaaaaaab", optical_absorption_coeff=stored
                )
            ]
        )
        assert doc.absorption_co == stored
        assert doc.energies == dielectric.energy

    def test_a_task_without_a_coefficient_is_skipped(self, base_task, dielectric):
        """The coefficient is stored when a task is parsed, and the builder does not make up for its absence."""
        without = self.task(
            base_task, dielectric, "aaaaaaab", optical_absorption_coeff=None
        )
        with pytest.raises(ValueError, match="absorption coefficient"):
            obtain_blessed_absorption_builder_input([without])
        doc = obtain_blessed_absorption_builder_input(
            [without, self.task(base_task, dielectric, "aaaaaaac")]
        )
        assert doc.origins[0].task_id == "aaaaaaac"
        assert doc.imag_d == dielectric.imaginary

    def test_the_task_with_most_kpoints_or_the_newest_is_chosen(
        self, base_task, dielectric
    ):
        older = self.task(base_task, dielectric, "aaaaaaab").model_copy(
            update={"last_updated": datetime(2020, 1, 1, tzinfo=UTC)}
        )
        newer = older.model_copy(
            update={
                "task_id": "aaaaaaac",
                "last_updated": datetime(2020, 1, 1, tzinfo=UTC) + timedelta(days=1),
            }
        )
        doc = obtain_blessed_absorption_builder_input([older, newer])
        assert doc.origins[0].task_id == "aaaaaaac"

    def test_tasks_without_a_dielectric_are_skipped(self, base_task, dielectric):
        plain = with_output(base_task, "aaaaaaab", bandgap=0.5).model_copy(
            update={"task_type": TaskType.Optic}
        )
        doc = obtain_blessed_absorption_builder_input(
            [plain, self.task(base_task, dielectric, "aaaaaaac")]
        )
        assert doc.origins[0].task_id == "aaaaaaac"

    def test_other_calculations_are_not_used_for_their_dielectric(
        self, base_task, dielectric
    ):
        """A static with a dielectric function is not an optical spectrum."""
        static = with_output(
            base_task,
            "aaaaaaab",
            bandgap=0.5,
            frequency_dependent_dielectric=dielectric,
        )
        assert static.task_type != TaskType.Optic
        with pytest.raises(ValueError, match="optics calculation"):
            obtain_blessed_absorption_builder_input([static])

    def test_no_task_is_a_clear_error_not_an_index_error(self, base_task):
        optics_without = with_output(base_task, "aaaaaaab", bandgap=0.5).model_copy(
            update={"task_type": TaskType.Optic}
        )
        with pytest.raises(ValueError, match="frequency dependent dielectric"):
            obtain_blessed_absorption_builder_input([optics_without])
        with pytest.raises(ValueError, match="frequency dependent dielectric"):
            obtain_blessed_absorption_builder_input([])


@pytest.fixture(scope="module")
def real_tasks(test_dir):
    """The tasks of an optics, a DFPT and a plain calculation, as the parser makes them."""
    tasks = {}
    for fixture in ("optic", "dfpt_piezo", "hse_static"):
        with DataArchive.extract(test_dir / "vasp" / f"{fixture}.json.gz") as directory:
            parsed = parse_calculation(
                DirectorySource.from_directory(directory)[0], "aaaaaaab"
            )
        assert parsed.errors == []
        tasks[fixture] = parsed.task
    return tasks


class TestRealCalculations:
    def test_the_absorption_of_an_optics_calculation(self, real_tasks):
        task = real_tasks["optic"]
        doc = obtain_blessed_absorption_builder_input([task])
        assert doc.absorption_co == task.output.optical_absorption_coeff
        assert len(doc.energies) == len(doc.real_d) == 2001
        assert doc.bandgap == task.output.bandgap

    def test_a_dfpt_calculation_is_not_an_absorption_spectrum(self, real_tasks):
        """LEPSILON writes a dielectric function, and a coefficient is derived from it."""
        dfpt = real_tasks["dfpt_piezo"]
        assert dfpt.output.optical_absorption_coeff is not None
        with pytest.raises(ValueError, match="optics calculation"):
            obtain_blessed_absorption_builder_input([dfpt])
        # with both, the optics one is used
        doc = obtain_blessed_absorption_builder_input(
            [dfpt, real_tasks["optic"]], material_id="mp-1"
        )
        assert doc.origins[0].task_id == real_tasks["optic"].task_id

    def test_the_piezoelectric_input_of_a_dfpt_calculation(self, real_tasks):
        """The piezoelectric tensors of the OUTCAR of a real calculation, with the keys it has."""
        dfpt = real_tasks["dfpt_piezo"]
        doc = obtain_blessed_linear_builder_input(
            [dfpt], "piezoelectric", PiezoelectricBuilderInput, material_id="mp-1"
        )
        assert doc.piezo_static == tuple(map(tuple, dfpt.output.outcar["piezo_tensor"]))
        assert doc.piezo_ionic == tuple(
            map(tuple, dfpt.output.outcar["piezo_ionic_tensor"])
        )
        assert abs(doc.piezo_static[2][2]) > 0 or any(
            abs(x) > 0 for row in doc.piezo_static for x in row
        )

    def test_the_dielectric_input_of_a_dfpt_calculation(self, real_tasks):
        dfpt = real_tasks["dfpt_piezo"]
        doc = obtain_blessed_linear_builder_input(
            [dfpt], "dielectric", DielectricBuilderInput
        )
        np.testing.assert_allclose(doc.epsilon_static, dfpt.output.epsilon_static)
        np.testing.assert_allclose(doc.epsilon_ionic, dfpt.output.epsilon_ionic)

    def test_a_plain_calculation_has_neither(self, real_tasks):
        for property_name, target in (
            ("piezoelectric", PiezoelectricBuilderInput),
            ("dielectric", DielectricBuilderInput),
        ):
            with pytest.raises(ValueError):
                obtain_blessed_linear_builder_input(
                    [real_tasks["hse_static"]], property_name, target
                )
