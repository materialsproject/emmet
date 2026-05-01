from emmet.api.utils import process_identifiers


def test_process_ids():
    for test_data, ref_data, use_prefix in [
        ("mp-13, mp-149,77", ["mp-aaaaaaan", "mp-aaaaaaft", "mp-aaaaaacz"], True),
        ("1000000000", ["adgehtym"], False),
        ("1000000000,abcdefg", ["mp-adgehtym", "mp-aabcdefg"], True),
    ]:
        assert process_identifiers(test_data, use_prefix=use_prefix) == ref_data
