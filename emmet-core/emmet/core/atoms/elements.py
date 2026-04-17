"""Define elements / isotopes."""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from typing import Any


class Element(StrEnum):
    """Map short chemical symbol to long name."""

    H = "Hydrogen"
    He = "Helium"
    Li = "Lithium"
    Be = "Beryllium"
    B = "Boron"
    C = "Carbon"
    N = "Nitrogen"
    O = "Oxygen"
    F = "Fluorine"
    Ne = "Neon"
    Na = "Sodium"
    Mg = "Magnesium"
    Al = "Aluminum"
    Si = "Silicon"
    P = "Phosphorus"
    S = "Sulfur"
    Cl = "Chlorine"
    Ar = "Argon"
    K = "Potassium"
    Ca = "Calcium"
    Sc = "Scandium"
    Ti = "Titanium"
    V = "Vanadium"
    Cr = "Chromium"
    Mn = "Manganese"
    Fe = "Iron"
    Co = "Cobalt"
    Ni = "Nickel"
    Cu = "Copper"
    Zn = "Zinc"
    Ga = "Gallium"
    Ge = "Germanium"
    As = "Arsenic"
    Se = "Selenium"
    Br = "Bromine"
    Kr = "Krypton"
    Rb = "Rubidium"
    Sr = "Strontium"
    Y = "Yttrium"
    Zr = "Zirconium"
    Nb = "Niobium"
    Mo = "Molybdenum"
    Tc = "Technetium"
    Ru = "Ruthenium"
    Rh = "Rhodium"
    Pd = "Palladium"
    Ag = "Silver"
    Cd = "Cadmium"
    In = "Indium"
    Sn = "Tin"
    Sb = "Antimony"
    Te = "Tellurium"
    I = "Iodine"
    Xe = "Xenon"
    Cs = "Cesium"
    Ba = "Barium"
    La = "Lanthanum"
    Ce = "Cerium"
    Pr = "Praseodymium"
    Nd = "Neodymium"
    Pm = "Promethium"
    Sm = "Samarium"
    Eu = "Europium"
    Gd = "Gadolinium"
    Tb = "Terbium"
    Dy = "Dysprosium"
    Ho = "Holmium"
    Er = "Erbium"
    Tm = "Thulium"
    Yb = "Ytterbium"
    Lu = "Lutetium"
    Hf = "Hafnium"
    Ta = "Tantalum"
    W = "Tungsten"
    Re = "Rhenium"
    Os = "Osmium"
    Ir = "Iridium"
    Pt = "Platinum"
    Au = "Gold"
    Hg = "Mercury"
    Tl = "Thallium"
    Pb = "Lead"
    Bi = "Bismuth"
    Po = "Polonium"
    At = "Astatine"
    Rn = "Radon"
    Fr = "Francium"
    Ra = "Radium"
    Ac = "Actinium"
    Th = "Thorium"
    Pa = "Protactinium"
    U = "Uranium"
    Np = "Neptunium"
    Pu = "Plutonium"
    Am = "Americium"
    Cm = "Curium"
    Bk = "Berkelium"
    Cf = "Californium"
    Es = "Einsteinium"
    Fm = "Fermium"
    Md = "Mendelevium"
    No = "Nobelium"
    Lr = "Lawrencium"
    Rf = "Rutherfordium"
    Db = "Dubnium"
    Sg = "Seaborgium"
    Bh = "Bohrium"
    Hs = "Hassium"
    Mt = "Meitnerium"
    Ds = "Darmstadtium"
    Rg = "Roentgenium"
    Cn = "Copernicium"
    Nh = "Nihonium"
    Fl = "Flerovium"
    Mc = "Moscovium"
    Lv = "Livermorium"
    Ts = "Tennessine"
    Og = "Oganesson"

    @classmethod
    def _missing_(cls, value: Any) -> "Element" | None:
        """Permit search for element based on symbol or name."""
        if value in cls:
            return cls(value)
        elif value in cls.__members__:
            return cls[value]


class ElementData(BaseModel):
    """Data for the elements."""

    Z: int = Field(description="The number of protons in this element")
    atomic_mass: float = Field(
        description="The atomic mass (number of protons + neutrons) in atomic mass units (amu)"
    )


class ElementDatabase(dict):

    def _load_data(self) -> dict[Element, ElementData]:
        """Cache atom data from pymatgen."""
        from pymatgen.core.periodic_table import Element as PmgElement

        # ignore isotopes
        type_map = {e: PmgElement(e.name) for e in Element}
        self.update(
            {
                ele: ElementData(Z=pmg_ele.Z, atomic_mass=pmg_ele.atomic_mass)
                for ele, pmg_ele in type_map.items()
            }
        )

    def __init__(self, **kwargs) -> None:
        self._load_data()


ELEMENT_DATA = ElementDatabase()
