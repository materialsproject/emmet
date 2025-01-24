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


def test_alphaid():
    # test roundtrip, addition, and subtraction
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

        w_prefix = AlphaID(i, prefix="mp")
        assert int(w_prefix) == int(alpha)
        assert w_prefix != alpha
        assert (alpha + w_prefix)._prefix == ""
        assert (w_prefix + alpha)._prefix == "mp"

        w_prefix_and_pad = AlphaID(i, prefix="mvc", padlen=8)
        assert int(w_prefix_and_pad) == int(alpha)
        assert w_prefix_and_pad != alpha
        assert (alpha + w_prefix_and_pad)._prefix == ""
        assert (w_prefix_and_pad + alpha)._prefix == "mvc"
        assert len(alpha + w_prefix_and_pad) >= len(alpha)
