from pydantic import BaseModel

from emmet.core.mpid import MPID, AlphaID
from emmet.core.types.typing import IdentifierType


def test_identifier_type():

    class TestClass(BaseModel):
        ID: IdentifierType

    tc = TestClass(ID="dogs")

    # ensure that extant MPIDs are deserialized to MPID,
    # and return AlphaID strings on model dump
    assert isinstance(tc.ID, MPID)
    assert tc.model_dump()["ID"].isalpha()
    assert not tc.model_dump()["ID"].isnumeric()

    tc = TestClass(ID=AlphaID._cut_point + 1)
    # ensure that new MPIDs are deserialized to MPID,
    # and return AlphaID strings on model dump
    assert isinstance(tc.ID, AlphaID)
    assert tc.model_dump()["ID"].isalpha()
    assert not tc.model_dump()["ID"].isnumeric()
