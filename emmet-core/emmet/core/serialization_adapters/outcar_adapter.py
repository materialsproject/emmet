from typing import NotRequired

from typing_extensions import TypedDict


class TypedPerIonProps(TypedDict):
    s: float
    p: float
    d: float
    tot: float


TypedOutcarDict = TypedDict(
    "TypedOutcarDict",
    {
        "@module": str,
        "@class": str,
        "efermi": NotRequired[float | None],
        "magnetization": NotRequired[tuple[TypedPerIonProps, ...] | None],
        "charge": NotRequired[tuple[TypedPerIonProps, ...] | None],
        "total_magnetization": NotRequired[float | None],
        "nelect": NotRequired[float | None],
        "is_stopped": NotRequired[bool | None],
        "drift": NotRequired[list[list[float]] | None],
        "ngf": NotRequired[list[int] | None],
        "sampling_radii": NotRequired[list[float] | None],
        "electrostatic_potential": NotRequired[list[float] | None],
    },
)
