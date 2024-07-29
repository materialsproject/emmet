"""Schemas for classical MD package."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from typing_extensions import Annotated
import zlib
from typing import Any

from pydantic import (
    BaseModel,
    Field,
    PlainValidator,
    PlainSerializer,
    WithJsonSchema,
    errors,
)
from monty.json import MSONable

from emmet.core.vasp.task_valid import TaskState  # type: ignore[import-untyped]


def hex_bytes_validator(o: Any) -> bytes:
    if isinstance(o, bytes):
        return o
    elif isinstance(o, bytearray):
        return bytes(o)
    elif isinstance(o, str):
        return zlib.decompress(bytes.fromhex(o))
    raise errors.BytesError()


def hex_bytes_serializer(b: bytes) -> str:
    return zlib.compress(b).hex()


HexBytes = Annotated[
    bytes,
    PlainValidator(hex_bytes_validator),
    PlainSerializer(hex_bytes_serializer),
    WithJsonSchema({"type": "string"}),
]


@dataclass
class MoleculeSpec(MSONable):
    """A molecule schema to be output by OpenMMGenerators."""

    name: str
    count: int
    charge_scaling: float
    charge_method: str
    openff_mol: str  # a tk.Molecule object serialized with to_json


class ClassicalMDTaskDocument(BaseModel, extra="allow"):  # type: ignore[call-arg]
    """Definition of the OpenMM task document."""

    tags: Optional[list[str]] = Field(
        [], title="tag", description="Metadata tagged to a given task."
    )

    dir_name: Optional[str] = Field(None, description="The directory for this MD task")

    state: Optional[TaskState] = Field(None, description="State of this calculation")

    calcs_reversed: Optional[list] = Field(
        None,
        title="Calcs reversed data",
        description="Detailed data for each MD calculation contributing to "
        "the task document.",
    )

    interchange: Optional[HexBytes] = Field(
        None,
        description="A byte serialized OpenFF interchange object. "
        "To generate, the Interchange is serialized to json and"
        "the json is transformed to bytes with a utf-8 encoding. ",
    )

    molecule_specs: Optional[list[MoleculeSpec]] = Field(
        None, description="Molecules within the system."
    )

    force_field: Optional[str] = Field(None, description="The classical MD forcefield.")

    task_type: Optional[str] = Field(None, description="The type of calculation.")

    # task_label: Optional[str] = Field(None, description="A description of the task")
    # TODO: where does task_label get added

    last_updated: Optional[datetime] = Field(
        None,
        description="Timestamp for the most recent calculation for this task document",
    )
