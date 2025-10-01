"""Test extended MPID / AlphaID formats."""

from itertools import product
import numpy as np
from pymatgen.core import Element

from emmet.core.mpid import MPID, AlphaID
from emmet.core.mpid_ext import BatteryID, ThermoID, XasSpectrumID, validate_identifier
from emmet.core.types.enums import ThermoType, XasEdge, XasType


def random_identifiers(num_idx: int = 10) -> set[str | MPID | AlphaID]:
    randints = set()
    c = 0
    while len(randints) < num_idx:
        # ensure mix of IDs which are MPID and AlphaID
        if c % 2 == 0:
            low = 1
            high = AlphaID._cut_point
        else:
            low = AlphaID._cut_point
            high = 1_000_000_000
        randints.add(np.random.randint(low=low, high=high))
        c += 1

    idxs = set()
    for idx in randints:
        idxs.update({f"mp-{idx}", MPID(f"mvc-{idx}"), AlphaID(idx)})
    return idxs


RAND_IDS = random_identifiers()


def test_validate_on_mpid_alpha():

    for idx in RAND_IDS:
        assert validate_identifier(idx, serialize=False) == AlphaID(idx).formatted
        assert validate_identifier(idx, serialize=True) == str(AlphaID(idx))


def test_single_suffix_ids():

    last_iden = None
    for id_cls, enum_cls in {BatteryID: Element, ThermoID: ThermoType}.items():

        for idx, enum_val in product(RAND_IDS, enum_cls.__members__):
            iden = id_cls(identifier=idx, suffix=enum_val)
            assert iden == id_cls.from_str(f"{idx}_{enum_val}")
            if last_iden:
                assert iden != last_iden
            last_iden = iden


def test_many_suffix_id():

    last_iden = None
    for prod in product(
        RAND_IDS, XasType.__members__, Element.__members__, XasEdge.__members__
    ):
        idx, xas_type, ele, xas_edge = prod
        iden = XasSpectrumID(identifier=idx, suffix=(xas_type, ele, xas_edge))
        assert iden == XasSpectrumID.from_str("-".join(prod))
        if last_iden:
            assert iden != last_iden
        last_iden = iden
