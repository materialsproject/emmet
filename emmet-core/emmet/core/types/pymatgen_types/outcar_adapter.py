from typing_extensions import TypedDict, NotRequired

from emmet.core.math import Matrix3D


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
        # `zval_dict` and `p_elec` are only required for ferroelectric stuff in atomate2
        "zval_dict": NotRequired[dict[str, float] | None],
        "p_elec": NotRequired[tuple[float, float, float] | None],
        # `born` is needed for phonon workflows
        "born": NotRequired[list[Matrix3D] | None],
    },
)

# would be nice to figure out a constructor for a pmg Outcar from a dict input

# OutcarTypeVar = TypeVar("OutcarTypeVar", Outcar, TypedOutcarDict)

# OutcarType = Annotated[
#     OutcarTypeVar,
#     BeforeValidator(lambda x: Outcar(**x) if isinstance(x, dict) else x),
#     WrapSerializer(lambda x, nxt, info: x.as_dict(), return_type=TypedOutcarDict),
# ]

OutcarType = TypedOutcarDict
