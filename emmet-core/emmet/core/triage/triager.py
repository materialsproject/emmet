from __future__ import annotations

import numpy as np
from pymatgen.core import Element

from typing import Sequence, TYPE_CHECKING

if TYPE_CHECKING:
    from pymatgen.core import Structure

    from filter import Filter


class Triager:
    default_radii: Sequence[str] = ("Atomic radius", "Ionic radii", "Metallic radius")
    filters: Sequence[Filter] = ()
    coord_env: str = "CrystalNN"

    def __init__(
        self, structure: Structure, coordination_envs: list, potcars: list[str]
    ):
        self.assessment = {
            "structure": structure,
            "potcar_titels": potcars,
            "magmom": structure.site_properties.get(
                "magmom", [0.0 for _ in range(len(structure))]
            ),
            "coordination_envs": coordination_envs,
        }

        if self.coord_env == "StructureGraph":
            # keeping here in case it proves useful later
            for icoord in range(len(self.assessment["coordination_envs"])):
                for unchg_char in ["0+", "0-"]:
                    self.assessment["coordination_envs"][icoord] = self.assessment[
                        "coordination_envs"
                    ][icoord].replace(unchg_char, "")

            self.interpret_coordination_envs()

        elif self.coord_env == "CrystalNN":
            self.CrystalNN_coordination_numers()

        self.assessment["max CN"] = max(self._coordination_numbers)

        composition = structure.composition.as_dict()
        total_num_atoms = sum(list(composition.values()))
        pcomp = np.array(
            [100.0 * stoich / total_num_atoms for stoich in composition.values()]
        )

        self.assessment["min pcomp"] = pcomp.min()
        self.assessment["avg pcomp"] = np.sum(pcomp) / len(pcomp)
        self.assessment["max pcomp"] = pcomp.max()

        self.get_atomic_radii()

        self.get_filter_values_from_assessment()
        self.triage()

    def CrystalNN_coordination_numers(self):
        self._coordination_numbers = [
            sum(self.assessment["coordination_envs"][isite].values())
            for isite in range(len(self.assessment["structure"]))
        ]

    def interpret_coordination_envs(self):
        coordination = {}
        self._coordination_numbers = []
        for coord_env_str in self.assessment["coordination_envs"]:
            envs = coord_env_str.split(",")
            for env in envs:
                if len(env.split("(")) == 1:
                    # failure of the coordination environment prediction?
                    continue
                spec, cn = env.split("(")
                cn = int(cn.split(")")[0])
                specs = spec.split("-")
                for ichar in range(len(specs)):
                    if len(specs[ichar]) == 0:
                        specs[ichar - 1] += "-"
                specs = [x for x in specs if x != ""]
                if len(specs) > 1:
                    site_atom = specs[0]
                    coordination[site_atom] = {}
                coordination[site_atom][specs[-1]] = cn
        for site_atom in coordination:
            self._coordination_numbers.append(sum(coordination[site_atom].values()))
        return

    def get_atomic_packing_density(self, radii: Sequence[float]):
        atomic_volume = 4 * np.pi * np.sum(np.array(radii) ** 3) / 3.0
        return atomic_volume / self.assessment["structure"].volume

    def get_atomic_radii(self, fallback: str | None = "Van der waals radius"):
        radii_to_try = set(self.default_radii)

        radii = {
            radius_name: np.zeros(len(self.assessment["structure"]))
            for radius_name in radii_to_try.union({fallback} if fallback else set())
        }

        radii_to_exclude = set()

        for isite in range(len(self.assessment["structure"])):
            element = Element(self.assessment["structure"].sites[isite].specie.name)
            for radius_name in radii:
                radius = element.data.get(radius_name, None)
                if radius_name == "Ionic radii" and isinstance(radius, dict):
                    ionic_radii = {int(key): radius[key] for key in radius}

                    oxi_state = 0
                    if (
                        len(
                            self.assessment["structure"]
                            .sites[isite]
                            .specie.oxidation_states
                        )
                        > 0
                    ):
                        oxi_state = (
                            self.assessment["structure"]
                            .sites[isite]
                            .specie.oxidation_states[0]
                        )

                    # if oxidation state is integer-valued, try getting ionic
                    # radius directly from PMG
                    radius = ionic_radii.get(oxi_state, None)
                    if radius is None and abs(int(oxi_state) - oxi_state) < 1.0e-15:
                        radius = ionic_radii.get(int(oxi_state), None)

                    if radius is None and len(ionic_radii) > 1:
                        chg = np.array(list(ionic_radii.keys()))
                        srtind = np.argsort(chg)
                        chg = chg[srtind]
                        ion_rad = np.array(list(ionic_radii.values()))[srtind]

                        if chg.min() <= oxi_state <= chg.max():
                            isrt = np.searchsorted(chg, oxi_state, side="left")
                            slope = (ion_rad[isrt] - ion_rad[isrt - 1]) / (
                                chg[isrt] - chg[isrt - 1]
                            )
                            icpt = ion_rad[isrt] - chg[isrt] * slope
                            radius = icpt + slope * oxi_state

                            # probably not necessary but being safe
                            if radius < 0.0:
                                radius = None

                if radius in [None, "no data"]:
                    radii_to_exclude = radii_to_exclude.union({radius_name})
                else:
                    radii[radius_name][isite] = radius

        radii_to_try = radii_to_try.difference(radii_to_exclude)
        radii = {
            radius_name: radii[radius_name]
            for radius_name in radii
            if radius_name not in radii_to_exclude
        }

        self.assessment["packing density"] = {
            radius_name: self.get_atomic_packing_density(radii[radius_name])
            for radius_name in radii_to_try
        }

        if len(radii_to_try) == 0 and (fallback in radii):
            # use vdW radius as fall back
            self.assessment["packing density"][
                fallback
            ] = self.get_atomic_packing_density(radii[fallback])

    def get_filter_values_from_assessment(self):
        # to be added by the user
        return NotImplementedError

    def triage(self):
        self.reasons = []

        self.triage = {}
        for _filter in self.filters:
            filter_name = _filter.__name__
            t = _filter().eval(self._filter_values[filter_name])
            self.triage[filter_name] = {k: v for k, v in t.items() if k != "reason"}
            if isinstance(self.triage[filter_name]["value"], set):
                self.triage[filter_name]["value"] = list(
                    self.triage[filter_name]["value"]
                )

            if t["reason"] is not None:
                self.reasons.append(t["reason"])

        self.passed = len(self.reasons) == 0

    def as_dict(self):
        return {
            "assessment": self.assessment,
            "triage": self.triage,
            "reasons": self.reasons,
            "passed": self.passed,
        }
