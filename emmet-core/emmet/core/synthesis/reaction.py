from pydantic import BaseModel, Field

__all__ = [
    "FormulaPart",
    "ReactionFormula",
]


class FormulaPart(BaseModel):
    amount: str = Field("1", description="Amount of the compound in a formula.")
    material: str = Field(
        ..., description="The compound that participates in a reaction."
    )


class ReactionFormula(BaseModel):
    """
    Model for a balanced reaction
    """

    left_side: list[FormulaPart] = Field(
        ..., description="List of materials and their amounts at the left side."
    )
    right_side: list[FormulaPart] = Field(
        ..., description="List of materials and their amounts at the right side."
    )

    # For example, BaCO3 + MO2 == BaMO3, element_substitution = {"M": "Ti"}
    element_substitution: dict[str, str] = Field(
        {}, description="Dictionary that contains elemental substitutions"
    )
