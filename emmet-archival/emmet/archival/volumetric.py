"""Common volumetric data archival framework."""
from __future__ import annotations

from enum import Enum
import json
from typing import TYPE_CHECKING

import pyarrow as pa
import pyarrow.parquet as pq
from pydantic import BaseModel, Field

from pymatgen.core import Structure
from pymatgen.io.common import VolumetricData as PmgVolumetricData

from emmet.archival.base import Archiver

if TYPE_CHECKING:
    from os import PathLike
    from pathlib import Path


class VolumetricLabel(Enum):
    TOTAL = "total"
    DIFF = "diff"
    DIFF_X = "diff_x"
    DIFF_Y = "diff_y"
    DIFF_Z = "diff_z"


class AugChargeData(BaseModel):
    label: str | None = Field(
        None, description="The label written by VASP for the augmenation charge data."
    )
    data: list[float] | None = Field(None, description="The augmentation charges.")


class VolumetricArchive(Archiver):
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
        return cls(
            data={VolumetricLabel(k): v.tolist() for k, v in vd.data.items()},
            data_aug=cls.parse_augmentation_charge_data(vd.data_aug),
            structure=vd.structure,
        )

    def _to_parquet(self, file_name: PathLike, **kwargs) -> None:
        config = {}
        for k, v in self.data.items():
            config[f"data_{k.value}"] = pa.array([v])
        for k, v in self.data_aug.items():
            config[f"data_aug_{k.value}"] = pa.array([[x.model_dump() for x in v]])

        # CRITICAL - improve like traj does
        config["structure"] = pa.array([json.dumps(self.structure.as_dict())])

        pq.write_table(pa.table(config), file_name)

    @classmethod
    def _extract_from_parquet(
        cls, archive_path: str | Path, *args, **kwargs
    ) -> PmgVolumetricData:
        table = pq.read_table(archive_path)
        cls_config = {}
        for data_key in ("data", "data_aug"):
            cls_config[data_key] = {}
            for vlab in VolumetricLabel:
                comp_key = f"{data_key}_{vlab.value}"
                if comp_key in table.column_names:
                    cls_config[data_key][vlab.value] = table[comp_key].to_pylist()[0]

        return PmgVolumetricData(
            structure=Structure.from_str(table["structure"].to_pylist()[0], fmt="json"),
            **cls_config,
        )
