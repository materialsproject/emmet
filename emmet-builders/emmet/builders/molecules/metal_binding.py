from datetime import datetime
from itertools import chain
from math import ceil
from typing import Optional, Iterable, Iterator, List, Dict
import copy

from pymatgen.core.structure import Molecule
from pymatgen.util.graph_hashing import weisfeiler_lehman_graph_hash

from maggma.builders import Builder
from maggma.core import Store
from maggma.utils import grouper

from emmet.core.qchem.molecule import MoleculeDoc
from emmet.core.molecules.atomic import PartialChargesDoc, PartialSpinsDoc
from emmet.core.molecules.bonds import MoleculeBondingDoc, metals
from emmet.core.molecules.thermo import MoleculeThermoDoc
from emmet.core.molecules.metal_binding import MetalBindingDoc, METAL_BINDING_METHODS
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
            possible methods for which all required data is available
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
        bonds: Store,
        thermo: Store,
        metal_binding: Store,
        query: Optional[Dict] = None,
        methods: Optional[List] = None,
        settings: Optional[EmmetBuildSettings] = None,
        **kwargs,
    ):
        self.molecules = molecules
        self.charges = charges
        self.spins = spins
        self.bonds = bonds
        self.thermo = thermo
        self.metal_binding = metal_binding
        self.query = query if query else dict()
        self.methods = methods if methods else METAL_BINDING_METHODS
        self.settings = EmmetBuildSettings.autoload(settings)
        self.kwargs = kwargs

        super().__init__(
            sources=[molecules, charges, spins, bonds, thermo],
            targets=[metal_binding],
            **kwargs,
        )
        # Uncomment in case of issue with mrun not connecting automatically to collections
        # for i in [self.molecules, self.charges, self.spins, self.bonds, self.thermo, self.metal_binding]:
        #     try:
        #         i.connect()
        #     except Exception as e:
        #         print("Could not connect,", e)

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
        self.metal_binding.ensure_index("method")

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

        processed_docs = set([e for e in self.metal_binding.distinct("molecule_id")])
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
            # First: do we need to do this? Are there actually metals in this molecule? And species other than metals?
            species = mol.species
            metal_indices = [i for i, e in enumerate(species) if e in metals]
            if len(metal_indices) == 0 or len(species) == 1:
                # print(mol.molecule_id, mol.formula_alphabetical)
                continue

            # Grab the basic documents needed to create a metal binding document
            molecule_id = mol.molecule_id
            solvents = mol.unique_solvents
            charges = [
                PartialChargesDoc(**e)
                for e in self.charges.query({"molecule_id": molecule_id})
            ]
            if mol.spin_multiplicity != 1:
                spins = [
                    PartialSpinsDoc(**e)
                    for e in self.spins.query({"molecule_id": molecule_id})
                ]
            else:
                spins = list()
            bonds = [
                MoleculeBondingDoc(**e)
                for e in self.bonds.query({"molecule_id": molecule_id})
            ]
            thermo = [
                MoleculeThermoDoc(**e)
                for e in self.thermo.query({"molecule_id": molecule_id})
            ]

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
                this_charge = charge_bysolv_meth.get(solvent)  # type: ignore
                this_spin = spins_bysolv_meth.get(solvent)  # type: ignore
                this_bond = bonds_bysolv_meth.get(solvent)  # type: ignore
                base_thermo_doc = thermo_bysolv.get(solvent)  # type: ignore

                # Do we have the requisite docs for this solvent?
                if mol.spin_multiplicity == 1:
                    needed = [this_charge, this_bond, base_thermo_doc]
                else:
                    needed = [this_charge, this_spin, this_bond, base_thermo_doc]

                if any([x is None for x in needed]):
                    continue

                # What method will we use?
                # Currently allows two options:
                # 1. Using NBO for everything ("nbo")
                # 2. Using Mulliken for charges/spins and OpenBabel + metal_edge_extender for bonding
                #   ("mulliken-OB-mee")
                for method in self.methods:
                    plan = False
                    if mol.spin_multiplicity == 1:
                        if method == "nbo" and all(
                            [x.get("nbo") is not None for x in [this_charge, this_bond]]  # type: ignore
                        ):  # type: ignore
                            plan = True
                            charge_doc = this_charge.get("nbo")  # type: ignore
                            spin_doc = None
                            bond_doc = this_bond.get("nbo")  # type: ignore
                        elif method == "mulliken-OB-mee" and (
                            this_charge.get("mulliken") is not None  # type: ignore
                            and this_bond.get("OpenBabelNN + metal_edge_extender") is not None  # type: ignore
                        ):
                            plan = True
                            charge_doc = this_charge.get("mulliken")  # type: ignore
                            spin_doc = None
                            bond_doc = this_bond.get("OpenBabelNN + metal_edge_extender")  # type: ignore
                    else:
                        if method == "nbo" and all(
                            [x.get("nbo") is not None for x in [this_charge, this_spin, this_bond]]  # type: ignore
                        ):  # type: ignore
                            charge_lot = this_charge.get("nbo").level_of_theory  # type: ignore
                            spin_lot = this_spin.get("nbo").level_of_theory  # type: ignore
                            if charge_lot == spin_lot:  # type: ignore
                                plan = True
                                charge_doc = this_charge.get("nbo")  # type: ignore
                                spin_doc = this_spin.get("nbo")  # type: ignore
                                bond_doc = this_bond.get("nbo")  # type: ignore
                        elif (
                            method == "mulliken-OB-mee"
                            and this_charge.get("mulliken") is not None  # type: ignore
                            and this_spin.get("mulliken") is not None  # type: ignore
                            and this_bond.get("OpenBabelNN + metal_edge_extender") is not None  # type: ignore
                        ):
                            charge_lot = this_charge.get("mulliken").level_of_theory  # type: ignore
                            spin_lot = this_spin.get("mulliken").level_of_theory  # type: ignore
                            if charge_lot == spin_lot:  # type: ignore
                                plan = True
                                charge_doc = this_charge.get("mulliken")  # type: ignore
                                spin_doc = this_spin.get("mulliken")  # type: ignore
                                bond_doc = this_bond.get("OpenBabelNN + metal_edge_extender")  # type: ignore

                    # Don't have the right combinations of level of theory and method
                    if plan is False:
                        continue

                    # Obtain relevant thermo documents for each metal atom/ion in the molecule
                    metal_thermo = dict()
                    nometal_thermo = dict()
                    for metal_index in metal_indices:
                        # First, determine the appropriate charge and spin of the metal
                        # TODO: figure out better charge assignment
                        partial_charge = charge_doc.partial_charges[metal_index]  # type: ignore

                        if mol.spin_multiplicity == 1:
                            # For now, just round to nearest whole number
                            charge = round(partial_charge)
                            spin = 1
                        else:
                            partial_spin = spin_doc.partial_spins[metal_index]  # type: ignore
                            charge = round(partial_charge)
                            spin = round(abs(partial_spin)) + 1

                        # Sanity check that charge and spin are compatible
                        metal_species = species[metal_index]
                        try:
                            _ = Molecule(
                                [metal_species],
                                [[0.0, 0.0, 0.0]],
                                charge=charge,
                                spin_multiplicity=spin,
                            )
                        except ValueError:
                            # Assume spin assignment is correct, and change charge accordingly
                            diff_up = abs(partial_charge - (charge + 1))
                            diff_down = abs(partial_charge - (charge - 1))
                            if diff_up < diff_down:
                                charge += 1
                            else:
                                charge -= 1

                        # Grab thermo doc for the relevant metal ion/atom (if available)
                        this_metal_thermo = [
                            MoleculeThermoDoc(**e)
                            for e in self.thermo.query(
                                {
                                    "formula_alphabetical": f"{metal_species}1",
                                    "charge": charge,
                                    "spin_multiplicity": spin,
                                    "lot_solvent": base_thermo_doc.lot_solvent,  # type: ignore
                                }
                            )
                        ]
                        if len(this_metal_thermo) == 0:
                            continue

                        this_metal_thermo = this_metal_thermo[0]
                        metal_thermo[metal_index] = this_metal_thermo

                        # Now the (somewhat) harder part - finding the document for this molecule without the metal
                        # Make sure charges and spins add up
                        nometal_charge = mol.charge - charge
                        nometal_spin = mol.spin_multiplicity - spin + 1
                        mg_copy = copy.deepcopy(bond_doc.molecule_graph)  # type: ignore
                        mg_copy.remove_nodes([metal_index])
                        new_hash = weisfeiler_lehman_graph_hash(
                            mg_copy.graph.to_undirected(), node_attr="specie"
                        )
                        nometal_mol_doc = [
                            MoleculeDoc(**e)
                            for e in self.molecules.query(
                                {
                                    "species_hash": new_hash,
                                    "charge": nometal_charge,
                                    "spin_multiplicity": nometal_spin,
                                }
                            )
                        ]
                        if len(nometal_mol_doc) == 0:
                            continue

                        nometal_mol_id = nometal_mol_doc[0].molecule_id
                        this_nometal_thermo = [
                            MoleculeThermoDoc(**e)
                            for e in self.thermo.query(
                                {
                                    "molecule_id": nometal_mol_id,
                                    "lot_solvent": base_thermo_doc.lot_solvent,  # type: ignore
                                }
                            )
                        ]
                        if len(this_nometal_thermo) == 0:
                            continue

                        this_nometal_thermo = this_nometal_thermo[0]
                        nometal_thermo[metal_index] = this_nometal_thermo

                    doc = MetalBindingDoc.from_docs(
                        method=method,
                        metal_indices=metal_indices,
                        base_molecule_doc=mol,
                        partial_charges=charge_doc,
                        partial_spins=spin_doc,
                        bonding=bond_doc,
                        base_thermo=base_thermo_doc,
                        metal_thermo=metal_thermo,
                        nometal_thermo=nometal_thermo,
                    )

                    if doc is not None and len(doc.binding_data) != 0:
                        binding_docs.append(doc)

        self.logger.debug(
            f"Produced {len(binding_docs)} metal binding docs for {formula}"
        )

        return jsanitize([doc.model_dump() for doc in binding_docs], allow_bson=True)

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
            self.metal_binding.remove_docs(
                {self.metal_binding.key: {"$in": molecule_ids}}
            )
            # Neither molecule_id nor solvent need to be unique, but the combination must be
            self.metal_binding.update(
                docs=docs,
                key=["molecule_id", "solvent", "method"],
            )
        else:
            self.logger.info("No items to update")
