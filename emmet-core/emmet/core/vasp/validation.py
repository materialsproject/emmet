"""Current MP tools to validate VASP calculations."""

from __future__ import annotations

from datetime import datetime
from pydantic import Field, field_validator

from emmet.core.vasp.calculation import Calculation
from emmet.core.base import EmmetBaseModel
from emmet.core.common import convert_datetime
from emmet.core.mpid import MPID
from emmet.core.utils import utcnow
from emmet.core.vasp.utils import FileMetadata
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


class ValidationDoc(VaspValidator, EmmetBaseModel):
    """
    Validation document for a VASP calculation
    """

    task_id: MPID | None = Field(
        None, description="The task_id for this validation document"
    )

    last_updated: datetime = Field(
        description="The most recent time when this document was updated.",
        default_factory=utcnow,
    )

    @field_validator("last_updated", mode="before")
    @classmethod
    def handle_datetime(cls, v):
        return convert_datetime(cls, v)

    @classmethod
    def from_file_metadata(cls, file_meta: list[FileMetadata], **kwargs) -> Self:
        """Validate files from a list of their metadata."""
        vasp_file_paths: dict[str, Path] = {}
        for f in file_meta:
            if (
                len(matched_files := [vf for vf in REQUIRED_VASP_FILES if vf in f.name])
                > 0
            ):
                vasp_file_paths[matched_files[0]] = f.path
        return cls.from_vasp_input(cls, vasp_file_paths, **kwargs)

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

        return VaspFiles(
            user_input=VaspInputSafe(
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
            vasprun=LightVasprun(
                vasp_version=final_calc.vasp_version,
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
        return cls.from_vasp_input(vasp_files=vasp_files, **kwargs)
