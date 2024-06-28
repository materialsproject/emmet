from __future__ import annotations

from pydantic import Field

from emmet.core.tasks import TaskDoc, _VOLUMETRIC_FILES
from typing import TYPE_CHECKING
from pymatgen.analysis.defects.core import Defect
from monty.json import MontyDecoder

if TYPE_CHECKING:
    from typing import Any, Dict, Optional, Tuple, Union
    from pathlib import Path

mdecoder = MontyDecoder().process_decoded


class DefectTaskDoc(TaskDoc, extra="allow"):
    """Defect Task Document"""

    defect_name: str = Field(
        None,
        title="The name of the defect",
    )

    defect: Defect = Field(
        None,
        title="Defect Object",
        description="Unit cell representation of the defect object.",
    )

    charge_state: int = Field(
        None,
        title="Charge State",
        description="Charge state of the defect.",
    )

    supercell_matrix: list = Field(
        None,
        title="Supercell Matrix",
        description="Supercell matrix used to construct the defect supercell.",
    )

    @classmethod
    def from_directory(
        cls,
        dir_name: Union[Path, str],
        volumetric_files: Tuple[str, ...] = _VOLUMETRIC_FILES,
        additional_fields: Optional[Dict[str, Any]] = None,
        volume_change_warning_tol: float = 0.2,
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
        **vasp_calculation_kwargs
            Additional parsing options that will be passed to the
            :obj:`.Calculation.from_vasp_files` function.

        Returns
        -------
        TaskDoc
            A task document for the calculation.
        """
        doc = super().from_directory(
            dir_name=dir_name,
            volumetric_files=volumetric_files,
            store_additional_json=True,
            additional_fields=additional_fields,
            volume_change_warning_tol=volume_change_warning_tol,
            **vasp_calculation_kwargs,
        )
        defect_doc = doc.model_copy(update=additional_fields)
        defect_doc.defect = mdecoder(
            defect_doc.additional_json.get("info", {}).get("defect", None)
        )
        defect_doc.charge_state = defect_doc.additional_json.get("info", {}).get(
            "charge_state", None
        )
        return defect_doc
