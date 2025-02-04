import pymatgen.analysis.reaction_calculator
from pydantic import RootModel
from typing_extensions import TypedDict

TypedBalancedReaction = TypedDict(
    "TypedBalancedReaction",
    {
        "@module": str,
        "@class": str,
        "reactants": dict[str, float],
        "products": dict[str, float],
    },
)


class BalancedReactionAdapter(RootModel):
    root: TypedBalancedReaction


pymatgen.analysis.reaction_calculator.BalancedReaction.__pydantic_model__ = (
    BalancedReactionAdapter
)
