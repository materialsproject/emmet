from typing import Annotated, TypeVar

from pydantic import BeforeValidator, WrapSerializer
from pymatgen.analysis.reaction_calculator import BalancedReaction
from typing_extensions import TypedDict

TypedBalancedReactionDict = TypedDict(
    "TypedBalancedReactionDict",
    {
        "@module": str,
        "@class": str,
        "reactants": dict[str, float],
        "products": dict[str, float],
    },
)

BalancedReactionTypeVar = TypeVar(
    "BalancedReactionTypeVar", BalancedReaction, TypedBalancedReactionDict
)

BalancedReactionType = Annotated[
    BalancedReactionTypeVar,
    BeforeValidator(
        lambda x: BalancedReaction.from_dict(x) if isinstance(x, dict) else x
    ),
    WrapSerializer(
        lambda x, nxt, info: x.as_dict(), return_type=TypedBalancedReactionDict
    ),
]
