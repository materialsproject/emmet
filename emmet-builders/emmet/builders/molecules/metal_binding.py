from collections import defaultdict
from datetime import datetime
from itertools import chain
from math import ceil
from typing import Optional, Iterable, Iterator, List, Dict

from maggma.builders import Builder
from maggma.core import Store
from maggma.utils import grouper

from emmet.core.qchem.molecule import MoleculeDoc, evaluate_lot
from emmet.core.molecules.atomic import PartialChargesDoc, PartialSpinsDoc
from emmet.core.molecules.bonds import MoleculeBondingDoc
from emmet.core.molecules.thermo import MoleculeThermoDoc
from emmet.core.molecules.metal_binding import (
    MetalBindingDoc
)
from emmet.core.utils import jsanitize
from emmet.builders.settings import EmmetBuildSettings


__author__ = "Evan Spotte-Smith"

SETTINGS = EmmetBuildSettings()


class MetalBindingBuilder(Builder):
    """
    The MetalBindingBuilder extracts information about metal binding in molecules
    from MoleculeDocs, MoleculeThermoDocs, MoleculeBondingDocs, PartialChargesDocs,
    and PartialSpinsDocs.

    NBO is the strongly preferred method to approximate partial charges and bonding,
    and so if NBO bonding and partial charges/spins documents are available, they will
    be used.

    If NBO docs are not available, then bonding can be taken from the "OpenBabelNN + metal_edge_extender"
    method, and partial charges and spins can be taken from "mulliken".

    This builder will attempt to build documents for each molecule in each solvent.
    For each molecule-solvent combination, the highest-quality data available
    (based on level of theory, electronic energy, and the method used to generate bonding/charges/spins)
    will be used.

    The process is as follows:
        1. Gather MoleculeDocs by formula
        2. For each molecule, first identify if there are any metals. If not, then no MetalBindingDoc can be made.
            If so, then identify the possible solvents that can be used to generate MetalBindingDocs
        3. For each combination of Molecule ID and solvent, search for additional documents:
            - MoleculeBondingDocs
            - PartialChargesDocs
            - PartialSpinsDocs (for open-shell molecules)
            - MoleculeThermoDocs
        4. Group these additional documents by level of theory and (where applicable) method, and choose the best
            possible level of theory and method for which all required data is available
        5. For each metal in the molecule:
            5.1 Use partial charge and spin information to determine the oxidation and spin state of the metal
            5.2 Search for MoleculeThermoDocs for the metal atom/ion with appropriate charge and spin with the
                chosen level of theory
            5.3 Use graph comparisons (hashing or isomorphism) to identify a molecule with the same structure as
                the molecule of interest WITHOUT the metal of interest, as well as the appropriate charge and spin
            5.4 If an appropriate metal-less molecule can be found, search for a MoleculeThermoDoc for that molecule'
                with the chosen level of theory
        6. Use the obtained bonding, charges, spins, and thermo docs to construct a MetalBindingDoc
    """

    def __init__(
        self,
        molecules: Store,
        charges: Store,
        spins: Store,
        bonding: Store,
        thermo: Store,
        metal_binding: Store,
        query: Optional[Dict] = None,
        settings: Optional[EmmetBuildSettings] = None,
        **kwargs,
    ):

        self.molecules = molecules
        self.charges = charges
        self.spins = spins
        self.bonding = bonding
        self.thermo = thermo
        self.metal_binding = metal_binding
        self.query = query if query else dict()
        self.settings = EmmetBuildSettings.autoload(settings)
        self.kwargs = kwargs

        super().__init__(sources=[molecules, charges, spins, bonding, thermo], targets=[metal_binding])

    def ensure_indexes(self):
        """
        Ensures indices on the collections needed for building
        """

        # Search index for molecules
        self.molecules.ensure_index("molecule_id")
        self.molecules.ensure_index("last_updated")
        self.molecules.ensure_index("task_ids")
        self.molecules.ensure_index("formula_alphabetical")

        # Search index for charges
        self.charges.ensure_index("molecule_id")
        self.charges.ensure_index("task_id")
        self.charges.ensure_index("method")
        self.charges.ensure_index("solvent")
        self.charges.ensure_index("lot_solvent")
        self.charges.ensure_index("property_id")
        self.charges.ensure_index("last_updated")
        self.charges.ensure_index("formula_alphabetical")

        # Search index for spins
        self.spins.ensure_index("molecule_id")
        self.spins.ensure_index("task_id")
        self.spins.ensure_index("method")
        self.spins.ensure_index("solvent")
        self.spins.ensure_index("lot_solvent")
        self.spins.ensure_index("property_id")
        self.spins.ensure_index("last_updated")
        self.spins.ensure_index("formula_alphabetical")

        # Search index for bonds
        self.bonds.ensure_index("molecule_id")
        self.bonds.ensure_index("method")
        self.bonds.ensure_index("task_id")
        self.bonds.ensure_index("solvent")
        self.bonds.ensure_index("lot_solvent")
        self.bonds.ensure_index("property_id")
        self.bonds.ensure_index("last_updated")
        self.bonds.ensure_index("formula_alphabetical")

        # Search index for thermo
        self.thermo.ensure_index("molecule_id")
        self.thermo.ensure_index("task_id")
        self.thermo.ensure_index("solvent")
        self.thermo.ensure_index("lot_solvent")
        self.thermo.ensure_index("property_id")
        self.thermo.ensure_index("last_updated")
        self.thermo.ensure_index("formula_alphabetical")

        # Search index for metal_binding
        self.metal_binding.ensure_index("molecule_id")
        self.metal_binding.ensure_index("solvent")
        self.metal_binding.ensure_index("lot_solvent")
        self.metal_binding.ensure_index("property_id")
        self.metal_binding.ensure_index("last_updated")
        self.metal_binding.ensure_index("formula_alphabetical")

    def prechunk(self, number_splits: int) -> Iterable[Dict]:  # pragma: no cover
        """Prechunk the builder for distributed computation"""

        temp_query = dict(self.query)
        temp_query["deprecated"] = False

        self.logger.info("Finding documents to process")
        all_mols = list(
            self.molecules.query(
                temp_query, [self.molecules.key, "formula_alphabetical"]
            )
        )

        processed_docs = set([e for e in self.metal_binding.distinct("molecule_id")])
        to_process_docs = {d[self.molecules.key] for d in all_mols} - processed_docs
        to_process_forms = {
            d["formula_alphabetical"]
            for d in all_mols
            if d[self.molecules.key] in to_process_docs
        }

        N = ceil(len(to_process_forms) / number_splits)

        for formula_chunk in grouper(to_process_forms, N):
            yield {"query": {"formula_alphabetical": {"$in": list(formula_chunk)}}}

    def get_items(self) -> Iterator[List[Dict]]:
        """
        Gets all items to process into metal_binding documents.

        Returns:
            generator or list relevant molecules to process into documents
        """

        self.logger.info("Metal binding builder started")
        self.logger.info("Setting indexes")
        self.ensure_indexes()

        # Save timestamp to mark buildtime
        self.timestamp = datetime.utcnow()

        # Get all processed molecules
        temp_query = dict(self.query)
        temp_query["deprecated"] = False

        self.logger.info("Finding documents to process")
        all_mols = list(
            self.molecules.query(
                temp_query, [self.molecules.key, "formula_alphabetical"]
            )
        )

        processed_docs = set([e for e in self.charges.distinct("molecule_id")])
        to_process_docs = {d[self.molecules.key] for d in all_mols} - processed_docs
        to_process_forms = {
            d["formula_alphabetical"]
            for d in all_mols
            if d[self.molecules.key] in to_process_docs
        }

        self.logger.info(f"Found {len(to_process_docs)} unprocessed documents")
        self.logger.info(f"Found {len(to_process_forms)} unprocessed formulas")

        # Set total for builder bars to have a total
        self.total = len(to_process_forms)

        for formula in to_process_forms:
            mol_query = dict(temp_query)
            mol_query["formula_alphabetical"] = formula
            molecules = list(self.molecules.query(criteria=mol_query))

            yield molecules

    def process_item(self, items: List[Dict]) -> List[Dict]:
        """
        Process molecule, bonding, partial charges, partial spins, and thermo documents into MetalBindingDocs

        Args:
            tasks List[Dict] : a list of MoleculeDocs in dict form

        Returns:
            [dict] : a list of new metal binding docs
        """

        mols = [MoleculeDoc(**item) for item in items]
        formula = mols[0].formula_alphabetical
        mol_ids = [m.molecule_id for m in mols]
        self.logger.debug(f"Processing {formula} : {mol_ids}")

        binding_docs = list()

        for mol in mols:
            # Grab the basic documents needed to create a metal binding document
            molecule_id = mol.molecule_id
            solvents = mol.unique_solvents
            charges = [PartialChargesDoc(**e) for e in self.charges.query({"molecule_id": molecule_id})]
            if mol.spin_multiplicity != 1:
                spins = [PartialSpinsDoc(**e) for e in self.spins.query({"molecule_id": molecule_id})]
            else:
                spins = list()
            bonds = [MoleculeBondingDoc(**e) for e in self.bonds.query({"molecule_id": molecule_id})]
            thermo = [MoleculeThermoDoc(**e) for e in self.thermo.query({"molecule_id": molecule_id})]

            if any([len(x) == 0 for x in [charges, bonds, thermo]]):
                # Not enough information to construct MetalBindingDoc
                continue
            elif mol.spin_multiplicity != 1 and len(spins) == 0:
                # For open-shell molecule, partial spins information needed
                continue

            # Group by solvent and (where appropriate) method
            charge_bysolv_meth = dict()
            for c in charges:
                if c.solvent not in charge_bysolv_meth:
                    charge_bysolv_meth[c.solvent] = {c.method: c}
                else:
                    charge_bysolv_meth[c.solvent][c.method] = c
            
            spins_bysolv_meth = dict()
            for s in spins:
                if s.solvent not in spins_bysolv_meth:
                    spins_bysolv_meth[s.solvent] = {s.method: s}
                else:
                    spins_bysolv_meth[s.solvent][s.method] = s

            bonds_bysolv_meth = dict()
            for b in bonds:
                if b.solvent not in bonds_bysolv_meth:
                    bonds_bysolv_meth[b.solvent] = {b.method: b}
                else:
                    bonds_bysolv_meth[b.solvent][b.method] = b

            thermo_bysolv = {t.solvent: t for t in thermo}

            for solvent in solvents:
                pass
                # TODO: you are here

        self.logger.debug(f"Produced {len(binding_docs)} metal binding docs for {formula}")

        return jsanitize([doc.dict() for doc in binding_docs], allow_bson=True)

    def update_targets(self, items: List[List[Dict]]):
        """
        Inserts the new documents into the metal_binding collection

        Args:
            items [[dict]]: A list of documents to update
        """

        docs = list(chain.from_iterable(items))  # type: ignore

        # Add timestamp
        for item in docs:
            item.update(
                {
                    "_bt": self.timestamp,
                }
            )

        molecule_ids = list({item["molecule_id"] for item in docs})

        if len(items) > 0:
            self.logger.info(f"Updating {len(docs)} metal binding documents")
            self.metal_binding.remove_docs({self.metal_binding.key: {"$in": molecule_ids}})
            # Neither molecule_id nor method need to be unique, but the combination must be
            self.metal_binding.update(
                docs=docs,
                key=["molecule_id", "solvent"],
            )
        else:
            self.logger.info("No items to update")
