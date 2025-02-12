"""Archival class definitions independent of data type."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import h5py
import numpy as np
from numcodecs import Blosc
import zarr

from pymatgen.core import Structure

from emmet.archival.utils import StrEnum

if TYPE_CHECKING:
    from typing import Any
    from typing_extensions import Self


class ArchivalFormat(StrEnum):
    HDF5 = "h5"
    ZARR = "zarr"


@dataclass
class Archiver:
    """Mixin class to define base archival methods"""

    parsed_objects: dict[str, Any]

    metadata: dict[str, Any] | None = None
    format: ArchivalFormat | str = ArchivalFormat.HDF5
    compression: dict | None = None
    float_dtype: str | np.dtype = "float64"

    def __post_init__(self) -> None:
        """Ensure that attributes have correct type."""
        # for key, value in self.parsed_objects.items():
        #    setattr(self, key.lower(), value)

        if isinstance(self.format, str):
            self.format = ArchivalFormat(self.format)

        if self.compression is None:
            if self.format == ArchivalFormat.HDF5:
                self.compression = {
                    "compression": "gzip",
                    "compression_opts": 9,
                    "chunks": True,
                }
            elif self.format == ArchivalFormat.ZARR:
                self.compression = {
                    "compressor": Blosc(clevel=9),
                }

        if isinstance(self.float_dtype, str):
            self.float_dtype = np.dtype(self.float_dtype)

    def __getattr__(self, name: Any) -> Any:
        """Allow accessing parsed objects with dot notation."""
        if name.upper() in self.parsed_objects:
            return self.parsed_objects[name.upper()]
        elif name.lower() in self.parsed_objects:
            return self.parsed_objects[name.lower()]
        raise AttributeError(name)

    def to_group(
        self, group: h5py.Group | zarr.Group, group_key: str = "group"
    ) -> None:
        """Append data to an existing HDF5-like file group."""
        raise NotImplementedError

    def to_archive(self, file_name: str | Path = "archive") -> None:
        """Create a new archive for this class of data."""

        if isinstance(file_name, Path):
            file_name = str(file_name)

        if len(file_split := file_name.split(".")) > 1:
            file_name = ".".join(file_split[:-1])
        file_name += f".{self.format.value}"  # type: ignore[union-attr,attr-defined]

        if self.format == ArchivalFormat.HDF5:
            with h5py.File(file_name, "w") as hf5:
                self.to_group(hf5)
        elif self.format == ArchivalFormat.ZARR:
            with zarr.open(file_name, "w") as zg:
                self.to_group(zg)
        else:
            raise ValueError(
                f"Unknown file format {self.format}. Acceptable file extensions are:"
                f" {', '.join(ArchivalFormat)}"
            )

    @classmethod
    def from_archive(cls, archive_path: str | Path, *args, **kwargs) -> Self:
        """Define methods to instantiate an Archiver from an archive path."""
        raise NotImplementedError


@dataclass
class StructureArchive(Archiver):
    """Archive a Structure."""

    # parsed_objects: dict[str, Any] = field(default_factory=lambda: {"structure": None})

    @classmethod
    def from_file(cls, file_path: str | Path) -> StructureArchive:
        return cls({"structure": Structure.from_file(file_path)})

    def to_group(
        self, group: h5py.Group | zarr.Group, group_key: str = "structure"
    ) -> None:
        group.create_group(group_key)
        group[group_key].attrs["charge"] = self.structure.charge
        if self.metadata is not None:
            for k, v in self.metadata.items():
                group[group_key].attrs[k] = v
        group[group_key].create_dataset(
            "lattice", data=self.structure.lattice.matrix, **self.compression
        )
        group[group_key].create_group("sites")
        group[f"{group_key}/sites"].create_dataset(
            "species",
            data=[site.species_string for site in self.structure.sites],
            **self.compression,
        )
        group[f"{group_key}/sites"].create_dataset(
            "direct_coordinates",
            data=[site.frac_coords for site in self.structure.sites],
            **self.compression,
        )
        if len(self.structure.site_properties) > 0.0:
            group[f"{group_key}/sites"].create_group("properties")
            for site_prop, prop_vals in self.structure.site_properties.items():
                group[f"{group_key}/sites/properties"].create_dataset(
                    site_prop, data=prop_vals, **self.compression
                )

    @staticmethod
    def from_group(group: h5py.Group | zarr.Group) -> Structure:
        site_properties = {}
        if (site_props := group["sites"].get("properties")) is not None:
            for site_prop in site_props:
                site_properties[site_prop] = list(site_prop)
        return Structure(
            lattice=group["lattice"],
            species=[
                ele_bytes.decode("utf8") if isinstance(ele_bytes, bytes) else ele_bytes
                for ele_bytes in group["sites/species"]
            ],
            coords=group["sites/direct_coordinates"],
            charge=group.attrs["charge"],
            coords_are_cartesian=False,
            site_properties=site_properties,
        )
