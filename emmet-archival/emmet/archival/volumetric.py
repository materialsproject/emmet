"""Common volumetric data archival framework."""

from __future__ import annotations

from typing import TYPE_CHECKING

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
    from typing import Any


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
        config = {}
        for k in VolumetricLabel:  # type: ignore[attr-defined]
            config[f"data_{k.value}"] = pa.array([[self.data.get(k, None)]])

        if self.data_aug:
            for k in VolumetricLabel:  # type: ignore[attr-defined]
                if vals := self.data_aug.get(k, None):
                    config[f"data_aug_{k.value}"] = pa.array(
                        [[x.model_dump() for x in vals]]
                    )
                else:
                    config[f"data_aug_{k.value}"] = pa.array([[None]])
        else:
            for k in VolumetricLabel:  # type: ignore[attr-defined]
                config[f"data_aug_{k.value}"] = pa.array([[None]])

        crystal_archive = CrystalArchive.from_pmg(self.structure)
        config.update(crystal_archive._to_arrow_arrays(prefix="structure_"))

        return pa.table(config)

    @classmethod
    def from_arrow(cls, table: pa.Table) -> PmgVolumetricData:
        cls_config: dict[str, Any] = {}
        for data_key in ("data", "data_aug"):
            cls_config[data_key] = {}
            for vlab in VolumetricLabel:  # type: ignore[attr-defined]
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
