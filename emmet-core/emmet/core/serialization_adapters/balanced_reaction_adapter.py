from typing import TypeVar

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
