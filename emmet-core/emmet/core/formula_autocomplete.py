from pydantic import BaseModel, Field


class FormulaAutocomplete(BaseModel):
    """
    Class defining formula autocomplete return data
    """

    formula_pretty: str | None = Field(
        None,
        description="Human readable chemical formula.",
    )
