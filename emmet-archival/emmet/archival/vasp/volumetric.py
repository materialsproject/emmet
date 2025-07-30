from __future__ import annotations

from datetime import datetime
import h5py
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
from pydantic import Field
import zarr

from emmet.core.band_theory import ElectronicBS
from emmet.core.tasks import TaskDoc
from emmet.core.vasp.calculation import VaspObject
from emmet.core.vasp.utils import VASP_VOLUMETRIC_FILES

from pymatgen.core import Structure
from pymatgen.electronic_structure.core import Orbital, Spin
from pymatgen.electronic_structure.dos import CompleteDos, Dos
from pymatgen.io.vasp.outputs import Vasprun

from emmet.archival.atoms import CrystalArchive
from emmet.archival.base import Archiver
from emmet.archival.volumetric import VolumetricArchive, ElectronicDos
from emmet.archival.utils import zpath
from emmet.archival.vasp import PMG_OBJ
from emmet.archival.vasp.inputs import PoscarArchive

if TYPE_CHECKING:
    from typing import Any

    from pymatgen.io.common import VolumetricData as PmgVolumetricData
    from pymatgen.core.sites import PeriodicSite


class DosArchive(Archiver):
    """Tools for archiving a density of states (DOS)."""

    total_dos: ElectronicDos = Field(description="The DOS for the entire structure.")

    structure: Structure | None = Field(
        None, description="The structure associated with this DOS."
    )

    projected_densities: list[list[ElectronicDos] | None] | None = Field(
        None, description="The orbital- and site-projected DOS."
    )

    @classmethod
    def from_vasprun(cls, vasprun: Vasprun, **kwargs):
        config = {
            "total_dos": ElectronicDos(
                **{
                    f"spin_{spin.name}": sr_dos
                    for spin, sr_dos in vasprun.complete_dos.densities.items()
                },
                energies=vasprun.complete_dos.energies,
                efermi=vasprun.complete_dos.efermi,
            ),
            "structure": vasprun.complete_dos.structure,
        }

        pdos = None
        if (vrun_pdos := vasprun.complete_dos.pdos) and config.get("structure"):
            pdos = [None for _ in range(len(config["structure"]))]
            for site, orb_spin_dos in vrun_pdos.items():
                site_idx = [
                    idx
                    for idx, ref_site in enumerate(config["structure"])
                    if ref_site == site
                ][0]
                pdos[site_idx] = [
                    ElectronicDos(
                        **{
                            f"spin_{spin.name}": sr_dos
                            for spin, sr_dos in spin_dos.items()
                        },
                        orbital=orbital.name,
                    )
                    for orbital, spin_dos in orb_spin_dos.items()
                ]

        return cls(**config, projected_densities=pdos, **kwargs)

    def to_arrow(self) -> pa.Table:
        config = {
            **{
                k: pa.array([v])
                for k, v in self.model_dump(mode="json", exclude="structure").items()
            },
            **CrystalArchive.from_pmg(self.structure)._to_arrow_arrays(
                prefix="structure_"
            ),
        }
        return pa.table(config)

    @classmethod
    def from_arrow(cls, table: pa.Table) -> Dos | CompleteDos:
        tdos = ElectronicDos(**table["total_dos"].to_pylist()[0]).to_pmg()
        if any("structure_" in col for col in table.column_names):
            structure = CrystalArchive.from_arrow(table, prefix="structure_")
        else:
            return tdos

        pdos_pmg = {}
        if "projected_densities" in table.column_names:
            pdos = table["projected_densities"].to_pylist()[0]
            for site_idx, pdos_by_site in enumerate(pdos):
                if pdos_by_site:
                    pdos_pmg[structure[site_idx]] = {}
                    for proj_dos in pdos_by_site:
                        pdos_pmg[structure[site_idx]][Orbital[proj_dos["orbital"]]] = {
                            spin: proj_dos[f"spin_{spin.name}"]
                            for spin in Spin
                            if proj_dos[f"spin_{spin.name}"]
                        }

        return CompleteDos(
            structure,
            tdos,
            pdos_pmg,
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


class BandStructureArchive(Archiver):

    band_structure: ElectronicBS = Field(description="The electronic band structure.")

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


class VaspVolumetricArchive(Archiver):
    """Archive all CHGCAR-like volumetric data associated with a VASP calculation."""

    file_names: list[str] = Field(
        description="The names of the volumetric files included in the archive."
    )
    volumetric_archives: list[VolumetricArchive] = Field(
        description="Individual volumetric archives for the files in file_names."
    )
    identifier: str | None = Field(
        None, description="The identifier associated with this set of volumetric d"
    )

    @classmethod
    def from_directory(cls, dir_name: str | Path, **kwargs) -> VaspVolumetricArchive:
        calc_dir = Path(dir_name).resolve()
        file_names: list[str] = []
        vol_archs = []
        for file_name in set(VASP_VOLUMETRIC_FILES).intersection(PMG_OBJ):
            file_path = zpath(calc_dir / file_name)
            if file_path.exists():
                file_names.append(file_name)
                vol_data = PMG_OBJ[file_name].from_file(file_path)
                vol_archs.append(VolumetricArchive.from_pmg(vol_data))

        return cls(file_names=file_names, volumetric_archives=vol_archs)

    def _to_parquet(self, file_name, **kwargs):
        # to ensure that the pyarrow schema contains augmentation data,
        # use either CHGCAR or POT first
        got_aug_data = False
        for schema_k in ("CHGCAR", "POT"):
            for schema_idx, fname in enumerate(self.file_names):
                if schema_k == fname:
                    got_aug_data = True
                    break
            if got_aug_data:
                break

        if not got_aug_data:
            schema_idx = 0

        tables = []
        for idx in [schema_idx] + [
            i for i in range(len(self.file_names)) if i != schema_idx
        ]:
            table = self.volumetric_archives[idx].to_arrow()
            table = table.append_column("file_name", pa.array([self.file_names[idx]]))
            table = table.append_column("identifier", pa.array([self.identifier]))
            tables.append(table)

        vol_data_table = pa.concat_tables(tables, promote_options="permissive")
        pq.write_table(vol_data_table, file_name, **kwargs)

    @classmethod
    def _extract_from_parquet(
        cls,
        archive_path: str | Path,
        file_names: list[str] | None = None,
        filters: list[tuple[str, str, Any]] | None = None,
    ) -> list[dict[str, PmgVolumetricData | str]]:
        """Extract volumetric data from a parquet file.

        Defaults to extracting all available data within an archive.
        """
        file_names = (
            file_names
            or pq.read_table(
                archive_path,
                columns=[
                    "file_name",
                ],
            ).to_pylist()[0]
        )
        table = pq.read_table(archive_path, filters=filters)
        output_data: list[dict[str, PmgVolumetricData | str]] = []
        for identifier in set(table["identifier"].to_pylist()):
            if identifier is None:
                id_filter = ~pa.compute.field("identifier").is_valid()
            else:
                id_filter = pa.compute.field("identifier") == identifier

            for file_name in set([f for f in table.filter(id_filter)["file_name"]]):
                output_data.append(
                    {
                        "identifier": identifier,
                        "file_name": file_name,
                        "data": VolumetricArchive.from_arrow(
                            table.filter(
                                id_filter & (pa.compute.field("file_name") == file_name)
                            )
                        ),
                    }
                )

        return output_data
