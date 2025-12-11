from emmet.core.tasks import _VOLUMETRIC_FILES, CoreTaskDoc
from emmet.core.types.typing import IdentifierType
from emmet.core.types.pymatgen_types.structure_adapter import StructureType
from emmet.core.trajectory import RelaxTrajectory
from pydantic import Field
from pymatgen.core.structure import Structure
from pathlib import Path
import json
from typing_extensions import TypedDict, Self
from typing import Any

REQUIRED_METADATA_KEYS: tuple[str, ...] = (
    "ordered_task_id",
    "reference_structure",
    "supercell_diag",
    "prototype",
    "prototype_params",
    "composition_map",
    "versions",
)


class TypedDisorderedTaskMetadata(TypedDict):
    ordered_task_id: IdentifierType
    reference_structure: dict[str, Any]
    supercell_diag: tuple[int, int, int]
    prototype: str
    prototype_params: dict[str, float]
    composition_map: dict[str, dict[str, int]]
    versions: dict[str, str]


def parse_json(dir_name: Path | str) -> TypedDisorderedTaskMetadata:
    """Parse the disordered_task_doc_metadata.json file from the given directory."""
    dir_path = Path(dir_name)
    json_file = dir_path / "disordered_task_doc_metadata.json"

    if not json_file.exists():
        raise FileNotFoundError(
            f"No disordered_task_doc_metadata.json found in directory: {dir_name}"
        )

    with json_file.open("r") as f:
        data = json.load(f)

    missing_keys = [key for key in REQUIRED_METADATA_KEYS if key not in data]
    if missing_keys:
        missing_str = ", ".join(missing_keys)
        raise ValueError(
            f"Missing required keys in disordered_task_doc_metadata.json: {missing_str}"
        )

    supercell_x, supercell_y, supercell_z = data["supercell_diag"]
    data["supercell_diag"] = (supercell_x, supercell_y, supercell_z)
    return data


class DisorderedTaskDoc(CoreTaskDoc):
    """Document for a disordered structure task, extending the CoreTaskDoc with additional metadata to
    capture disorder-specific information and its relationship to the ordered structure.
    """

    ordered_task_id: IdentifierType = Field(
        ...,
        description="The task ID of the ordered structure task from which this disordered structure was generated.",
    )
    reference_structure: StructureType = Field(
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
    prototype_params: dict[str, float] = Field(
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

        data = base_doc.model_dump()
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
