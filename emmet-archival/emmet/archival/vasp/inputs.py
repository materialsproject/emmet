"""Define archival formats for VASP inputs."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from pymatgen.core import Structure
from pymatgen.io.vasp.inputs import Incar, Poscar

from emmet.archival.base import Archiver, StructureArchive

if TYPE_CHECKING:
    import h5py
    import zarr


@dataclass
class PoscarArchive(StructureArchive):
    """Archive a POSCAR."""

    # parsed_objects: dict[str, Any] = field(default_factory=lambda: {"POSCAR": None})

    def __post_init__(self):
        if isinstance(self.parsed_objects["POSCAR"], Structure):
            self.parsed_objects["POSCAR"] = Poscar(
                structure=self.parsed_objects["POSCAR"]
            )
        elif (
            isinstance(self.parsed_objects["POSCAR"], (str, Path))
            and Path(self.parsed_objects["POSCAR"]).exists()
        ):
            self.parsed_objects["POSCAR"] = Poscar.from_file(
                self.parsed_objects["POSCAR"]
            )
        elif isinstance(self.parsed_objects["POSCAR"], str):
            self.parsed_objects["POSCAR"] = Poscar.from_str(
                self.parsed_objects["POSCAR"]
            )

        self.metadata.update({"comment": self.parsed_objects["POSCAR"]["comment"]})

        super().__post_init__()

    @staticmethod
    def from_group(group: h5py.Group | zarr.Group) -> Poscar:  # type: ignore[override]
        return Poscar(StructureArchive.from_group(group), comment=group.get("comment"))


@dataclass
class IncarArchive(Archiver):
    # parsed_objects : dict[str,Any] = {"INCAR": None}

    def __post_init__(self) -> None:
        if (
            isinstance(self.parsed_objects["INCAR"], (str, Path))
            and Path(self.parsed_objects["INCAR"]).exists()
        ):
            self.parsed_objects["INCAR"] = Incar.from_file(self.parsed_objects["INCAR"])
        elif isinstance(self.parsed_objects["INCAR"], str):
            self.parsed_objects["INCAR"] = Incar.from_str(self.parsed_objects["INCAR"])

        super().__post_init__()

    def to_group(self, group: h5py.Group, group_key: str = "INCAR") -> None:
        group.create_group(group_key)
        group.attrs.update(self.incar)

    @staticmethod
    def from_group(group: h5py.Group | zarr.Group) -> Incar:
        return Incar(group["INCAR"].attrs)
