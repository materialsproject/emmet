from typing_extensions import TypedDict

from emmet.core.math import Vector3D


class TypedSiteProperitesDict(TypedDict):
    magmom: float
    charge: float
    velocities: Vector3D
    selective_dynamics: tuple[bool, bool, bool]
    coordination_no: int
    forces: list[float, float, float]


class TypedAggregateProperitesDict(TypedDict):
    magmom: list[float]
    charge: list[float]
    velocities: list[Vector3D]
    selective_dynamics: list[tuple[bool, bool, bool]]
