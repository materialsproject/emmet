from pydantic import BaseModel, Field
from emmet.core.types.enums import ValueEnum


class Value(BaseModel):
    min_value: float | None = Field(None, description="Minimal value.")
    max_value: float | None = Field(None, description="Maximal value.")
    values: list[float] = Field([], description="Enumerated values in the literature.")
    units: str = Field(..., description="Unit of this value.")


class Conditions(BaseModel):
    heating_temperature: list[Value] | None = Field(
        None, description="Heating temperatures."
    )
    heating_time: list[Value] | None = Field(None, description="Heating times.")
    heating_atmosphere: list[str] | None = Field(
        None, description="List of heating atmospheres."
    )
    mixing_device: str | None = Field(
        None, description="Mixing device, if this operation is MIXING."
    )
    mixing_media: str | None = Field(
        None, description="Mixing media, if this operation is MIXING."
    )


class OperationTypeEnum(str, ValueEnum):
    starting = "StartingSynthesis"
    mixing = "MixingOperation"
    shaping = "ShapingOperation"
    drying = "DryingOperation"
    heating = "HeatingOperation"
    quenching = "QuenchingOperation"


class Operation(BaseModel):
    type: OperationTypeEnum = Field(
        ..., description="Type of the operation as classified by the pipeline."
    )
    token: str = Field(
        ..., description="Token (word) of the operation as written in paper."
    )
    conditions: Conditions = Field(
        ..., description="The conditions linked to this operation."
    )
