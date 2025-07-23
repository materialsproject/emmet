from pydantic import BaseModel, Field

__all__ = ["Component", "ExtractedMaterial"]


class Component(BaseModel):
    formula: str = Field(..., description="Formula of this component.")
    amount: str = Field(..., description="Amount of this component.")
    elements: dict[str, str] = Field(
        ..., description="Amount of each chemical elements in this component."
    )


class Values(BaseModel):
    values: list[float] | None = Field(None, description="list of values.")
    min_value: float | None = Field(None, description="Minimal value.")
    max_value: float | None = Field(None, description="Maximal value.")


class ExtractedMaterial(BaseModel):
    """
    Model for a material extracted from the literature
    """

    material_string: str = Field(
        ..., description="String of the material as written in paper."
    )
    material_formula: str = Field(
        ..., description="Normalized formula of the material."
    )
    material_name: str | None = Field(None, description="English name of the material.")

    phase: str | None = Field(
        None, description="Phase description of material, such as anatase."
    )
    is_acronym: bool | None = Field(
        None, description="Whether the material is an acronym, such as LMO for LiMn2O4."
    )

    composition: list[Component] = Field(
        ..., description="List of components in this material."
    )
    amounts_vars: dict[str, Values] = Field(
        {}, description="Amount variables (formula subscripts)."
    )
    elements_vars: dict[str, list[str]] = Field(
        {}, description="Chemical element variables"
    )

    additives: list[str] = Field([], description="list of additives, dopants, etc.")
    oxygen_deficiency: str | None = Field(
        None, description="Symbol indicating whether the materials is oxygen deficient."
    )
