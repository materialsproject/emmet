"""Common volumetric data archival framework."""
from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

import pyarrow as pa
import pyarrow.parquet as pq
from pydantic import BaseModel, Field

from pymatgen.core import Structure
from pymatgen.io.common import VolumetricData as PmgVolumetricData

from emmet.archival.base import Archiver
from emmet.archival.atoms import CrystalArchive

if TYPE_CHECKING:
    from pathlib import Path


class VolumetricLabel(Enum):
    TOTAL = "total"
    DIFF = "diff"

    # NB: we only need these if we have noncolinear calculations
    DIFF_X = "diff_x"
    DIFF_Y = "diff_y"
    DIFF_Z = "diff_z"


class AugChargeData(BaseModel):
    label: str | None = Field(
        None, description="The label written by VASP for the augmenation charge data."
    )
    data: list[float] | None = Field(None, description="The augmentation charges.")


class ElectronicDos(BaseModel):
    """Basic structure for spin-resolved density of states (DOS)."""

    spin_up: list[float] = Field(description="The up-spin DOS.")

    spin_down: list[float] = Field(description="The down-spin DOS.")

    energies: list[float] | None = Field(
        None, description="The energies at which the DOS was calculated."
    )

    efermi: float | None = Field(None, description="The Fermi energy.")

    orbital: str | None = Field(
        None, description="The orbital character of this DOS, if applicable."
    )


class VolumetricArchive(Archiver):
    """Archive a pymatgen.io.common.VolumetricData object.

    While the name of this file suggests a common I/O purpose,
    the structure of the pymatgen object and its Archiver are meant
    for VASP data.
    """

    data: dict[VolumetricLabel, list[list[list[float]]] | None] = Field(
        None, description="The primary volumetric data."
    )
    data_aug: dict[VolumetricLabel, list[AugChargeData]] | None = Field(
        None, description="The augmentation charge volumetric data."
    )
    structure: Structure | None = Field(
        None, description="The structure associated with the volumetric data."
    )

    @staticmethod
    def parse_augmentation_charge_data(
        aug_data: dict[str, list[str]]
    ) -> dict[VolumetricLabel, list[AugChargeData]]:
        aug_data_arr = {}
        for k, unfmt_data in aug_data.items():
            if not any(line.strip() for line in unfmt_data):
                continue
            parse_meta = True
            num_vals = -1
            aug_data_arr[VolumetricLabel(k)] = []
            atom_data = {}
            for row in unfmt_data:
                data = row.replace("\n", "").split()
                if parse_meta:
                    if not data[0].isalpha():
                        # pymatgen sometimes puts extra lines here because they
                        # exist in a CHGCAR but have no clear meaning.
                        # probably needs a fix in pymatgen
                        continue

                    label = " ".join([x for x in data[:-1] if x.isalpha()])

                    atom_data = {"label": label, "data": []}
                    num_vals = int(data[-1])
                    parse_meta = False
                else:
                    atom_data["data"].extend([float(x) for x in data])
                    if len(atom_data["data"]) >= num_vals:
                        parse_meta = True
                        aug_data_arr[VolumetricLabel(k)].append(
                            AugChargeData(**atom_data)
                        )

        return aug_data_arr

    @classmethod
    def from_pmg(cls, vd: PmgVolumetricData) -> VolumetricArchive:
        """Convert generic pymatgen volumetric data to an archive format."""
        return cls(
            data={VolumetricLabel(k): v.tolist() for k, v in vd.data.items()},
            data_aug=cls.parse_augmentation_charge_data(vd.data_aug) or None,
            structure=vd.structure,
        )

    def to_arrow(self) -> pa.Table:
        config = {}
        for k in VolumetricLabel:
            config[f"data_{k.value}"] = pa.array([[self.data.get(k, None)]])

        if self.data_aug:
            for k in VolumetricLabel:
                if vals := self.data_aug.get(k, None):
                    config[f"data_aug_{k.value}"] = pa.array(
                        [[x.model_dump() for x in vals]]
                    )
                else:
                    config[f"data_aug_{k.value}"] = pa.array([[None]])
        else:
            for k in VolumetricLabel:
                config[f"data_aug_{k.value}"] = pa.array([[None]])

        crystal_archive = CrystalArchive.from_pmg(self.structure)
        config.update(crystal_archive._to_arrow_arrays(prefix="structure_"))

        return pa.table(config)

    @classmethod
    def from_arrow(cls, table: pa.Table) -> PmgVolumetricData:
        cls_config = {}
        for data_key in ("data", "data_aug"):
            cls_config[data_key] = {}
            for vlab in VolumetricLabel:
                comp_key = f"{data_key}_{vlab.value}"
                if comp_key in table.column_names:
                    cls_config[data_key][vlab.value] = table[comp_key].to_pylist()[0]

        return PmgVolumetricData(
            structure=CrystalArchive.from_arrow(table, prefix="structure_"),
            **cls_config,
        )

    @classmethod
    def _extract_from_parquet(
        cls,
        archive_path: str | Path,
    ) -> PmgVolumetricData:
        return cls.from_arrow(pq.read_table(archive_path))
