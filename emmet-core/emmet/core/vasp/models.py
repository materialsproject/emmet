"""Common models and types needed for VASP data."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from pydantic import BaseModel, Field

from pymatgen.core import Structure
from pymatgen.io.common import VolumetricData as PmgVolumetricData
from pymatgen.io.vasp import Poscar

from emmet.core.types.enums import ValueEnum
from emmet.core.types.pymatgen_types.structure_adapter import StructureType

if TYPE_CHECKING:
    from collections.abc import Callable
    from typing_extensions import Self


class ElectronicStep(BaseModel):
    """Document defining the information at each electronic step.

    Note, not all the information will be available at every step.
    """

    alphaZ: float | None = Field(None, description="The alpha Z term.")
    ewald: float | None = Field(None, description="The ewald energy.")
    hartreedc: float | None = Field(None, description="Negative Hartree energy.")
    XCdc: float | None = Field(None, description="Negative exchange energy.")
    pawpsdc: float | None = Field(
        None, description="Negative potential energy with exchange-correlation energy."
    )
    pawaedc: float | None = Field(None, description="The PAW double counting term.")
    eentropy: float | None = Field(None, description="The entropy (T * S).")
    bandstr: float | None = Field(
        None, description="The band energy (from eigenvalues)."
    )
    atom: float | None = Field(None, description="The atomic energy.")
    e_fr_energy: float | None = Field(None, description="The free energy.")
    e_wo_entrp: float | None = Field(None, description="The energy without entropy.")
    e_0_energy: float | None = Field(None, description="The internal energy.")


class VolumetricLabel(ValueEnum):
    TOTAL = "total"
    DIFF = "diff"

    # NB: we only need these if we have noncolinear calculations
    # DIFF_X = "diff_x"
    # DIFF_Y = "diff_y"
    # DIFF_Z = "diff_z"


class AugChargeData(BaseModel):
    label: str | None = Field(
        None, description="The label written by VASP for the augmenation charge data."
    )
    data: list[float] | None = Field(None, description="The augmentation charges.")


class ChgcarLike(BaseModel):
    """Model for VASP CHGCAR-like data.

    Includes CHGCAR, CHG, LOCPOT, ELFCAR, AECCAR0, AECCAR1, AECCAR2, POT.
    All volumetric data is flattened upon storage in the model from a
    rank-3 tensor.
    C-order is used throughout.
    """

    identifier: str | None = Field(
        None, description="The identifier of this calculation."
    )

    labels: list[VolumetricLabel] | None = Field(
        None, description="The spin resolution of the volumetric data."
    )
    data: list[list[float] | None] | None = Field(
        description="The primary volumetric data."
    )
    data_rank: list[tuple[int, int, int]] | None = Field(
        None, description="The original shape of the"
    )
    data_aug: list[list[AugChargeData] | None] | None = Field(
        None, description="The augmentation charge volumetric data."
    )
    structure: StructureType | None = Field(
        None, description="The structure associated with the volumetric data."
    )

    @staticmethod
    def parse_augmentation_charge_data(
        aug_data: dict[str, list[str]],
    ) -> dict[VolumetricLabel, list[AugChargeData]]:
        aug_data_arr: dict[VolumetricLabel, list[AugChargeData]] = {}
        for k, unfmt_data in aug_data.items():
            if not isinstance(unfmt_data, list) or not any(
                line.strip() for line in unfmt_data
            ):
                continue
            parse_meta = True
            num_vals = -1
            aug_data_arr[VolumetricLabel(k)] = []
            atom_data: list[float] = []
            atom_label: str | None = None
            for row in unfmt_data:
                data = row.replace("\n", "").split()
                if parse_meta:
                    if not data[0].isalpha():
                        # pymatgen sometimes puts extra lines here because they
                        # exist in a CHGCAR but have no clear meaning.
                        # probably needs a fix in pymatgen
                        continue

                    label = " ".join([x for x in data[:-1] if x.isalpha()])

                    atom_label = label
                    atom_data = []
                    num_vals = int(data[-1])
                    parse_meta = False
                else:
                    atom_data.extend([float(x) for x in data])
                    if len(atom_data) >= num_vals:
                        parse_meta = True
                        aug_data_arr[VolumetricLabel(k)].append(
                            AugChargeData(label=atom_label, data=atom_data)
                        )

        return aug_data_arr

    @classmethod
    def from_pmg(cls, vd: PmgVolumetricData, **kwargs) -> Self:
        """Convert generic pymatgen volumetric data to an archive format."""
        labels = [VolumetricLabel(k) for k in vd.data]
        data_aug = None
        if aug_data := cls.parse_augmentation_charge_data(vd.data_aug):  # type: ignore[arg-type]
            data_aug = [aug_data.get(vlab) for vlab in labels]

        return cls(  # type: ignore[call-arg]
            labels=labels,
            data=[vd.data[vlab].flatten(order="C") for vlab in labels],  # type: ignore[misc]
            data_rank=[vd.data[vlab].shape for vlab in labels],  # type: ignore[misc]
            data_aug=data_aug,
            structure=(
                vd.structure
                if isinstance(vd.structure, Structure)
                else Structure.from_dict(vd.structure.as_dict())
            ),
            **kwargs,
        )

    def to_pmg(self, pmg_cls: Callable = PmgVolumetricData) -> PmgVolumetricData:
        """Convert to a pymatgen VolumetricData-derived object."""
        data_aug: dict[str, np.ndarray] | None = None
        if self.data_aug:
            data_aug = {
                vol_label.value: np.array(self.data_aug[i])
                for i, vol_label in enumerate(self.labels or [])
                if self.data_aug[i]
            }
        return pmg_cls(
            Poscar(self.structure),  # type: ignore[arg-type]
            {
                vol_label.value: np.array(self.data[i]).reshape(  # type: ignore[index]
                    self.data_rank[i], order="C"  # type: ignore[index]
                )
                for i, vol_label in enumerate(self.labels or [])
            },
            data_aug=data_aug,
        )
