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


setattr(
    pymatgen.analysis.reaction_calculator.BalancedReaction,
    "__type_adapter__",
    BalancedReactionAdapter,
)
