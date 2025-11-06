from typing import Annotated, TypeVar

from pydantic import BeforeValidator, WrapSerializer
from pymatgen.core.trajectory import Trajectory
from typing_extensions import TypedDict

from emmet.core.math import Matrix3D, Vector3D
from emmet.core.types.pymatgen_types.properties import TypedAggregateProperitesDict


class FrameProps(TypedDict):
    energy: float


TypedTrajectoryDict = TypedDict(
    "TypedTrajectoryDict",
    {
        "@module": str,
        "@class": str,
        "species": list[str],
        "coords": list[list[Vector3D]],
        "charge": float,
        "spin_multiplicity": float,
        "lattice": list[Matrix3D],
        "site_properties": TypedAggregateProperitesDict,
        "frame_properties": FrameProps,
        "constant_lattice": bool,
        "time_step": float,
        "coords_are_displacement": bool,
        "base_positions": list[Vector3D],
    },
)

TrajectoryTypeVar = TypeVar("TrajectoryTypeVar", Trajectory, TypedTrajectoryDict)

TrajectoryType = Annotated[
    TrajectoryTypeVar,
    BeforeValidator(lambda x: Trajectory.from_dict(x) if isinstance(x, dict) else x),
    WrapSerializer(lambda x, nxt, info: x.as_dict(), return_type=TypedTrajectoryDict),
]
