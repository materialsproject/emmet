from emmet.core.tasks import _VOLUMETRIC_FILES, CoreTaskDoc
from emmet.core.types.typing import IdentifierType
from pydantic import Field
from pymatgen.core.structure import Structure
from pathlib import Path
import json
from typing_extensions import Self
from typing import Any
from emmet.core.trajectory import RelaxTrajectory

def parse_json(dir_name: Path | str) -> dict:
    dir_path = Path(dir_name)
    json_file = dir_path / "disordered_task_doc_metadata.json"
    if not json_file.exists():
        raise FileNotFoundError(f"No disordered_task_doc_metadata.json found in directory: {dir_name}")

    with open(json_file, 'r') as f:
        data = json.load(f)
    return data


class DisorderedTaskDoc(CoreTaskDoc):
    """Document for a disordered structure task, extending the CoreTaskDoc with additional metadata to 
    capture disorder-specific information and its relationship to the ordered structure."""

    ordered_task_id: IdentifierType = Field(
        ...,
        description="The task ID of the ordered structure task from which this disordered structure was generated.",
    )
    reference_structure: Structure = Field(
        ...,
        description="The reference disordered structure used to start relaxation and represent this disordered structure in the cluster expansion.",
    )
    supercell_diag: tuple[int, int, int] = Field(
        ...,
        description="The supercell diagonal used to generate this disordered structure from the prototype structure.",
    )
    prototype: str = Field(
        ...,
        description="The prototype name from which this disordered structure was generated.",
    )
    prototype_params: dict = Field(
        ...,
        description="The parameters used to generate the prototype structure.",
    )
    composition_map: dict[str, dict[str, int]] = Field(
        ...,
        description="A mapping of which elements are in each sublattice for the disordered structure.",
    )
    versions: dict[str, str] = Field(
        ...,
        description="A dictionary capturing the versions of relevant software packages used during the calculation.",
    )

    @classmethod
    def from_directory(
        cls,
        dir_name: Path | str,
        volumetric_files: tuple[str, ...] = _VOLUMETRIC_FILES,
        **vasp_calculation_kwargs,
    ) -> tuple[Self, RelaxTrajectory]:
        base_doc, trajectory = CoreTaskDoc.from_directory(
            dir_name,
            volumetric_files=volumetric_files,
            **vasp_calculation_kwargs,
        )

        metadata = parse_json(dir_name)

        data: dict[str, Any] = base_doc.model_dump()
        data.update(
            ordered_task_id=metadata["ordered_task_id"],
            reference_structure=Structure.from_dict(metadata["reference_structure"]),
            supercell_diag=tuple(metadata["supercell_diag"]),
            prototype=metadata["prototype"],
            prototype_params=metadata["prototype_params"],
            composition_map=metadata["composition_map"],
            versions=metadata["versions"],
        )

        return (cls.model_validate(data), trajectory)
