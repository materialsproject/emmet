from emmet.api.routes.molecules.thermo.query_operators import ThermoCorrectionQuery


def test_thermo_correction_query():
    op = ThermoCorrectionQuery()
    assert op.query(
        has_correction=True,
        correction_level_of_theory="wB97M-V/def2-QZVPPD/SMD",
        correction_solvent="SOLVENT=WATER",
        correction_lot_solvent="wB97M-V/def2-QZVPPD/SMD(SOLVENT=WATER)",
        combined_lot_solvent="wB97M-V/def2-SVPD/SMD(SOLVENT=WATER)//wB97M-V/def2-QZVPPD/SMD(SOLVENT=WATER)",
    ) == {
        "criteria": {
            "correction": True,
            "correction_level_of_theory": "wB97M-V/def2-QZVPPD/SMD",
            "correction_solvent": "SOLVENT=WATER",
            "correction_lot_solvent": "wB97M-V/def2-QZVPPD/SMD(SOLVENT=WATER)",
            "combined_lot_solvent": "wB97M-V/def2-SVPD/SMD(SOLVENT=WATER)//wB97M-V/def2-QZVPPD/SMD(SOLVENT=WATER)",
        }
    }
