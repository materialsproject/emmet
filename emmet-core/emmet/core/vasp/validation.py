"""Current MP tools to validate VASP calculations."""

from __future__ import annotations

from pydantic import Field

from emmet.core.vasp.calculation import Calculation
from emmet.core.base import EmmetBaseModel
from emmet.core.types.typing import DateTimeType, IdentifierType
from emmet.core.types.enums import DocEnum
from emmet.core.vasp.calc_types.enums import CalcType, RunType
from emmet.core.vasp.utils import FileMetadata, discover_vasp_files
from emmet.core.vasp.task_valid import TaskDocument

from pymatgen.io.vasp import Incar

from pymatgen.io.validation.common import (
    LightOutcar,
    LightVasprun,
    PotcarSummaryStats,
    VaspFiles,
    VaspInputSafe,
)
from pymatgen.io.validation.validation import REQUIRED_VASP_FILES, VaspValidator

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path
    from typing_extensions import Self
    from emmet.core.tasks import TaskDoc


class DeprecationMessage(DocEnum):
    MANUAL = "M", "Manual deprecation"
    SYMMETRY = (
        "S001",
        "Could not determine crystalline space group, needed for input set check.",
    )
    KPTS = "C001", "Too few KPoints"
    KSPACING = "C002", "KSpacing not high enough"
    ENCUT = "C002", "ENCUT too low"
    FORCES = "C003", "Forces too large"
    MAG = "C004", "At least one site magnetization is too large"
    POTCAR = (
        "C005",
        "At least one POTCAR used does not agree with the pymatgen input set",
    )
    CONVERGENCE = "E001", "Calculation did not converge"
    MAX_SCF = "E002", "Max SCF gradient too large"
    LDAU = "I001", "LDAU Parameters don't match the inputset"
    SET = ("I002", "Cannot validate due to missing or problematic input set")
    UNKNOWN = "U001", "Cannot validate due to unknown calc type"


class ValidationDoc(VaspValidator, EmmetBaseModel):
    """
    Validation document for a VASP calculation
    """

    task_id: IdentifierType | None = Field(
        None, description="The task_id for this validation document"
    )

    last_updated: DateTimeType = Field(
        description="The most recent time when this document was updated.",
    )

    nelements: int | None = Field(None, description="Number of elements.")
    symmetry_number: int | None = Field(
        None,
        title="Space Group Number",
        description="The spacegroup number for the lattice.",
    )
    run_type: RunType | None = Field(
        None, description="The run type of the calculation"
    )
    calc_type: CalcType | None = Field(None, description="The calculation type.")

    @classmethod
    def from_file_metadata(cls, file_meta: list[FileMetadata], **kwargs) -> Self:
        """Validate files from a list of their metadata."""
        vasp_file_paths: dict[str, Path] = {}
        for f in file_meta:
            if (
                len(matched_files := [vf for vf in REQUIRED_VASP_FILES if vf in f.name])
                > 0
            ):
                vasp_file_paths[matched_files[0].lower().split(".")[0]] = f.path
        return cls.from_vasp_input(vasp_file_paths=vasp_file_paths, **kwargs)

    @staticmethod
    def task_doc_to_vasp_files(task_doc: TaskDoc | TaskDocument) -> VaspFiles:
        """Convert an emmet.core TaskDoc or legacy TaskDocument to VaspFiles."""

        if isinstance(task_doc, TaskDocument):
            final_calc = Calculation(**task_doc.calcs_reversed[0])
        else:
            final_calc = task_doc.calcs_reversed[0]

        potcar_stats = None
        if final_calc.input.potcar_spec:
            potcar_stats = [
                PotcarSummaryStats(
                    titel=ps.titel,
                    keywords=ps.summary_stats["keywords"] if ps.summary_stats else None,
                    stats=ps.summary_stats["stats"] if ps.summary_stats else None,
                    lexch=(
                        "pe" if final_calc.input.potcar_type[0] == "PAW_PBE" else "ca"
                    ),
                )
                for ps in final_calc.input.potcar_spec
            ]

        # Issue with legacy data: VASP version can include date info - remove here
        vasp_version = None
        if len(split_vasp_ver := final_calc.vasp_version.split(".")) > 0:
            vasp_version = ".".join(split_vasp_ver[: min(3, len(split_vasp_ver))])

        return VaspFiles(
            user_input=VaspInputSafe(  # type: ignore[call-arg]
                incar=Incar(final_calc.input.incar),
                kpoints=final_calc.input.kpoints,
                structure=final_calc.input.structure,
                potcar=potcar_stats,
            ),
            outcar=LightOutcar(
                **{
                    k: final_calc.output.outcar.get(k)
                    for k in ("drift", "magnetization")
                }
            ),
            vasprun=LightVasprun(  # type: ignore[call-arg]
                vasp_version=vasp_version,  # type: ignore[arg-type]
                ionic_steps=[
                    ionic_step.model_dump()
                    for ionic_step in final_calc.output.ionic_steps
                ],
                final_energy=task_doc.output.energy,
                final_structure=task_doc.output.structure,
                kpoints=final_calc.input.kpoints,
                parameters=final_calc.input.parameters,
                bandgap=final_calc.output.bandgap,
            ),
        )

    @classmethod
    def from_task_doc(cls, task_doc: TaskDoc | TaskDocument, **kwargs) -> Self:
        """Validate a VASP calculation represented by an emmet.core TaskDoc/ument."""
        vasp_files = cls.task_doc_to_vasp_files(task_doc)

        for k in ("run_type", "calc_type"):
            if not kwargs.get(k):
                kwargs[k] = getattr(task_doc, k, None)

        if not kwargs.get("symmetry_number") and task_doc.symmetry:
            kwargs["symmetry_number"] = task_doc.symmetry.number

        return cls.from_vasp_input(vasp_files=vasp_files, **kwargs)

    @classmethod
    def from_directory(cls, dir_name: str | Path, **kwargs) -> Self:
        """Override parent model to use file discovery method."""
        vasp_files = discover_vasp_files(dir_name)

        # NB: this will pick "standard" over "relax*" if present,
        # and will select the last "relax*" if those are the only
        # types present
        final_calc_name = sorted(vasp_files)[-1]
        return cls.from_file_metadata(vasp_files[final_calc_name], **kwargs)
