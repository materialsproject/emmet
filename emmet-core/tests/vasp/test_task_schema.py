"""Test the schema of the tasks table: what CoreTaskDoc holds and no longer holds."""

from types import SimpleNamespace

import numpy as np
import pytest

from emmet.core import ARROW_COMPATIBLE
from emmet.core.io.pymatgen import Kpoints, Vasprun
from emmet.core.tasks import CoreTaskDoc, TaskDoc, ValidationTaskDoc
from emmet.core.testing_utils import TEST_FILES_DIR, DataArchive
from emmet.core.types.pymatgen_types.kpoints_adapter import (
    TypedKpointsDict,
    kpoints_deserializer,
)
from emmet.core.vasp.calculation import (
    CalculationInput,
    CalculationOutput,
    CoreCalculationInput,
    CoreCalculationOutput,
    FrequencyDependentDielectric,
)
from emmet.core.vasp.parse import DirectorySource, parse_calculation

if ARROW_COMPATIBLE:
    import pyarrow as pa

    from emmet.core.arrow import arrowize


def parse_task(fixture, suffix=None):
    with DataArchive.extract(TEST_FILES_DIR / "vasp" / f"{fixture}.json.gz") as d:
        sources = DirectorySource.from_directory(d)
        source = next(s for s in sources if suffix in (None, s.calc_suffix))
        return parse_calculation(source, "aaaaaaab").task


@pytest.fixture(scope="module")
def task():
    return parse_task("Si_static")


class TestFields:
    def test_core_task_doc_has_dropped_fields(self):
        fields = set(CoreTaskDoc.model_fields)
        assert not {"vasp_objects", "structure"} & fields
        assert set(CoreCalculationInput.model_fields) == set(
            CalculationInput.model_fields
        ) - {"lattice_rec"}
        assert not {"density", "dielectric_properties"} & set(
            CoreCalculationOutput.model_fields
        )
        assert (
            CoreTaskDoc.model_fields["input"].annotation == CoreCalculationInput | None
        )
        assert (
            CoreTaskDoc.model_fields["output"].annotation
            == CoreCalculationOutput | None
        )

    def test_the_full_models_keep_them(self):
        assert {"density", "dielectric_properties", "run_stats"} <= set(
            CalculationOutput.model_fields
        )
        assert "lattice_rec" in CalculationInput.model_fields
        assert {"structure", "vasp_objects"} <= set(TaskDoc.model_fields)
        assert TaskDoc.model_fields["input"].annotation == CalculationInput | None
        assert TaskDoc.model_fields["orig_inputs"].annotation == CalculationInput | None

    def test_a_calculation_input_is_a_core_input(self):
        assert issubclass(CalculationInput, CoreCalculationInput)
        assert issubclass(CalculationOutput, CoreCalculationOutput)

    def test_the_row_does_not_dump_what_it_dropped(self, task):
        dumped = task.model_dump()
        assert not {"structure", "vasp_objects"} & set(dumped)
        assert "lattice_rec" not in dumped["input"]
        assert not {"density", "dielectric_properties"} & set(dumped["output"])

    def test_the_inputs_of_a_task_are_core_inputs(self, task):
        """Not the inputs of the calculation, which hold the reciprocal lattice in memory."""
        assert type(task.input) is CoreCalculationInput
        assert not hasattr(task.input, "lattice_rec")

    def test_the_structure_is_that_of_the_output(self, task):
        assert task.structure is task.output.structure
        assert task.structure.formula == "Si2"
        assert ValidationTaskDoc(**task.model_dump()).structure == task.output.structure
        assert (
            CoreTaskDoc(
                output=None, last_updated=task.last_updated, completed_at=None
            ).structure
            is None
        )

    def test_old_documents_still_validate(self, task):
        """Documents written with the fields that were dropped have them ignored."""
        old = {
            **task.model_dump(),
            "structure": task.output.structure.as_dict(),
            "vasp_objects": {},
        }
        old["input"] = {
            **old["input"],
            "lattice_rec": task.input.structure.lattice.reciprocal_lattice.as_dict(),
        }
        old["output"] = {**old["output"], "density": 2.3, "dielectric_properties": None}
        doc = CoreTaskDoc(**old)
        assert doc.structure == task.output.structure
        assert not hasattr(doc, "vasp_objects")

    def test_task_doc_is_unchanged(self):
        """TaskDoc has what it had: the structure, the objects, and the full inputs."""
        with DataArchive.extract(TEST_FILES_DIR / "vasp" / "Si_static.json.gz") as d:
            doc = TaskDoc.from_directory(d)
        dumped = doc.model_dump()
        assert "structure" in dumped and "vasp_objects" in dumped
        assert dumped["input"]["lattice_rec"] is not None
        assert "dielectric_properties" in doc.calcs_reversed[0].output.model_dump()
        assert "density" in doc.calcs_reversed[0].output.model_dump()

    @pytest.mark.skipif(
        not ARROW_COMPATIBLE, reason="pyarrow must be installed to run this test."
    )
    def test_columns(self):
        schema = pa.schema(arrowize(CoreTaskDoc))
        assert not {"structure", "vasp_objects"} & set(schema.names)
        assert "lattice_rec" not in schema.field("input").type.names
        assert "lattice_rec" not in schema.field("orig_inputs").type.names
        assert not {"density", "dielectric_properties"} & set(
            schema.field("output").type.names
        )
        # the structure is in three places, not four
        assert "structure" in schema.field("input").type.names
        assert "structure" in schema.field("output").type.names


class TestKpoints:
    def test_explicit_kpoints_are_floats(self):
        """pymatgen has floats for explicit k-points; the column was integers, which truncated."""
        annotation = TypedKpointsDict.__annotations__["kpoints"]
        assert annotation == list[list[float]]

    @pytest.mark.skipif(
        not ARROW_COMPATIBLE, reason="pyarrow must be installed to run this test."
    )
    def test_the_k_points_of_a_line_calculation_survive_arrow(self):
        task = parse_task("r2scan_scf_line")
        kpts = task.input.kpoints.kpts
        assert len(kpts) > 100 and any(abs(x) % 1 > 0.01 for k in kpts for x in k)

        schema = pa.schema(arrowize(CoreTaskDoc))
        assert pa.types.is_floating(
            schema.field("input")
            .type.field("kpoints")
            .type.field("kpoints")
            .type.value_type.value_type
        )
        table = pa.Table.from_pylist(
            [task.model_dump(context={"format": "arrow"})], schema=schema
        )
        restored = CoreTaskDoc(**table.to_pylist(maps_as_pydicts="strict")[0])
        np.testing.assert_allclose(restored.input.kpoints.kpts, kpts)
        np.testing.assert_allclose(
            restored.input.kpoints.kpts_weights, task.input.kpoints.kpts_weights
        )

    @pytest.mark.parametrize(
        "kpoints, style",
        [
            (Kpoints.gamma_automatic((4, 4, 4)), "Gamma"),
            (Kpoints.monkhorst_automatic((3, 3, 3), (0.5, 0.5, 0.5)), "Monkhorst"),
            (Kpoints.automatic(30), "Automatic"),
        ],
    )
    def test_a_mesh_is_integers_when_read_and_written(self, kpoints, style):
        as_dict = kpoints.as_dict()
        stored = {
            **as_dict,
            "kpoints": [[float(x) for x in k] for k in as_dict["kpoints"]],
        }
        restored = kpoints_deserializer(stored)
        assert restored.style.name == style
        assert restored.kpts == kpoints.kpts
        assert all(isinstance(x, int) for k in restored.kpts for x in k)
        # and so is what is written to a KPOINTS file
        assert str(restored) == str(kpoints)

    def test_explicit_kpoints_are_not_cast(self):
        kpoints = Kpoints(
            comment="path",
            num_kpts=2,
            style="Reciprocal",
            kpts=[(0.0, 0.0, 0.0), (0.5, 0.25, 0.0)],
            kpts_weights=[1.0, 1.0],
        )
        restored = kpoints_deserializer(kpoints.as_dict())
        assert restored.kpts == [(0.0, 0.0, 0.0), (0.5, 0.25, 0.0)]
        # integer-valued explicit points are still explicit points
        whole = Kpoints(
            num_kpts=1, style="Reciprocal", kpts=[(1.0, 0.0, 0.0)], kpts_weights=[1.0]
        )
        assert kpoints_deserializer(whole.as_dict()).kpts == [(1.0, 0.0, 0.0)]


ENERGY = [0.0, 1.0, 2.0]
REAL = [[2.0, 2.0, 2.0, 0.0, 0.0, 0.0]] * 3
IMAGINARY = [[0.0, 0.5, 1.0, 0.0, 0.0, 0.0]] * 3
INVERSE = "INVERSE MACROSCOPIC DIELECTRIC TENSOR (including local field effects in RPA (Hartree))"


def vasprun_with(**dielectric_data):
    """What is read of a vasprun to store a dielectric function: its `dielectric_data`.

    Each argument is the energies, real and imaginary parts of a block, scaled so that
    the blocks can be told apart.
    """
    return SimpleNamespace(
        dielectric_data={
            label: (
                ENERGY,
                [[x * scale for x in row] for row in REAL],
                [[x * scale for x in row] for row in IMAGINARY],
            )
            for label, scale in dielectric_data.items()
        }
    )


class TestFrequencyDependentDielectric:
    """The dielectric function stored is that which pymatgen derives the absorption from."""

    @pytest.mark.parametrize(
        "blocks, stored",
        [
            ({"density": 1.0}, 1.0),
            ({"density": 1.0, "velocity": 3.0}, 1.0),
            ({"freq_dependent": 2.0}, 2.0),
            ({"density": 1.0, "freq_dependent": 2.0}, 2.0),
        ],
    )
    def test_the_block_is_the_one_of_the_absorption_coefficient(self, blocks, stored):
        vasprun = vasprun_with(**blocks)
        dielectric = FrequencyDependentDielectric.from_vasprun(vasprun)
        assert dielectric.energy == ENERGY
        assert dielectric.real == [[x * stored for x in row] for row in REAL]
        assert dielectric.imaginary == [[x * stored for x in row] for row in IMAGINARY]
        # and the coefficient pymatgen gives is of those values
        coefficient = Vasprun.optical_absorption_coeff.fget(vasprun)
        assert coefficient is not None
        real = [sum(row[:3]) / 3 for row in dielectric.real]
        imaginary = [sum(row[:3]) / 3 for row in dielectric.imaginary]
        reference = Vasprun.optical_absorption_coeff.fget(
            SimpleNamespace(
                dielectric_data={
                    "density": (
                        ENERGY,
                        [[r] * 3 for r in real],
                        [[i] * 3 for i in imaginary],
                    )
                }
            )
        )
        np.testing.assert_allclose(coefficient, reference)

    @pytest.mark.parametrize(
        "blocks",
        [{}, {INVERSE: 1.0}, {"velocity": 1.0}, {INVERSE: 1.0, "velocity": 2.0}],
    )
    def test_there_is_none_without_one(self, blocks):
        """The inverse of a dielectric function is not one, and there is no absorption from it."""
        vasprun = vasprun_with(**blocks)
        assert FrequencyDependentDielectric.from_vasprun(vasprun) is None
        assert Vasprun.optical_absorption_coeff.fget(vasprun) is None


def test_a_pymatgen_whose_coefficient_needs_a_density_block(monkeypatch):
    """Some versions of pymatgen raise a KeyError for the coefficient of a vasprun with no dielectric function."""

    def older(self):
        data = self.dielectric_data
        diel_data = data.get("freq_dependent") or data["density"]
        return list(diel_data[0])

    monkeypatch.setattr(Vasprun, "optical_absorption_coeff", property(older))
    with DataArchive.extract(TEST_FILES_DIR / "vasp" / "Si_static.json.gz") as d:
        (source,) = DirectorySource.from_directory(d)
        parsed = parse_calculation(source, "aaaaaaab")
    assert parsed.errors == []
    assert parsed.task.output.frequency_dependent_dielectric is None
    assert parsed.task.output.optical_absorption_coeff is None


class TestAbsorptionCoefficient:
    def test_it_is_none_without_a_dielectric(self, task):
        assert task.output.frequency_dependent_dielectric is None
        assert task.output.optical_absorption_coeff is None
