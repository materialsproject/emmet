from pydantic import Field, BaseModel


class FormulaAutocomplete(BaseModel):
    """
    Class defining formula autocomplete return data
    """

    formula_pretty: str = Field(
        None,
        description="Human readable chemical formula.",
    )
