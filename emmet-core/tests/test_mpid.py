from emmet.core.mpid import MPID, MPculeID, AlphaID
import pytest


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

    # Test relationality - should always be False if prefix / separator don't match
    assert mpid_like_idx > MPID("mp-140")
    mvc_idx = AlphaID("mvc-140")
    assert not mpid_like_idx < mvc_idx
    assert not mpid_like_idx > mvc_idx

    majik_num = 137

    ref_idx = AlphaID(majik_num, prefix="cats", separator="^")
    assert ref_idx < AlphaID(
        majik_num + 100, prefix=ref_idx._prefix, separator=ref_idx._separator
    )
    assert ref_idx > AlphaID(
        majik_num - 100, prefix=ref_idx._prefix, separator=ref_idx._separator
    )

    # Test initialization from int
    for pfx in (
        None,
        "iamaprefix",
    ):
        for separator in ("-", ":", ">"):
            idx = AlphaID(majik_num, prefix=pfx, separator=separator)
            assert int(idx) == majik_num

            # Test integer equality
            assert idx == majik_num

            # Test in/equality when prefix and separators do not match
            assert idx != AlphaID(majik_num, prefix="unusedprefix")

            # Test equality when separators differ but prefixes are None
            # (separators are unset)
            idx_diff_sep = AlphaID(majik_num, prefix=pfx, separator="&")
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
            other_idx = AlphaID(100)
            assert other_idx != idx
            if pfx is None:
                assert idx - other_idx == majik_num - 100
                assert idx - other_idx == AlphaID(majik_num - 100)

                assert idx + other_idx == majik_num + 100
                assert idx + other_idx == AlphaID(majik_num + 100)

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
