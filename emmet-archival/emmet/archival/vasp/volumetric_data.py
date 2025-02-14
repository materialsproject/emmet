from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import h5py
from pathlib import Path
from typing import TYPE_CHECKING

from monty.serialization import loadfn
import numpy as np
import zarr

from emmet.core.tasks import TaskDoc
from emmet.core.vasp.calculation import VaspObject

from pymatgen.electronic_structure.bandstructure import BandStructureSymmLine
from pymatgen.electronic_structure.core import Orbital, Spin
from pymatgen.electronic_structure.dos import CompleteDos, Dos
from pymatgen.io.vasp.outputs import Vasprun

from emmet.archival.base import ArchivalFormat, Archiver
from emmet.archival.utils import zpath
from emmet.archival.vasp import VASP_VOLUMETRIC_FILES, PMG_OBJ
from emmet.archival.vasp.inputs import PoscarArchive

if TYPE_CHECKING:
    from typing import Any

    from pymatgen.core.sites import PeriodicSite
    from pymatgen.io.vasp.outputs import VolumetricData

@dataclass
class DosArchive(Archiver):
    # parsed_objects : dict[str,Any] = {"DOS": None}

    def __post_init__(self) -> None:
        if isinstance(self.parsed_objects["DOS"], dict):
            self.parsed_objects["DOS"] = CompleteDos.from_dict(
                self.parsed_objects["DOS"]
            )
        super().__post_init__()

    @classmethod
    def from_vasprun(cls, vasprun: Vasprun | str | Path, **kwargs):
        if isinstance(vasprun, (str, Path)) and Path(vasprun).exists():
            vasprun = Vasprun(vasprun)
        return cls(parsed_objects={"DOS": vasprun.complete_dos}, **kwargs)  # type: ignore[union-attr]

    @classmethod
    def from_parsed_data(cls, dos_path: str | Path, **kwargs):
        dos_data = loadfn(dos_path)
        metadata = {k: v for k, v in dos_data.items() if k != "data"}
        return cls(
            parsed_objects={"DOS": dos_data["data"]}, metadata=metadata, **kwargs
        )

    def to_group(self, group: h5py.Group, group_key: str = "DOS") -> None:
        group.create_group(group_key)
        group[group_key].attrs["efermi"] = self.dos.efermi
        for k, v in (self.metadata or {}).items():
            group[group_key].attrs[k] = str(v) if isinstance(v, datetime) else v

        PoscarArchive(
            parsed_objects={"POSCAR": self.dos.structure}, format=self.format
        ).to_group(group[group_key])

        spin_idxs = list(self.dos.densities)

        pdos_idxs = []
        pdos_data = []
        if (pdos := getattr(self.dos, "pdos")) is not None:
            pdos_idxs = [
                (site_idx, orbital, spin)
                for site_idx in range(self.dos.structure.num_sites)
                for orbital in pdos[self.dos.structure[0]]
                for spin in spin_idxs
            ]

            for site_idx, orbital, spin in pdos_idxs:
                pdos_data.append(pdos[self.dos.structure[site_idx]][orbital][spin])

        group[group_key].create_dataset(
            "index",
            data=[
                "energies",
                *[f"total-{spin}" for spin in spin_idxs],
                *[
                    "pdos-" + "-".join([str(idx) for idx in comp_idx])
                    for comp_idx in pdos_idxs
                ],
            ],
            **self.compression,
        )

        group[group_key].create_dataset(
            "complete_dos",
            data=np.array(
                [
                    self.dos.energies,
                    *[self.dos.densities[spin] for spin in spin_idxs],
                    *pdos_data,
                ]
            ),
            dtype=self.float_dtype,
            **self.compression,
        )

    @staticmethod
    def from_group(group: h5py.Group) -> CompleteDos:
        energies = None
        densities: dict[Spin, np.ndarray] = {}
        pdos: dict[PeriodicSite, dict[Orbital, dict[Spin, np.ndarray]]] = {}
        structure = PoscarArchive.from_group(group["POSCAR"]).structure
        for idx, key in enumerate(group["index"]):
            key = key.decode()
            col = np.array(group["complete_dos"][idx])
            if key == "energies":
                energies = col
            elif "total" in key:
                densities[Spin(int(key.split("-")[-1]))] = col
            elif "pdos" in key:
                site_idx, orbital, spin = key.split("-")[1:]
                site = structure[int(site_idx)]
                orbital = Orbital[orbital]
                if site not in pdos:
                    pdos[site] = {}
                if orbital not in pdos[site]:
                    pdos[site][orbital] = {}
                pdos[site][orbital][Spin(int(spin))] = col

        total_dos = Dos(
            efermi=group.attrs["efermi"],
            energies=energies.tolist(),
            densities=densities,
        )

        return CompleteDos(
            structure=PoscarArchive.from_group(group["structure"]).structure,
            total_dos=total_dos,
            pdoss=pdos,
        )


@dataclass
class BandStructureArchive(Archiver):
    # parsed_objects : dict[str,Any] = {"BS": None}

    def __post_init__(self) -> None:
        if isinstance(self.parsed_objects["BS"], dict):
            self.parsed_objects["BS"] = BandStructureSymmLine.from_dict(
                self.parsed_objects["BS"]
            )

        super().__post_init__()

    @classmethod
    def from_parsed_data(cls, bs_path: str | Path, **kwargs):
        bs_data = loadfn(bs_path)
        return cls(
            parsed_objects={"BS": bs_data["data"]},
            metadata={k: v for k, v in bs_data.items() if k != "data"},
            **kwargs,
        )

    def to_group(
        self, group: h5py.Group | zarr.Group, group_key: str = "group"
    ) -> None:
        group.create_group("band_structure")
        group[group_key].attrs["efermi"] = self.bs.efermi
        group[group_key].attrs["num_bands"] = self.bs.nb_bands
        for k, v in (self.metadata or {}).items():
            group[group_key].attrs[k] = str(v) if isinstance(v, datetime) else v

        bs_data = np.zeros(
            (3 + len(self.bs.bands) * self.bs.nb_bands, len(self.bs.kpoints))
        )
        bs_data[:3, :] = np.array([kpt.frac_coords for kpt in self.bs.kpoints]).T
        idxs = ["kx", "ky", "kz"]

        bs_idx = 3
        for spin, sr_bands in self.bs.bands.items():
            idxs += [f"{spin}-{band_idx}" for band_idx in range(self.bs.nb_bands)]
            bs_data[bs_idx : bs_idx + self.bs.nb_bands, :] = sr_bands

        group[group_key].create_dataset("index", data=idxs, **self.compression)
        group[group_key].create_dataset(
            "complete_band_structure",
            data=bs_data,
            dtype=self.float_dtype,
            **self.compression,
        )
        group[group_key].create_dataset(
            "reciprocal_lattice",
            data=self.bs.lattice_rec.matrix,
            dtype=self.float_dtype,
            **self.compression,
        )
        PoscarArchive({"POSCAR": self.bs.structure}, format=self.format).to_group(
            group[group_key]
        )

        if (bs_proj := self.bs.projections) is not None:
            group[group_key].create_group("projections")
            for spin, sr_proj_data in bs_proj.items():
                group[f"{group_key}/projections"].create_dataset(
                    str(spin),
                    data=sr_proj_data,
                    dtype=self.float_dtype,
                    **self.compression,
                )


@dataclass
class ElectronicStructureArchive(Archiver):
    # parsed_objects : dict[str,Any] = {"DOS": None,"BS": None,}

    @classmethod
    def from_vasprun(cls, vasprun: str | Path | Vasprun = "vasprun.xml", **kwargs):
        if isinstance(vasprun, (str, Path)):
            vasprun = Vasprun(zpath(vasprun))
        return cls(
            parsed_objects={
                "DOS": vasprun.complete_dos,
                "BS": vasprun.get_band_structure(efermi="smart"),
            },
            **kwargs,
        )

    @classmethod
    def from_task_doc(cls, task_doc: TaskDoc, **kwargs):
        es_objs = {
            obj_name: task_doc.vasp_objects.get(VaspObject[obj_name])
            for obj_name in ("DOS", "BANDSTRUCTURE")
        }
        if not all(obj is not None for obj in es_objs.values()):
            raise UserWarning(
                f"Missing {', '.join([obj_name for obj_name, obj in es_objs.items() if obj is None])} data!"
            )
        return cls(
            parsed_objects={"DOS": es_objs["DOS"], "BS": es_objs["BANDSTRUCTURE"]},
            **kwargs,
        )

    def to_group(
        self,
        group: h5py.Group | zarr.Group,
        group_key: str = "electronic_structure",
    ) -> None:
        group.create_group(group_key)
        if self.dos is not None:
            DosArchive(
                parsed_objects={"DOS": self.dos}, metadata=self.metadata
            ).to_group(group[group_key])
        if self.bs is not None:
            BandStructureArchive(
                parsed_objects={"BS": self.bs}, metadata=self.metadata
            ).to_group(group[group_key])


@dataclass
class VolumetricArchive(Archiver):
    def __post_init__(self):
        for file_name, obj in self.parsed_objects.items():
            self.parsed_objects[file_name] = {
                "object": obj,
                "augmentation": {},
            }
            for aug_key, data_aug_subset in obj.data_aug.items():
                if data_aug_subset is not None:
                    (
                        self.parsed_objects[file_name]["augmentation"][aug_key],
                        _,
                    ) = self.parse_augmentation_data(data_aug_subset)

            self.parsed_objects[file_name]["augmentation"] = (
                self.parsed_objects[file_name]["augmentation"] or None
            )

        super().__post_init__()

    @classmethod
    def from_directory(cls, calc_dir: str | Path, **kwargs) -> VolumetricArchive:
        calc_dir = Path(calc_dir).resolve()
        metadata = {"calc_dir": str(calc_dir), "file_paths": {}}
        parsed_objects: dict[str, Any] = {}
        for file_name in VASP_VOLUMETRIC_FILES:
            file_path = zpath(calc_dir / file_name)
            if file_path.exists():
                metadata["file_paths"][file_name] = file_path  # type: ignore[index]
                parsed_objects[file_name] = PMG_OBJ[file_name].from_file(file_path)  # type: ignore[attr-defined]

        return cls(parsed_objects=parsed_objects, metadata=metadata, **kwargs)

    @staticmethod
    def parse_augmentation_data(
        aug_data: list[str], pad_value=None, pad_to_rank: int | None = None
    ):
        aug_data_parsed: list | np.ndarray = []
        data = None
        for _line in aug_data:
            line = _line.strip().split()
            if any("augmentation" in ele for ele in line):
                rank = int(line[-1])
                if data is not None:
                    aug_data_parsed.append(data)
                data_idx = 0
                data = np.zeros(rank)
                continue
            for val in line:
                if data_idx == rank:
                    continue
                data[data_idx] = float(val)
                data_idx += 1

        ranks = [len(row) for row in aug_data_parsed]
        if pad_value is not None:
            pad_to_rank = pad_to_rank or max(ranks)
            for idx, row in enumerate(aug_data_parsed):
                if len(row) < pad_to_rank:
                    aug_data_parsed[idx] = np.array(
                        list(row) + [pad_value for _ in range(pad_to_rank - len(row))]
                    )
            aug_data_parsed = np.array(aug_data_parsed)

        return aug_data_parsed, ranks

    def to_group(self, group: h5py.Group, group_key: str | None = None) -> None:
        for vobj in self.parsed_objects.values():
            if vobj is not None:
                break

        if group_key is not None:
            group.create_group(group_key)
            group = group[group_key]
        for k, v in self.metadata.items():
            if k != "file_paths":
                group.attrs[k] = v

        PoscarArchive(
            parsed_objects={"POSCAR": vobj["object"].poscar}, format=self.format
        ).to_group(group)

        for file_name, entry in self.parsed_objects.items():
            group.create_group(file_name)
            if (
                fpath := self.metadata.get("file_paths", {}).get(file_name)
            ) is not None:
                group[file_name].attrs["path"] = str(fpath)
            for chg_key, data in entry["object"].data.items():
                group[file_name].create_dataset(
                    chg_key, data=data, dtype=self.float_dtype, **self.compression
                )

            if entry["augmentation"] is not None:
                group[file_name].create_group("augmentation")
                for aug_key, aug_data in entry["augmentation"].items():
                    group[f"{file_name}/augmentation"].create_group(aug_key)
                    for aug_idx, aug_set in enumerate(aug_data):
                        group[f"{file_name}/augmentation/{aug_key}"].create_dataset(
                            f"{aug_idx+1}",
                            data=aug_set,
                            dtype=self.float_dtype,
                            **self.compression,
                        )

    @classmethod
    def get_vol_data_from_archive(
        cls,
        archive_name: str | Path,
        files_to_retrieve=VASP_VOLUMETRIC_FILES,
        fmt: str | ArchivalFormat | None = None,
        group_key : str | None = None,
    ) -> dict[str, VolumetricData]:

        charge_densities = {}

        with cls.load_archive(archive_name, fmt = fmt, group_key=group_key) as group:
            
            poscar = PoscarArchive.from_group(group["structure"])
            for file_name in files_to_retrieve:
                if group.get(file_name):
                    data = {}
                    for k in (
                        "total",
                        "diff",
                    ):
                        if (_data := group[file_name].get(k)) is not None:
                            data[k] = np.array(_data)

                    data_aug = None
                    if (aug_data := group[file_name].get("augmentation")) is not None:
                        data_aug = {}
                        for k in (
                            "total",
                            "diff",
                        ):
                            if (_data := aug_data.get(k)) is not None:
                                data_aug[k] = [
                                    np.array(aug_chgs) for aug_chgs in _data.values()
                                ]

                    kwargs: dict[str, Any] = {"poscar": poscar, "data": data}
                    if all(f not in file_name.upper() for f in ("ELFCAR", "LOCPOT")):
                        kwargs.update({"data_aug": data_aug})
                    charge_densities[file_name] = PMG_OBJ[file_name](**kwargs)

        return charge_densities