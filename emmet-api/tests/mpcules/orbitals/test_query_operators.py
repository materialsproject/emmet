from emmet.api.routes.mpcules.orbitals.query_operators import (
    NBOPopulationQuery,
    NBOLonePairQuery,
    NBOBondQuery,
    NBOInteractionQuery
)
from monty.tempfile import ScratchDir
from monty.serialization import loadfn, dumpfn


def test_nbo_population_query():
    op = NBOPopulationQuery()
    assert op.query(
        open_shell=True,
        electron_type="beta",
        min_core_electron=10.0,
        max_core_electron=11.0,
        min_valence_electron=0.0,
        max_valence_electron=2.0,
        min_rydberg_electron=0.0,
        max_rydberg_electron=1.0,
        min_total_electron=11.0,
        max_total_electron=12.0
    ) == {
        'criteria': {
            'open_shell': True,
            'beta_population.core_electrons': {'$gte': 10.0, '$lte': 11.0},
            'beta_population.valence_electrons': {'$gte': 0.0, '$lte': 2.0},
            'beta_population.rydberg_electrons': {'$gte': 0.0, '$lte': 1.0},
            'beta_population.total_electrons': {'$gte': 11.0, '$lte': 12.0}
        }
    }

    with ScratchDir("."):
        dumpfn(op, "temp.json")
        new_op = loadfn("temp.json")
        assert new_op.query(
            open_shell=True, 
            electron_type="beta",
            min_core_electron=10.0,
            max_core_electron=11.0,
            min_valence_electron=0.0,
            max_valence_electron=2.0,
            min_rydberg_electron=0.0,
            max_rydberg_electron=1.0,
            min_total_electron=11.0,
            max_total_electron=12.0
        ) == {
            'criteria': {
                'open_shell': True,
                'beta_population.core_electrons': {'$gte': 10.0, '$lte': 11.0},
                'beta_population.valence_electrons': {'$gte': 0.0, '$lte': 2.0},
                'beta_population.rydberg_electrons': {'$gte': 0.0, '$lte': 1.0},
                'beta_population.total_electrons': {'$gte': 11.0, '$lte': 12.0}
            }
        }


def test_nbo_lone_pair_query():
    op = NBOLonePairQuery()
    assert op.query(
        open_shell=True,
        electron_type="alpha",
        lp_type="LP",
        min_s_character=10.0,
        max_s_character=25.0,
        min_p_character=70.0,
        max_p_character=90.0,
        min_d_character=0.0,
        max_d_character=5.0,
        min_f_character=0.0,
        max_f_character=5.0,
        min_occupancy=1.5,
        max_occupancy=2.0
    ) == {
        'criteria': {
            'open_shell': True,
            'alpha_lone_pairs.s_character': {'$gte': 10.0, '$lte': 25.0},
            'alpha_lone_pairs.p_character': {'$gte': 70.0, '$lte': 90.0},
            'alpha_lone_pairs.d_character': {'$gte': 0.0, '$lte': 5.0},
            'alpha_lone_pairs.f_character': {'$gte': 0.0, '$lte': 5.0},
            'alpha_lone_pairs.occupancy': {'$gte': 1.5, '$lte': 2.0},
            'alpha_lone_pairs.type_code': 'LP'
        }
    }

    with ScratchDir("."):
        dumpfn(op, "temp.json")
        new_op = loadfn("temp.json")
        assert new_op.query(
            open_shell=True,
            electron_type="alpha",
            lp_type="LP",
            min_s_character=10.0,
            max_s_character=25.0,
            min_p_character=70.0,
            max_p_character=90.0,
            min_d_character=0.0,
            max_d_character=5.0,
            min_f_character=0.0,
            max_f_character=5.0,
            min_occupancy=1.5,
            max_occupancy=2.0
        ) == {
            'criteria': {
                'open_shell': True,
                'alpha_lone_pairs.s_character': {'$gte': 10.0, '$lte': 25.0},
                'alpha_lone_pairs.p_character': {'$gte': 70.0, '$lte': 90.0},
                'alpha_lone_pairs.d_character': {'$gte': 0.0, '$lte': 5.0},
                'alpha_lone_pairs.f_character': {'$gte': 0.0, '$lte': 5.0},
                'alpha_lone_pairs.occupancy': {'$gte': 1.5, '$lte': 2.0},
                'alpha_lone_pairs.type_code': 'LP'
            }
        }


def test_nbo_bond_query():
    op = NBOBondQuery()
    assert op.query(
        open_shell=False,
        bond_type="BD*",
        min_s_character_atom1=10.0,
        max_s_character_atom1=25.0,
        min_s_character_atom2=10.0,
        max_s_character_atom2=25.0,
        min_p_character_atom1=70.0,
        max_p_character_atom1=90.0,
        min_p_character_atom2=70.0,
        max_p_character_atom2=90.0,
        min_d_character_atom1=0.0,
        max_d_character_atom1=5.0,
        min_d_character_atom2=0.0,
        max_d_character_atom2=5.0,
        min_f_character_atom1=0.0,
        max_f_character_atom1=5.0,
        min_f_character_atom2=0.0,
        max_f_character_atom2=5.0,
        min_polarization_atom1=30.0,
        max_polarization_atom1=70.0,
        min_polarization_atom2=30.0,
        max_polarization_atom2=70.0,
        min_occupancy=0.0,
        max_occupancy=1.0
    ) == {
        'criteria': {
            'open_shell': False,
            'nbo_bonds.atom1_s_character': {'$gte': 10.0, '$lte': 25.0},
            'nbo_bonds.atom1_p_character': {'$gte': 70.0, '$lte': 90.0},
            'nbo_bonds.atom1_d_character': {'$gte': 0.0, '$lte': 5.0},
            'nbo_bonds.atom1_f_character': {'$gte': 0.0, '$lte': 5.0},
            'nbo_bonds.atom2_s_character': {'$gte': 10.0, '$lte': 25.0},
            'nbo_bonds.atom2_p_character': {'$gte': 70.0, '$lte': 90.0},
            'nbo_bonds.atom2_d_character': {'$gte': 0.0, '$lte': 5.0},
            'nbo_bonds.atom2_f_character': {'$gte': 0.0, '$lte': 5.0},
            'nbo_bonds.atom1_polarization': {'$gte': 30.0, '$lte': 70.0},
            'nbo_bonds.atom2_polarization': {'$gte': 30.0, '$lte': 70.0},
            'nbo_bonds.occupancy': {'$gte': 0.0, '$lte': 1.0},
            'nbo_bonds.type_code': 'BD*'
        }
    }

    with ScratchDir("."):
        dumpfn(op, "temp.json")
        new_op = loadfn("temp.json")
        assert new_op.query(
            open_shell=False,
            bond_type="BD*",
            min_s_character_atom1=10.0,
            max_s_character_atom1=25.0,
            min_s_character_atom2=10.0,
            max_s_character_atom2=25.0,
            min_p_character_atom1=70.0,
            max_p_character_atom1=90.0,
            min_p_character_atom2=70.0,
            max_p_character_atom2=90.0,
            min_d_character_atom1=0.0,
            max_d_character_atom1=5.0,
            min_d_character_atom2=0.0,
            max_d_character_atom2=5.0,
            min_f_character_atom1=0.0,
            max_f_character_atom1=5.0,
            min_f_character_atom2=0.0,
            max_f_character_atom2=5.0,
            min_polarization_atom1=30.0,
            max_polarization_atom1=70.0,
            min_polarization_atom2=30.0,
            max_polarization_atom2=70.0,
            min_occupancy=0.0,
            max_occupancy=1.0
        ) == {
            'criteria': {
                'open_shell': False,
                'nbo_bonds.atom1_s_character': {'$gte': 10.0, '$lte': 25.0},
                'nbo_bonds.atom1_p_character': {'$gte': 70.0, '$lte': 90.0},
                'nbo_bonds.atom1_d_character': {'$gte': 0.0, '$lte': 5.0},
                'nbo_bonds.atom1_f_character': {'$gte': 0.0, '$lte': 5.0},
                'nbo_bonds.atom2_s_character': {'$gte': 10.0, '$lte': 25.0},
                'nbo_bonds.atom2_p_character': {'$gte': 70.0, '$lte': 90.0},
                'nbo_bonds.atom2_d_character': {'$gte': 0.0, '$lte': 5.0},
                'nbo_bonds.atom2_f_character': {'$gte': 0.0, '$lte': 5.0},
                'nbo_bonds.atom1_polarization': {'$gte': 30.0, '$lte': 70.0},
                'nbo_bonds.atom2_polarization': {'$gte': 30.0, '$lte': 70.0},
                'nbo_bonds.occupancy': {'$gte': 0.0, '$lte': 1.0},
                'nbo_bonds.type_code': 'BD*'
            }
        }


def test_nbo_interaction_query():
    op = NBOInteractionQuery()
    assert op.query(
        open_shell=True,
        electron_type="alpha",
        donor_type="LP",
        acceptor_type="RY",
        min_perturbation_energy=0.1,
        max_perturbation_energy=3.0,
        min_energy_difference=2.0,
        max_energy_difference=15.0,
        min_fock_element=0.0,
        max_fock_element=10.0
    ) == {
        'criteria': {
            'open_shell': True,
            'alpha_interactions.perturbation_energy': {'$gte': 0.1, '$lte': 3.0},
            'alpha_interactions.energy_difference': {'$gte': 2.0, '$lte': 15.0},
            'alpha_interactions.fock_element': {'$gte': 0.0, '$lte': 10.0},
            'alpha_interactions.donor_type': 'LP',
            'alpha_interactions.acceptor_type': 'RY'
        }
    }

    with ScratchDir("."):
        dumpfn(op, "temp.json")
        new_op = loadfn("temp.json")
        assert new_op.query(
            open_shell=True,
            electron_type="alpha",
            donor_type="LP",
            acceptor_type="RY",
            min_perturbation_energy=0.1,
            max_perturbation_energy=3.0,
            min_energy_difference=2.0,
            max_energy_difference=15.0,
            min_fock_element=0.0,
            max_fock_element=10.0
        ) == {
            'criteria': {
                'open_shell': True,
                'alpha_interactions.perturbation_energy': {'$gte': 0.1, '$lte': 3.0},
                'alpha_interactions.energy_difference': {'$gte': 2.0, '$lte': 15.0},
                'alpha_interactions.fock_element': {'$gte': 0.0, '$lte': 10.0},
                'alpha_interactions.donor_type': 'LP',
                'alpha_interactions.acceptor_type': 'RY'
            }
        }
