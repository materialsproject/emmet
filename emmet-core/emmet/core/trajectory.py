from __future__ import annotations

from enum import Enum
import numpy as np
from pydantic import BaseModel, Field
from pathlib import Path
from typing import Literal, TYPE_CHECKING

from pymatgen.core import Element, Structure
from pymatgen.core.trajectory import Trajectory as PmgTrajectory

from monty.dev import requires
from monty.io import zopen
from monty.serialization import dumpfn

from emmet.core.math import Vector3D, Matrix3D
from emmet.core.tasks import TaskDoc
from emmet.core.vasp.calculation import ElectronicStep

try:
    import pyarrow as pa
    import pyarrow.parquet as pa_pq

except ImportError:
    pa = None
    pa_pq = None

if TYPE_CHECKING:
    from collections.abc import Sequence


class TrajFormat(Enum):

    PMG = "pmg"
    ASE = "ase"
    ARROW = "arrow"
    PARQUET = "parquet"

class Trajectory(BaseModel):

    elements : list[int] = Field(description="The proton number Z of the elements in the sites")

    cart_coords : list[list[Vector3D]] = Field(description="The Cartesian coordinates (Å) of the sites at each ionic step")
    num_ionic_steps : int = Field(description="The number of ionic steps.")

    constant_lattice : Matrix3D | None = Field(None, description="The constant lattice throughout the trajectory. If not populated, it is assumed that the lattice varies.")
    lattice : list[Matrix3D] | None = Field(None, description="The lattice at each ionic step. If not populated, it is assumed the lattice is constant through the trajectory.")
    
    electronic_steps : list[list[ElectronicStep]] | None = Field(None, description="The electronic steps within a given ionic step.")
    num_electronic_steps : list[int] | None = Field(None, description="The number of electronic steps within each ionic step.")

    energy : list[float] | None = Field(None, description="The total energy in eV at each ionic step. This key is also called e_0_energy.")
    e_wo_entrp : list[float] | None = Field(None, description="The total energy in eV without electronic pseudoentropy from smearing of the Fermi surface.")
    e_fr_energy : list[float] | None = Field(None, description="The total electronic free energy in eV.")
    forces : list[list[Vector3D]] | None = Field(None, description="The interatomic forces in eV/Å at each ionic step.")
    stress : list[Matrix3D] | None = Field(None, description="The 3x3 stress tensor in kilobar at each ionic step.")

    def __hash__(self):
        return hash(self.model_dump_json())

    @staticmethod
    def reorder_structure(structure: Structure, ref_z : list[int]) -> Structure:

        if [site.species.elements[0].Z for site in structure] == ref_z:
            return structure

        running_sites = list(range(len(structure)))
        ordered_sites = []
        for z in ref_z:
            for idx in running_sites:
                if structure[idx].species.elements[0].Z == z:
                    ordered_sites.append(structure[idx])
                    running_sites.remove(idx)
                    break

        if len(running_sites) > 0:
            raise ValueError("Cannot order structure according to reference list.")

        return Structure.from_sites(ordered_sites)
    
    @classmethod
    def _from_dict(cls, props: dict[str,list], constant_lattice : bool = False, lattice_match_tol : float | None = 1.e-6):

        structures = props.pop("structure")
        if any(not structure.is_ordered for structure in structures):
            raise ValueError("At this time, the Trajectory model in emmet does not support disordered structures.")
        
        props["num_ionic_steps"] = len(structures)

        props["elements"] = [site.species.elements[0].Z for site in structures[0]]
        if (
            constant_lattice
            or (
                lattice_match_tol and all(
                    np.all(
                        np.abs(structures[i].lattice.matrix - structures[j].lattice.matrix) < lattice_match_tol
                    ) 
                    for i in range(props["num_ionic_steps"])
                    for j in range(i+1, props["num_ionic_steps"])
                )
            )
        ):
            props["constant_lattice"] = structures[0].lattice.matrix
        else:
            props["lattice"] = [structure.lattice.matrix for structure in structures]

        props["cart_coords"] = [
            cls.reorder_structure(structure, props["elements"]).cart_coords for structure in structures
        ]
        
        if len(esteps := props.get("electronic_steps",[])) > 0:
            props["num_electronic_steps"] = [len(estep) for estep in esteps]

        return cls(**props)


    @classmethod
    def from_task_doc(cls, task_doc : TaskDoc, **kwargs):
        
        props = {
            "structure": [],
            "cart_coords": [],
            "electronic_steps": [],
            "energy": [],
            "e_wo_entrp": [],
            "e_fr_energy": [],
            "forces": [],
            "stress": [],
        }
        # un-reverse the calcs_reversed
        for cr in task_doc.calcs_reversed[::-1]:
            for ionic_step in cr.output.ionic_steps:
                props["structure"].append(ionic_step.structure)

                props["energy"].append(ionic_step.e_0_energy)
                for k in ("e_fr_energy","e_wo_entrp", "forces", "stress", "electronic_steps"):
                    props[k].append(getattr(ionic_step,k))

        return cls._from_dict(props,**kwargs)

    @classmethod
    def from_pmg(cls, traj : PmgTrajectory, **kwargs):

        props = {
            "structure": [structure for structure in traj],
        }
        for k in cls.model_fields:
            vals = [fp.get(k) for fp in traj.frame_properties]
            if all(v is not None for v in vals):
                props[k] = vals

        return cls._from_dict(props,**kwargs)


    @requires(pa is not None, message = "pyarrow must be installed to de-/serialize to parquet")
    def to_arrow(self, file_name : str | Path | None = None):

        pa_config = {
            k: pa.array(v)
            for k, v in self.model_dump(mode="json").items()
            if hasattr(v,"__len__")
        }
        pa_config["elements"] = pa.array([self.elements for _ in range(self.num_ionic_steps)])
        
        pa_table = pa.table(pa_config)
        if file_name:
            with zopen(str(file_name),"wb") as f:
                pa_pq.write_table(pa_table,f)

        return pa_table
    
    @classmethod
    def from_parquet(cls, file_name : str | Path):
        with zopen(str(file_name),"rb") as f:
            pa_table = pa_pq.read_table(f)
        config = pa_table.to_pydict()
        config["num_ionic_steps"] = len(config["elements"])
        config["elements"] = config["elements"][0]
        return cls(**config)
    
    def to_pmg(self, frame_props : Sequence[str] | None = None):

        frame_props = frame_props or [
            "energy","e_wo_entrp", "e_fr_energy", "forces", "stress", "electronic_steps"
        ]

        species = [Element.from_Z(z) for z in self.elements]
        structures = []
        frame_properties = []
        
        for i, coords in enumerate(self.cart_coords):
            structure = Structure(
                lattice = self.constant_lattice if self.constant_lattice else self.lattice[i],
                species = species,
                coords=coords,
                coords_are_cartesian=True,
            )
            structures.append(structure)
            
            props = {}
            for k in frame_props:
                if (prop := getattr(self,k,None)[i]) is not None:
                    for cmth in ("model_dump","tolist"):
                        if hasattr(prop,cmth):
                            prop = getattr(prop,cmth)()
                    props[k] = prop

            frame_properties.append(props)

        return PmgTrajectory.from_structures(
            structures,
            constant_lattice=self.constant_lattice is not None, 
            frame_properties=frame_properties
        )

    def to(self, fmt : TrajFormat | str = TrajFormat.PMG, file_name : str | Path | None = None, **kwargs):

        fmt = TrajFormat(fmt)

        if fmt in (TrajFormat.PMG, TrajFormat.ASE):
            traj = self.to_pmg(**kwargs)
            
            if fmt == "pmg":
                if file_name:
                    dumpfn(traj, file_name)
            else:
                traj = traj.to_ase(ase_traj_file=file_name)

        elif fmt in (TrajFormat.ARROW, TrajFormat.PARQUET):
            traj = self.to_arrow(file_name = None if fmt == "arrow" else file_name)

        return traj