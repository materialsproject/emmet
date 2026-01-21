from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from emmet.core.tasks import _VOLUMETRIC_FILES, TaskDoc
from emmet.core.types.pymatgen_types.defect_adapter import DefectType

if TYPE_CHECKING:
    from pathlib import Path
    from typing import Any


class DefectInfo(BaseModel):
    """Information related to a point defect."""

    defect_name: str = Field(
        title="The name of the defect",
    )

    bulk_formula: str = Field(
        title="Bulk Formula",
        description="Formula of the bulk structure.",
    )

    defect: DefectType = Field(
        title="Defect Object",
        description="Unit cell representation of the defect object.",
    )

    charge_state: int | None = Field(
        None,
        title="Charge State",
        description="Charge state of the defect.",
    )

    supercell_matrix: list[list[int, int, int]] | None = Field(  # type: ignore[type-arg]
        None,
        title="Supercell Matrix",
        description="Supercell matrix used to construct the defect supercell.",
    )


class DefectTaskDoc(DefectInfo, TaskDoc):
    """Defect Task Document.

    Contains all the task-level information for a defect supercell calculation.
    """

    @classmethod
    def from_directory(
        cls,
        dir_name: Path | str,
        volumetric_files: tuple[str, ...] = _VOLUMETRIC_FILES,
        additional_fields: dict[str, Any] | None = None,
        volume_change_warning_tol: float = 0.2,
        defect_info_key: str = "info",
        **vasp_calculation_kwargs,
    ) -> TaskDoc:
        """
        Create a task document from a directory containing VASP files.

        Parameters
        ----------
        dir_name
            The path to the folder containing the calculation outputs.
        store_additional_json
            Whether to store additional json files found in the calculation directory.
        volumetric_files
            Volumetric files to search for.
        additional_fields
            Dictionary of additional fields to add to output document.
        volume_change_warning_tol
            Maximum volume change allowed in VASP relaxations before the calculation is
            tagged with a warning.
        defect_info_key
            The key in the `additional_json` to extract the defect information from
        **vasp_calculation_kwargs
            Additional parsing options that will be passed to the
            :obj:`.Calculation.from_vasp_files` function.

        Returns
        -------
        TaskDoc
            A task document for the calculation.
        """
        tdoc = TaskDoc.from_directory(
            dir_name=dir_name,
            volumetric_files=volumetric_files,
            store_additional_json=True,
            additional_fields=additional_fields,
            volume_change_warning_tol=volume_change_warning_tol,
            **vasp_calculation_kwargs,
        )
        return cls.from_taskdoc(tdoc, defect_info_key=defect_info_key)

    @classmethod
    def from_taskdoc(
        cls,
        taskdoc: TaskDoc,
        defect_info_key: str = "info",
    ) -> DefectTaskDoc:
        """
        Create a DefectTaskDoc from a TaskDoc

        Args:
            taskdoc: TaskDoc to convert
            defect_info_key: The key in the `additional_json`
                to extract the defect information from

        Returns:
            DefectTaskDoc
        """
        additional_info = taskdoc.additional_json[defect_info_key]
        defect = additional_info["defect"]
        charge_state = additional_info["charge_state"]
        defect_name = additional_info["defect_name"]
        bulk_formula = additional_info["bulk_formula"]
        supercell_matrix = additional_info["sc_mat"]

        task_dict = taskdoc.model_dump()
        task_dict.update(
            {
                "defect_name": defect_name,
                "defect": defect,
                "charge_state": charge_state,
                "bulk_formula": bulk_formula,
                "supercell_matrix": supercell_matrix,
            }
        )

        return cls(**task_dict)
