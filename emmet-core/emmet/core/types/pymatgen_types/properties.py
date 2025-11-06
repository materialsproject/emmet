from typing_extensions import NotRequired, TypedDict

from emmet.core.math import Vector3D


class TypedSiteProperitesDict(TypedDict):
    magmom: NotRequired[float | None]
    charge: NotRequired[float | None]
    velocities: NotRequired[Vector3D | None]
    selective_dynamics: NotRequired[tuple[bool, bool, bool] | None]
    coordination_no: NotRequired[int | None]
    forces: NotRequired[list[float, float, float] | None]  # type: ignore[type-arg]


class TypedAggregateProperitesDict(TypedDict):
    magmom: NotRequired[list[float] | None]
    charge: NotRequired[list[float] | None]
    velocities: NotRequired[list[Vector3D] | None]
    selective_dynamics: NotRequired[list[tuple[bool, bool, bool]] | None]
