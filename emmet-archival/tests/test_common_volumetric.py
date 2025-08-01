"""Test common volumetric objects."""

import numpy as np

from pymatgen.electronic_structure.core import Spin

from emmet.archival.volumetric import ElectronicDos


def test_electronic_dos():
    rs = 4.0
    efermi = (9 * np.pi / 4.0) ** (1 / 3) / rs
    energies = np.linspace(0, 3 * efermi, 200)
    heg_dos = (2 * energies) ** (0.5) / np.pi**2

    for spin_pol in (1, 0.5):
        edos = ElectronicDos(
            spin_up=spin_pol * heg_dos,
            spin_down=spin_pol * heg_dos if spin_pol < 1 else None,
            energies=energies,
            efermi=efermi,
        )

        spins_to_check = [Spin.up]
        pmg_dos = edos.to_pmg()
        if spin_pol < 1:
            spins_to_check.append(Spin.down)
        else:
            assert pmg_dos.densities.get(Spin.down) is None

        for spin in spins_to_check:
            assert np.all(
                np.abs(
                    np.array(getattr(edos, f"spin_{spin.name}"))
                    - pmg_dos.densities[spin]
                )
                < 1e-6
            )
