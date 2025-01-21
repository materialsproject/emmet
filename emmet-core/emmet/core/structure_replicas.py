"""Tools for representing pymatgen objects as low-memory, strongly typed objects."""

from __future__ import annotations
from collections.abc import Iterator
from pydantic import BaseModel, Field

from enum import Enum
from typing import TYPE_CHECKING

import numpy as np

from pymatgen.core import Structure, PeriodicSite, Lattice, Element
from pymatgen.io.vasp import Poscar

from emmet.core.math import Vector3D, Matrix3D, ListMatrix3D

if TYPE_CHECKING:
    from pathlib import Path
    from typing import Any
    from typing_extensions import Self

class EmmetReplica(BaseModel):
    """Define strongly typed, fixed schema versions of generic pymatgen objects."""

    @classmethod
    def from_pymatgen(cls, pmg_obj : Any) -> Self:
        """Convert pymatgen objects to an EmmetReplica representation."""
        raise NotImplementedError

    def to_pymatgen(self) -> Any:
        """Convert EmmetReplica object to pymatgen equivalent."""
        raise NotImplementedError
    
    @classmethod
    def from_dict(cls, dct : dict[str,Any]) -> Self:
        """MSONable-like function to create this object from a dict."""
        raise NotImplementedError

    def as_dict(self) -> dict[str,Any]:
        """MSONable-like function to create dict representation of this object."""
        raise NotImplementedError


class SiteProperties(Enum):
    """Define a restricted set of structure site properties."""

    magmom = "magmom"
    charge = "charge"
    velocities = "velocities"
    selective_dynamics = "selective_dynamics"

class ElementSymbol(Enum):
    """Lightweight representation of a chemical element."""

    H = 1
    He = 2
    Li = 3
    Be = 4
    B = 5
    C = 6
    N = 7
    O = 8
    F = 9
    Ne = 10
    Na = 11
    Mg = 12
    Al = 13
    Si = 14
    P = 15
    S = 16
    Cl = 17
    Ar = 18
    K = 19
    Ca = 20
    Sc = 21
    Ti = 22
    V = 23
    Cr = 24
    Mn = 25
    Fe = 26
    Co = 27
    Ni = 28
    Cu = 29
    Zn = 30
    Ga = 31
    Ge = 32
    As = 33
    Se = 34
    Br = 35
    Kr = 36
    Rb = 37
    Sr = 38
    Y = 39
    Zr = 40
    Nb = 41
    Mo = 42
    Tc = 43
    Ru = 44
    Rh = 45
    Pd = 46
    Ag = 47
    Cd = 48
    In = 49
    Sn = 50
    Sb = 51
    Te = 52
    I = 53
    Xe = 54
    Cs = 55
    Ba = 56
    La = 57
    Ce = 58
    Pr = 59
    Nd = 60
    Pm = 61
    Sm = 62
    Eu = 63
    Gd = 64
    Tb = 65
    Dy = 66
    Ho = 67
    Er = 68
    Tm = 69
    Yb = 70
    Lu = 71
    Hf = 72
    Ta = 73
    W = 74
    Re = 75
    Os = 76
    Ir = 77
    Pt = 78
    Au = 79
    Hg = 80
    Tl = 81
    Pb = 82
    Bi = 83
    Po = 84
    At = 85
    Rn = 86
    Fr = 87
    Ra = 88
    Ac = 89
    Th = 90
    Pa = 91
    U = 92
    Np = 93
    Pu = 94
    Am = 95
    Cm = 96
    Bk = 97
    Cf = 98
    Es = 99
    Fm = 100
    Md = 101
    No = 102
    Lr = 103
    Rf = 104
    Db = 105
    Sg = 106
    Bh = 107
    Hs = 108
    Mt = 109
    Ds = 110
    Rg = 111
    Cn = 112
    Nh = 113
    Fl = 114
    Mc = 115
    Lv = 116
    Ts = 117
    Og = 118

    @property
    def Z(self) -> int:
        """The number of protons in the element."""
        return self.value

    def __str__(self):
        """Get element name."""
        return self.name

class LightLattice(tuple):
    """Low memory representation of a Lattice as a tuple of a 3x3 matrix."""

    def __new__(cls, matrix):
        """Overset __new__ to define new tuple instance."""
        lattice_matrix = np.array(matrix)
        if lattice_matrix.shape != (3, 3):
            raise ValueError("Lattice matrix must be 3x3.")
        return super(LightLattice,cls).__new__(cls,tuple([tuple(v) for v in lattice_matrix.tolist()]))

    def as_dict(self) -> dict[str, list | str]:
        """Define MSONable-like as_dict."""
        return {"@class": self.__class__, "@module": self.__module__, "matrix": self}

    @classmethod
    def from_dict(cls, dct: dict) -> Self:
        """Define MSONable-like from_dict."""
        return cls(dct["matrix"])

    def copy(self) -> Self:
        """Return a new copy of LightLattice."""
        return LightLattice(self)

    @property
    def volume(self) -> float:
        """Get the volume enclosed by the direct lattice vectors."""
        return abs(np.linalg.det(self))


class ElementReplica(EmmetReplica):
    """Define a flexible schema for elements and periodic sites.
    
    The only required field in this model is `element`.
    This is intended to mimic a `pymatgen` `.Element` object.
    Additionally, the `lattice` and coordinates of the site can be specified
    to mimic a `pymatgen` `.PeriodicSite`.

    Parameters
    -----------
    element (required) : ElementSymbol
        The symbol of the element.
    lattice (optional) : Matrix3D
        The 3x3 representation of the lattice the site exists in.
    cart_coords (optional) : Vector3D
        A tuple of 3 floats specifying the position of the site in Cartesian space.
    frac_coords (optional) : Vector3D
        A tuple of 3 floats specifying the position of the site in units of the
        direct lattice vectors.
    charge (optional) : float
        The charge (either from the electron density or oxidation state) on the site.
    magmom (optional) : float
        The on-site magnetic moment.
    velocities (optional) : Vector3D
        A tuple of 3 floats specifying the Cartesian components of the site velocity.
    selective_dynamics (optional) : tuple[bool, bool, bool]
        A tuple of 3 booleans specifying which Cartesian directions the site position
        was allowed to relax on.
    """

    element : ElementSymbol = Field(description="The element.")
    lattice : Matrix3D | None = Field(default = None, description="The lattice in 3x3 matrix form.")
    cart_coords : Vector3D | None = Field(default = None, description="The postion of the site in Cartesian coordinates.")
    frac_coords : Vector3D | None = Field(default = None, description="The postion of the site in direct lattice vector coordinates.")
    charge : float | None = Field(default = None, description="The on-site charge.")
    magmom : float | None = Field(default = None, description="The on-site magnetic moment.")
    velocities : Vector3D | None = Field(default = None, description="The Cartesian components of the site velocity.")
    selective_dynamics : tuple[bool, bool, bool] | None = Field(default = None, description="The degrees of freedom which are allowed to relax on the site.")

    def model_post_init(self, __context : Any) -> None:
        """Ensure both Cartesian and direct coordinates are set, if necessary."""
        if self.lattice:
            if self.cart_coords is not None:
                self.frac_coords = self.frac_coords or np.linalg.solve(
                        np.array(self.lattice).T, np.array(self.cart_coords)
                    )
            elif self.frac_coords is not None:
                self.cart_coords = self.cart_coords or tuple(
                    np.matmul(np.array(self.lattice).T, np.array(self.frac_coords))
                )
        
    @classmethod
    def from_pymatgen(cls, pmg_obj : Element | PeriodicSite) -> Self:
        """Convert a pymatgen .PeriodicSite or .Element to .ElementReplica.
        
        Parameters
        -----------
        site : pymatgen .Element or .PeriodicSite
        """
        if isinstance(pmg_obj, Element):
            return cls(element = ElementSymbol(pmg_obj.name))

        return cls(
            element = ElementSymbol(next(iter(pmg_obj.species.remove_charges().as_dict()))),
            lattice = LightLattice(pmg_obj.lattice.matrix),
            frac_coords = pmg_obj.frac_coords,
            cart_coords = pmg_obj.coords,
        )

    def to_pymatgen(self) -> PeriodicSite:
        """Create a PeriodicSite from a ElementReplica."""
        return PeriodicSite(
            self.element.name,
            self.frac_coords,
            Lattice(self.lattice),
            coords_are_cartesian=False,
            properties = self.properties
        )

    @property
    def species(self) -> dict[str,int]:
        """Composition-like representation of site."""
        return {self.element.name : 1}

    @property
    def properties(self) -> dict[str,float]:
        """Aggregate optional properties defined on the site."""
        props = {}
        for k in SiteProperties.__members__:
            if (prop := getattr(self,k,None)) is not None:
                props[k] = prop
        return props

    def __int__(self) -> int:
        """Ensure pymatgen's get_el_sp recognizes this class as an element."""
        return self.element.Z

    def __float__(self) -> float:
        """Ensure pymatgen's get_el_sp recognizes this class as an element."""
        return float(self.element.Z)

    @property
    def elements(self) -> list[ElementSymbol]:
        """Ensure compatibility with PeriodicSite."""
        return [self.element]

    @property
    def Z(self) -> int:
        """Ensure compatibility with PeriodicSite."""
        return self.element.Z

    @property
    def name(self) -> str:
        """Ensure compatibility with PeriodicSite."""
        return self.element.name
    
    @property
    def species_string(self) -> str:
        """Ensure compatibility with PeriodicSite."""
        return self.name

    @property
    def label(self) -> str:
        """Ensure compatibility with PeriodicSite."""
        return self.name

    def __str__(self):
        return self.label
    
    def add_attrs(self, **kwargs) -> ElementReplica:
        """Rapidly create a copy of this instance with additional fields set.
        
        Parameters
        -----------
        **kwargs
            Any of the fields defined in the model. This function is used to
            add lattice and coordinate information to each site, and thereby
            not store it in the StructureReplica object itself in addition to
            each site.
        
        Returns
        -----------
            ElementReplica
        """
        config = self.model_dump()
        config.update(**kwargs)
        return ElementReplica(**config)

class StructureReplica(BaseModel):
    """Define a fixed schema structure.

    This class is intended to provide both a fixed schema for a generic structure,
    and to reduce the memory footprint over a pymatgen .Structure.
    To do this, the `lattice`, `frac_coords` and `cart_coords` are stored only on the
    `StructureReplica`.
    When the `.sites` attr of `StructureReplica` is accessed, all prior attributes
    (respective aliases: `lattice`, `frac_coords`, and `coords`) are assigned to the
    retrieved sites.
    Compare this to pymatgen's .Structure, which stores the `lattice`, `frac_coords`, 
    and `cart_coords` both in the .Structure object and each .PeriodicSite within it.

    
    Parameters
    -----------
    lattice : LightLattice
        A 3x3 tuple of the lattice vectors, with a, b, and c as subsequent rows.
    species : list[ElementReplica]
        A list of elements in the structure
    frac_coords : ListMatrix3D
        A list of 3-vectors corresponding to the coordinates of each site in units of
        the direct lattice vectors.
    cart_coords : ListMatrix3D
        A list of 3-vectors corresponding to the Cartesian coordinates of each site.
    charge (optional) : float
        The total charge on the structure.
    """
    
    lattice : LightLattice = Field(description="The lattice in 3x3 matrix form.")
    species : list[ElementReplica] = Field(description="The elements in the structure.")
    frac_coords : ListMatrix3D = Field(description="The direct coordinates of the sites in the structure.")
    cart_coords : ListMatrix3D = Field(description="The Cartesian coordinates of the sites in the structure.")
    charge : float | None = Field(None, description="The net charge on the structure.")

    @property
    def sites(self) -> list[ElementReplica]:
        """Return a list of sites in the structure with lattice and coordinate info."""
        return [
            species.add_attrs(
                lattice = self.lattice,
                cart_coords = self.cart_coords[idx],
                frac_coords = self.frac_coords[idx],
            )
            for idx, species in enumerate(self.species)
        ]

    def __getitem__(self, idx: int | slice) -> ElementReplica | list[ElementReplica]:
        """Permit list-like access of the sites in StructureReplica."""
        if isinstance(idx, int) or isinstance(idx, slice):
            return self.sites[idx]
        raise IndexError("Index must be an integer or slice!")

    def __iter__(self) -> Iterator[ElementReplica]:
        """Permit list-like iteration on the sites in StructureReplica."""
        yield from self.sites

    @property
    def volume(self) -> float:
        """Get the volume enclosed by the direct lattice vectors."""
        return self.lattice.volume

    def __len__(self) -> int:
        """Define number of sites in StructureReplica."""
        return len(self.species)

    @property
    def num_sites(self) -> int:
        """Define number of sites in StructureReplica."""
        return self.__len__()

    @classmethod
    def from_pymatgen(cls, pmg_obj: Structure) -> Self:
        """Create a StructureReplica from a pymatgen .Structure.
        
        Parameters
        -----------
        pmg_obj : pymatgen .Structure

        Returns
        -----------
            StructureReplica
        """
        if not pmg_obj.is_ordered:
            raise ValueError(
                "Currently, `StructureReplica` is intended to represent only ordered materials."
            )
        
        lattice = LightLattice(pmg_obj.lattice.matrix)
        properties = [{} for _ in range(len(pmg_obj))]
        for idx, site in enumerate(pmg_obj):
            for k in ("charge","magmom","velocities","selective_dynamics"):
                if (prop := site.properties.get(k)) is not None:
                    properties[idx][k] = prop

        species = [
            ElementReplica(
                element = ElementSymbol[next(iter(site.species.remove_charges().as_dict()))],
                **properties[idx]
            )
            for idx, site in enumerate(pmg_obj)
        ]

        return cls(
            lattice=lattice,
            species = species,
            frac_coords = [site.frac_coords for site in pmg_obj],
            cart_coords = [site.coords for site in pmg_obj],
            charge = pmg_obj.charge,
        )
    
    def to_pymatgen(self) -> Structure:
        """Convert to a pymatgen .Structure."""
        return Structure.from_sites([site.to_periodic_site() for site in self], charge = self.charge)
            
    @classmethod
    def from_poscar(cls, poscar_path: str | Path) -> Self:
        """Define convenience method to create a StructureReplica from a VASP POSCAR."""
        return cls.from_structure(Poscar.from_file(poscar_path).structure)

    def __str__(self):
        """Define format for printing a Structure."""
        def _format_float(val: float | int) -> str:
            nspace = 2 if val >= 0.0 else 1
            return " " * nspace + f"{val:.8f}"

        lattice_str = [
            [_format_float(self.lattice[i][j]) for j in range(3)] for i in range(3)
        ]
        coords_str = [
            [_format_float(self.cart_coords[i][j]) for j in range(3)]
            for i in range(len(self))
        ]
        as_str = "Lattice\n"
        as_str += "\n".join(
            f"{name}  : " + ",".join(lattice_str[idx])
            for idx, name in enumerate(["a", "b", "c"])
        )
        as_str += "\nCartesian Coordinates\n"

        as_str += "\n".join(
            f"{self[idx].element}{' '*(3-len(str(self[idx].element)))}: "
            + ",".join(site_str)
            for idx, site_str in enumerate(coords_str)
        )
        return as_str
