from emmet.core.mpid import (
    MPID,
    MPculeID,
    AlphaID,
    VALID_ALPHA_SEPARATORS,
)
import pytest

import json
from pydantic import BaseModel


def test_mpid():
    assert MPID("mp-3") == MPID("mp-3")
    assert MPID("mp-3") < 3
    assert MPID("mp-3") < MPID("np-3")
    assert MPID("mp-3") > MPID("mp-2")
    assert 3 > MPID("mp-3")
    assert MPID(MPID("mp-1234")) < MPID(1234)
    assert "mp-1234" < MPID(1234)
    assert MPID("1234") > MPID("mp-1234")
    assert MPID("1234") == MPID(1234)
    assert MPID("1234") == "1234"
    assert MPID("mp-12345") > MPID("mp-1234")

    assert min(
        [MPID("mp-44545"), MPID("mp-33"), MPID("mp-2134234"), MPID(33), MPID("33")]
    ) == MPID("mp-33")

    assert (
        len(set([MPID("mp-33"), MPID("mp-44545"), MPID("mp-33"), MPID("mp-2134234")]))
        == 3
    )

    for invalid_value, msg in {
        "-100": "MPID string representation must follow",
        -14: "MPID cannot represent a negative integer.",
    }.items():
        with pytest.raises(ValueError, match=msg):
            MPID(invalid_value)

    MPID(3)
    ulid_mpid = MPID("01HMVV88CCQ6JQ2Y1N8F3ZTVWP-Li")
    assert ulid_mpid.parts == ("01HMVV88CCQ6JQ2Y1N8F3ZTVWP", 0)
    with pytest.raises(ValueError, match="MPID string representation must follow"):
        MPID("GGIRADF")


def test_mpculeid():
    assert MPculeID("b9ba54febc77d2a9177accf4605767db-F6Li1P1-1-2") == MPculeID(
        "b9ba54febc77d2a9177accf4605767db-F6Li1P1-1-2"
    )
    assert (
        MPculeID("b9ba54febc77d2a9177accf4605767db-F6Li1P1-1-2")
        == "b9ba54febc77d2a9177accf4605767db-F6Li1P1-1-2"
    )
    assert MPculeID("b9ba54febc77d2a9177accf4605767db-F6Li1P1-1-2") < MPculeID(
        "b9ba54febc77d2a9177accf4605767db-F6Li1P1-2-1"
    )
    assert MPculeID("b9ba54febc77d2a9177accf4605767db-F6Li1P1-2-1") > MPculeID(
        "b9ba54febc77d2a9177accf4605767db-F6Li1P1-1-2"
    )
    assert MPculeID("mpcule-98bab8f3795eae3fd8e28f5ff2d476e8-C3H8-0-1") < MPculeID(
        "b9ba54febc77d2a9177accf4605767db-F6Li1P1-1-2"
    )


def test_to_str():
    assert str(MPID("mp-149")) == "mp-149"
    assert (
        str(MPculeID("b9ba54febc77d2a9177accf4605767db-F6Li1P1-1-2"))
        == "b9ba54febc77d2a9177accf4605767db-F6Li1P1-1-2"
    )


def test_alpha_id():
    # Test initialization from MPID-like string
    mpid_like_idx = AlphaID("mp-149")
    assert mpid_like_idx == AlphaID(149, prefix="mp", separator="-")
    assert mpid_like_idx._prefix == "mp"
    assert mpid_like_idx._separator == "-"
    assert int(mpid_like_idx) == 149

    assert mpid_like_idx == MPID("mp-149")
    assert mpid_like_idx == AlphaID(MPID("mp-149"))
    assert AlphaID("mvc-160") == MPID("mvc-160")
    assert AlphaID(160) == MPID("160")
    assert mpid_like_idx + MPID("mp-140") == AlphaID("mp-289")
    assert mpid_like_idx - MPID("mp-140") == AlphaID("mp-9")

    # Test relationality - should still compare integers when prefix and separator don't match
    assert mpid_like_idx > MPID("mp-140")
    mvc_idx = AlphaID("mvc-140")
    assert not mpid_like_idx < mvc_idx
    assert mpid_like_idx > mvc_idx

    majik_num = 137

    ref_idx = AlphaID(majik_num, prefix="cats", separator=":")
    assert (
        ref_idx.__repr__()
        == f"AlphaID(cats:{AlphaID._integer_to_alpha_rep(majik_num)})"
    )
    assert ref_idx < AlphaID(
        majik_num + 100, prefix=ref_idx._prefix, separator=ref_idx._separator
    )
    assert ref_idx > AlphaID(
        majik_num - 100, prefix=ref_idx._prefix, separator=ref_idx._separator
    )

    # test padding
    padded_idx = AlphaID(majik_num, prefix="cats", separator=":", padlen=8)
    assert ref_idx == padded_idx
    assert int(ref_idx) == int(padded_idx)
    assert str(padded_idx) == ref_idx._prefix + ref_idx._separator + (
        8 - len(str(ref_idx._identifier))
    ) * "a" + str(ref_idx._identifier)

    # test invalid sep
    for sep in ("^", "&", "%", "$", "#"):
        with pytest.raises(ValueError, match="Invalid separator"):
            AlphaID(majik_num, prefix="v", separator=sep)

    # test copy
    ref_idx_copy = ref_idx.copy()
    ref_idx += 1
    assert ref_idx != ref_idx_copy

    assert AlphaID(majik_num, padlen=10) < AlphaID(majik_num + 1)
    assert AlphaID(majik_num, padlen=10) > AlphaID(majik_num - 1)

    # Test initialization from int

    ordered_seps = list(VALID_ALPHA_SEPARATORS)
    for pfx in (None, "task"):
        for isep, separator in enumerate(ordered_seps):
            idx = AlphaID(majik_num, prefix=pfx, separator=separator)
            assert isinstance(hash(idx), int)

            # Roundtrip
            assert idx == AlphaID(str(idx))

            assert int(idx) == majik_num

            # Test integer equality
            assert idx == majik_num

            # Test in/equality when prefix and separators do not match
            assert idx != AlphaID(majik_num, prefix="unusedprefix")

            # Test equality when separators differ but prefixes are None
            # (separators are unset)
            idx_diff_sep = AlphaID(
                majik_num,
                prefix=pfx,
                separator=ordered_seps[
                    (isep + 1) % len(ordered_seps)
                ],  # ensures separator differs
            )
            if pfx is None:
                assert idx == idx_diff_sep
            else:
                assert idx != idx_diff_sep

            # Test integer addition
            assert idx + 1 == majik_num + 1
            assert idx + 1 == AlphaID(majik_num + 1, prefix=pfx, separator=separator)

            # Test string addition/subtraction
            assert idx + "y" == AlphaID(majik_num + 24, prefix=pfx, separator=separator)
            assert idx - "z" == AlphaID(majik_num - 25, prefix=pfx, separator=separator)

            # Test equality, addition, subtraction of AlphaID
            other_idx = AlphaID("task:100")
            assert other_idx != idx
            if pfx == "task" and separator == ":":
                assert idx - other_idx == majik_num - 100
                assert idx - other_idx == AlphaID(f"task:{majik_num - 100}")

                assert idx + other_idx == majik_num + 100
                assert idx + other_idx == AlphaID(f"task:{majik_num + 100}")
            else:
                match_strs = []
                if pfx != "task":
                    match_strs.append("Prefixes do not match")
                if pfx and separator != ":":
                    match_strs.append("Separators do not match")

                for match_str in match_strs:
                    with pytest.raises(TypeError, match=match_str):
                        idx - other_idx

                    with pytest.raises(TypeError, match=match_str):
                        idx + other_idx

            # Can't add nor compare floats with AlphaID
            with pytest.raises(NotImplementedError, match="Cannot compare AlphaID"):
                idx + 1.0
            with pytest.raises(NotImplementedError, match="Cannot compare AlphaID"):
                idx < float(int(idx))

        # test sorting
        test_ints = (10, 100, 50, 20, 50000)
        test_idxs = [AlphaID(i) for i in test_ints]
        sorted_idxs = sorted(test_idxs)
        assert all(isinstance(_idx, AlphaID) for _idx in sorted_idxs)
        assert [int(v) for v in sorted_idxs] == sorted(test_ints)
        assert max(test_idxs) == AlphaID(max(test_ints))
        assert min(test_idxs) == AlphaID(min(test_ints))

    # test iterative addition / subtraction
    last_val = None
    next_val = None
    for i in range(5000):
        alpha = AlphaID(i)
        assert int(alpha) == i
        if i > 0:
            assert alpha - 1 == last_val
            assert alpha - AlphaID(1) == last_val
            assert alpha == next_val

        last_val = alpha
        next_val = alpha + 1

    # For legacy purposes, ensure that MPIDs with lower values
    # present as int when calling .string
    assert AlphaID("mp-149").string == "mp-149"
    assert AlphaID("mp-3347529").string == "mp-3347529"
    assert AlphaID("mp-3347530").string == str(AlphaID("mp-3347530"))

    for invalid_val, msg in {
        "-100": "Missing prefix and/or identifer.",
        "pfx-": "Missing prefix and/or identifer.",
        ":": "Missing prefix and/or identifer.",
        -100: "AlphaID cannot represent a negative integer.",
    }.items():
        with pytest.raises(ValueError, match=msg):
            AlphaID(invalid_val)

    # Test next safe AlphaID
    # The following words are "obscene" in a
    # non-English language but are safe in English
    # Test works by ensuring that the AlphaID less than
    # a profane word skips the profane word.
    for word in ("pano", "johny", "sega"):
        curr_alpha_id = AlphaID(word)
        prev_alpha_id = curr_alpha_id - 1
        assert prev_alpha_id.next_safe == curr_alpha_id + 1


@pytest.mark.parametrize("id_cls", [MPID, AlphaID])
def test_pydantic(id_cls):
    # test that AlphaID is supported by pydantic de-/serialization

    class TestClass(BaseModel):
        ID: id_cls

    idx = id_cls(101010)
    test_case = TestClass(ID=idx)
    assert test_case.model_dump() == {"ID": idx}
    assert json.loads(test_case.model_dump_json()) == {"ID": str(idx)}

    with pytest.raises(ValueError, match=f"Invalid {id_cls.__name__} Format"):
        TestClass(ID=10.0)
