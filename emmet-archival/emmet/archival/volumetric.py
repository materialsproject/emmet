"""Common volumetric data archival framework."""

from __future__ import annotations

from typing import TYPE_CHECKING, Type

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
from pydantic import BaseModel, Field

from pymatgen.io.common import VolumetricData as PmgVolumetricData

from emmet.core.vasp.models import ChgcarLike
from emmet.core.types.enums import ValueEnum

from emmet.archival.base import Archiver
from emmet.archival.atoms import CrystalArchive

if TYPE_CHECKING:
    from pathlib import Path


class VolumetricLabel(ValueEnum):
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


class VolumetricArchive(Archiver, ChgcarLike):
    """Archive a volumetric data / CHGCAR-like object.

    Can archive pymatgen.io.common.VolumetricData
    or emmet.core.vasp.models.ChgcarLike objects.

    While the name of this file suggests a common I/O purpose,
    the structure of the pymatgen object and its Archiver are meant
    for VASP data.
    """

    def to_arrow(self) -> pa.Table:
        config = {
            k: (
                pa.array([v])
                if k != "labels"
                else pa.array([[v.value for v in self.labels]])
            )
            for k, v in self.model_dump().items()
        }

        crystal_archive = CrystalArchive.from_pmg(self.structure)
        config.update(crystal_archive._to_arrow_arrays(prefix="structure_"))

        return pa.table(config)

    @classmethod
    def from_arrow(
        cls, table: pa.Table, pmg_cls: Type[PmgVolumetricData] = PmgVolumetricData
    ) -> PmgVolumetricData:
        cls_config: dict[str, dict[str, np.ndarray]] = {
            k: {} for k in ("data", "data_aug")
        }
        data = table["data"].to_numpy()[0]
        aug_data = (
            table["data_aug"].to_pylist()[0]
            if "data_aug" in table.column_names
            else None
        )
        ranks = table["data_rank"].to_pylist()[0]
        for i, vol_label in enumerate(table["labels"].to_pylist()[0]):
            cls_config["data"][vol_label] = data[i].reshape(ranks[i])
            if aug_data and aug_data[i]:
                cls_config["data_aug"][vol_label] = np.array(aug_data[i])

        return pmg_cls(
            CrystalArchive.from_arrow(table, prefix="structure_"),
            **cls_config,
        )

    @classmethod
    def _extract_from_parquet(
        cls,
        archive_path: str | Path,
    ) -> PmgVolumetricData:
        return cls.from_arrow(pq.read_table(archive_path))
