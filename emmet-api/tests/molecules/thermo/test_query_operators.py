from emmet.api.routes.molecules.thermo.query_operators import ThermoCorrectionQuery
from monty.tempfile import ScratchDir
from monty.serialization import loadfn, dumpfn


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

    with ScratchDir("."):
        dumpfn(op, "temp.json")
        new_op = loadfn("temp.json")
        assert new_op.query(
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
