import pymatgen.core.trajectory
from pydantic import RootModel
from typing_extensions import TypedDict

from emmet.core.math import Matrix3D, Vector3D


class SiteProps(TypedDict):
    magmom: list[float]
    charge: float
    velocities: Vector3D
    selective_dynamics: tuple[bool, bool, bool]


class FrameProps(TypedDict):
    energy: float


TypedTrajectory = TypedDict(
    "TypedTrajectory",
    {
        "@module": str,
        "@class": str,
        "species": list[str],
        "coords": list[list[Vector3D]],
        "charge": float,
        "spin_multiplicity": float,
        "lattice": list[Matrix3D],
        "site_properties": SiteProps,
        "frame_properties": FrameProps,
        "constant_lattice": bool,
        "time_step": float,
        "coords_are_displacement": bool,
        "base_positions": list[Vector3D],
    },
)


class TrajectoryAdapter(RootModel):
    root: TypedTrajectory


pymatgen.core.trajectory.Trajectory.__pydantic_model__ = TrajectoryAdapter
