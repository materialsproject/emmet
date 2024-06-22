from emmet.core.classical_md import MoleculeSpec
from emmet.core.base import EmmetBaseModel


class ClassicalMDDoc(EmmetBaseModel):
    molecule_specs: MoleculeSpec

    # should contain more information on all molecules
    # use MoleculeMetadata somewhere
