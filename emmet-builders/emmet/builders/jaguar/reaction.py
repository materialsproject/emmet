from datetime import datetime
from itertools import chain, groupby
from math import ceil
from typing import Dict, Iterable, Iterator, List, Optional, Tuple

import numpy as np

from pymatgen.core.structure import Molecule

from maggma.builders import Builder
from maggma.stores import Store
from maggma.utils import grouper

from emmet.builders.settings import EmmetBuildSettings
from emmet.core.utils import jsanitize
from emmet.core.jaguar.calc_types import LevelOfTheory
from emmet.core.jaguar.pes import (
    PESMinimumDoc,
    TransitionStateDoc,
)
from emmet.core.jaguar.reactions import ReactionDoc


__author__ = "Evan Spotte-Smith <ewcspottesmith@lbl.gov>"


SETTINGS = EmmetBuildSettings()


def group_reactions(reactions: List[ReactionDoc], consider_metal_bonds: bool = False):
    """
    Collect reactions based on their charges, spin multiplicities, endpoint
    connectivities, and bonds broken/formed

    :param reactions: list of ReactionDocs to be grouped
    :param consider_metal_bonds: Should metal bonds be considered when
        determining if two reactions are the same?
    :return: lists of grouped ReactionDocs
    """

    def charge_spin(doc):
        return (doc.charge, doc.spin_multiplicity)

    for c_s, pregroup in groupby(sorted(reactions, key=charge_spin), key=charge_spin):
        groups = list()  # type: ignore

        for doc in pregroup:
            match = False
            for group in groups:
                rep = group[0]
                if consider_metal_bonds:
                    if doc.reactant_molecule_graph.isomorphic_to(
                        rep.reactant_molecule_graph
                    ) and doc.product_molecule_graph.isomorphic_to(
                        rep.product_molecule_graph
                    ):
                        if (
                            doc.bond_types_broken == rep.bond_types_broken
                            and doc.bond_types_formed == rep.bond_types_formed
                        ):
                            group.append(doc)
                            match = True
                            break

                    elif doc.reactant_molecule_graph.isomorphic_to(
                        rep.product_molecule_graph
                    ) and doc.product_molecule_graph.isomorphic_to(
                        rep.reactant_molecule_graph
                    ):
                        if (
                            doc.bond_types_broken == rep.bond_types_formed
                            and doc.bond_types_formed == rep.bond_types_broken
                        ):
                            group.append(doc)
                            match = True
                            break

                else:
                    if doc.reactant_molecule_graph_nometal.isomorphic_to(
                        rep.reactant_molecule_graph_nometal
                    ) and doc.product_molecule_graph_nometal.isomorphic_to(
                        rep.product_molecule_graph_nometal
                    ):
                        if (
                            doc.bond_types_broken_nometal
                            == rep.bond_types_broken_nometal
                            and doc.bond_types_formed_nometal
                            == rep.bond_types_formed_nometal
                        ):
                            group.append(doc)
                            match = True
                            break
                    elif doc.reactant_molecule_graph_nometal.isomorphic_to(
                        rep.product_molecule_graph_nometal
                    ) and doc.product_molecule_graph_nometal.isomorphic_to(
                        rep.reactant_molecule_graph_nometal
                    ):
                        if (
                            doc.bond_types_broken_nometal
                            == rep.bond_types_formed_nometal
                            and doc.bond_types_formed_nometal
                            == rep.bond_types_broken_nometal
                        ):
                            group.append(doc)
                            match = True
                            break

            if not match:
                groups.append([doc])

        for group in groups:
            yield group


class ReactionAssociationBuilder(Builder):
    """
    The ReactionAssociationBuilder connects transition-states (TS) with their
    corresponding reaction endpoints (reactants and products). It also
    calculates the properties of the corresponding reaction, including reaction
    thermodynamics and bond changes.

    The process is as follows:

        1.) Separate transition-states by overall formula
        2.) Search minima for documents with
            - The same formula
            - The same charge
            - The same spin multiplicity (conical intersections between different
            PES are not currently considered)
            - A geometry optimized at same level of theory as the TS...
                - where the initial structure of that geometry optimization lies
                    along the reaction coordinate of the transition-state
        3.) If there are multiple viable minima for the same endpoint (reactant
            or product), take the lowest-energy document
        4.) Combine TS and minima to form ReactionDoc

    Note that this builder will not perform any filtering - in particular, if
    given calculations representing essentially the same reaction (but perhaps
    with the TS or the product in a different conformation), it will produce
    multiple different ReactionDocs. Reducing redundant reactions is the job
    of the ReactionBuilder.

    Also note that, at present, this builder cannot handle cases where one of
    the endpoints failed to optimize because various reactants or products
    moved away to infinite separation. Accounting for such cases is a goal for a
    future version of this code.
    """

    def __init__(
        self,
        transition_states: Store,
        minima: Store,
        assoc: Store,
        query: Optional[Dict] = None,
        settings: Optional[EmmetBuildSettings] = None,
        **kwargs,
    ):
        """
        Args:
            transition_states:  Store of TransitionStateDocs
            minima: Store of PESMinimumDocs
            assoc: Store to be populated with ReactionDocs
            query: dictionary to limit PES points to be analyzed
            settings: EmmetSettings to use in the build process
        """

        self.transition_states = transition_states
        self.minima = minima
        self.assoc = assoc
        self.query = query if query else dict()
        self.settings = EmmetBuildSettings.autoload(settings)
        self.kwargs = kwargs

        super().__init__(sources=[transition_states, minima], targets=[assoc])

    def ensure_indexes(self):
        """
        Ensures indices on the collections needed for building
        """

        # Search index for minima
        self.minima.ensure_index("molecule_id")
        self.minima.ensure_index("last_updated")
        self.minima.ensure_index("task_ids")
        self.minima.ensure_index("formula_alphabetical")

        # Search index for transition-states
        self.transition_states.ensure_index("molecule_id")
        self.transition_states.ensure_index("last_updated")
        self.transition_states.ensure_index("task_ids")
        self.transition_states.ensure_index("formula_alphabetical")

        # Search index for reactions
        self.assoc.ensure_index("reaction_id")
        self.assoc.ensure_index("transition_state_id")
        self.assoc.ensure_index("reactant_id")
        self.assoc.ensure_index("product_id")
        self.assoc.ensure_index("formla_alphabetical")

    def prechunk(self, number_splits: int) -> Iterable[Dict]:  # pragma: no cover
        """Prechunk the ReactionAssociationBuilder for distributed computation"""

        temp_query = dict(self.query)
        temp_query["success"] = True

        self.logger.info("Finding transition-states to process")
        all_ts = list(
            self.transition_states.query(
                temp_query, [self.transition_states.key, "formula_alphabetical"]
            )
        )

        processed_ts = set(self.assoc.distinct("transition_state_id"))
        to_process_ts = {d[self.transition_states.key] for d in all_ts} - processed_ts
        to_process_forms = {
            d["formula_alphabetical"]
            for d in all_ts
            if d[self.transition_states.key] in to_process_ts
        }

        N = ceil(len(to_process_forms) / number_splits)

        for formula_chunk in grouper(to_process_forms, N):
            yield {"query": {"formula_alphabetical": {"$in": list(formula_chunk)}}}

    def get_items(self) -> Iterator[List[Dict]]:
        """
        Gets all transition-states to process into ReactionDocs.

        Returns:
            generator or list relevant transition-states to process into documents
        """

        self.logger.info("Reaction Association Builder started")

        self.logger.info("Setting indexes")
        self.ensure_indexes()

        # Save timestamp to mark buildtime
        self.timestamp = datetime.utcnow()

        # Get all processed transition-states
        temp_query = dict(self.query)
        temp_query["deprecated"] = False

        self.logger.info("Finding transition-states to process")
        all_ts = list(
            self.transition_states.query(
                temp_query, [self.transition_states.key, "formula_alphabetical"]
            )
        )

        processed_ts = set(self.assoc.distinct("transition_state_id"))
        to_process_ts = {d[self.transition_states.key] for d in all_ts} - processed_ts
        to_process_forms = {
            d["formula_alphabetical"]
            for d in all_ts
            if d[self.transition_states.key] in to_process_ts
        }

        self.logger.info(f"Found {len(to_process_ts)} unprocessed transition-states")
        self.logger.info(f"Found {len(to_process_forms)} unprocessed formulas")

        # Set total for builder bars to have a total
        self.total = len(to_process_forms)

        for formula in to_process_forms:
            ts_query = dict(temp_query)
            ts_query["formula_alphabetical"] = formula
            tss = list(self.transition_states.query(criteria=ts_query))

            # TODO: Do I need to do validation?
            # Presumably if these TS have already been turned into documents
            # using another builder, they should be fine?

            yield tss

    def identify_endpoints(
        self, ts: TransitionStateDoc
    ) -> Optional[Tuple[PESMinimumDoc, PESMinimumDoc]]:
        """
        Identify the minima associated with a TS.

        :param ts: TransitionStateDoc
        :return: Tuple (PESMinimumDoc, PESMinimumDoc), representing the two
            endpoints of the reaction associated with ts.
            If one or both endpoints cannot be found, returns None
        """

        # We use this molecule, rather than simply ts.molecule, to ensure that
        # the structure is EXACTLY the one that would be perturbed to optimize
        # to the endpoints

        ts_mol = Molecule.from_dict(ts.freq_entry["output"]["molecule"])  # type: ignore
        ts_mol_coords = ts_mol.cart_coords
        transition_mode = ts.vibrational_frequency_modes[0]
        transition_array = np.array(transition_mode)
        transition_mode_normalized = (
            transition_array / transition_array.sum(axis=1)[:, np.newaxis]
        )
        ts_freq_lot = ts.freq_entry["level_of_theory"]

        possible_minima = list(
            self.minima.query(
                {
                    "formula_alphabetical": ts.formula_alphabetical,
                    "charge": ts.charge,
                    "spin_multiplicity": ts.spin_multiplicity,
                    "deprecated": False
                }
            )
        )
        poss_min_docs = [PESMinimumDoc(**d) for d in possible_minima]

        reverse_minima = list()
        forward_minima = list()

        for poss_min in poss_min_docs:
            # Level of theory for optimization must match level of theory for
            # TS frequency calculation
            if poss_min.best_entries is None:
                continue

            if ts_freq_lot in poss_min.best_entries.keys():
                poss_opt_entry = poss_min.best_entries[ts_freq_lot]
            elif LevelOfTheory(ts_freq_lot) in poss_min.best_entries.keys():
                ts_freq_lot = LevelOfTheory(ts_freq_lot)
                poss_opt_entry = poss_min.best_entries[ts_freq_lot]
            else:
                continue

            initial_mol = poss_opt_entry["input"].get("molecule")
            final_mol = poss_opt_entry["output"].get("molecule")
            # Should never be the case, but for safety...
            if initial_mol is None or final_mol is None:
                continue

            if not isinstance(initial_mol, Molecule):
                initial_mol = Molecule.from_dict(initial_mol)
            if not isinstance(final_mol, Molecule):
                final_mol = Molecule.from_dict(final_mol)

            # Endpoint is the same as TS
            if np.allclose(final_mol.cart_coords, ts_mol_coords):
                continue

            init_mol_coords = initial_mol.cart_coords
            diff = init_mol_coords - ts_mol_coords
            diff_norm = diff / diff.sum(axis=1)[:, np.newaxis]

            if np.allclose(diff_norm, transition_mode_normalized):
                if np.sum(diff) < 0:
                    reverse_minima.append(poss_min)
                else:
                    forward_minima.append(poss_min)

        # One or both endpoints could not be found
        if len(reverse_minima) == 0 or len(forward_minima) == 0:
            return None

        return (
            sorted(reverse_minima, key=lambda x: x.best_entries[ts_freq_lot]["energy"])[
                0
            ],
            sorted(forward_minima, key=lambda x: x.best_entries[ts_freq_lot]["energy"])[
                0
            ],
        )

    def process_item(self, items: List[Dict]) -> List[Dict]:
        """
        Process the into a ReactionDoc

        Args:
            tasks [dict] : a list of TransitionStateDocs

        Returns:
            [dict] : a list of new ReactionDocs
        """

        tss = [TransitionStateDoc(**item) for item in items]
        formula = tss[0].formula_alphabetical
        ids = [ts.molecule_id for ts in tss]

        self.logger.debug(f"Processing {formula} : {ids}")
        reactions = list()

        for ts in tss:
            endpoints = self.identify_endpoints(ts)
            if endpoints is None:
                self.logger.warn(
                    f"Failed making ReactionDoc for {ts.molecule_id} "
                    f"because endpoints could not be found."
                )
                continue
            doc = ReactionDoc.from_docs(endpoints[0], endpoints[1], ts)
            reactions.append(doc)

        self.logger.debug(f"Produced {len(reactions)} reactions for {formula}")

        return jsanitize([doc.dict() for doc in reactions], allow_bson=True)

    def update_targets(self, items: List[Dict]):
        """
        Inserts the new reactions into the reactions collection

        Args:
            items [dict]: A list of ReactionDocs to update
        """

        docs = list(chain.from_iterable(items))  # type: ignore

        for item in docs:
            item.update({"_bt": self.timestamp})

        rxn_ids = list({item["reaction_id"] for item in docs})

        if len(docs) > 0:
            self.logger.info(f"Updating {len(docs)} reactions")
            self.assoc.remove_docs({self.assoc.key: {"$in": rxn_ids}})
            self.assoc.update(
                docs=docs,
                key=["reaction_id"],
            )
        else:
            self.logger.info("No items to update")


class ReactionBuilder(Builder):
    """
    The ReactionBuilder collects ReactionDocs that describe the same reaction,
    meaning that the endpoints (reactants and products) have the same connectivity,
    and the same types of bonds break and form. This account for the fact that
    different transition-states may be found at multiple conformations, leading
    to slightly different endpoints.

    When determining the properties of the overall ReactionDoc, the reaction
    with the lowest electronic energy barrier dE_barrier is preferred.

    The process is as follows:

        1.) Separate ReactionDocs by overall formula, charge, and then spin
            multiplicity
        2.) Group reactions based on the connectivity of the endpoints and
            the bonds broken/formed (in both directions)
        3.) Insert the combined ReactionDocs into the reactions collection
    """

    def __init__(
        self,
        assoc: Store,
        reactions: Store,
        query: Optional[Dict] = None,
        consider_metal_bonds: bool = False,
        settings: Optional[EmmetBuildSettings] = None,
        **kwargs,
    ):
        """
        Args:
            assoc: Store of associated ReactionDocs
            reactions: Store of reactions to be populated
            query: dictionary to limit reactions to be analyzed
            consider_metal_bonds: when determining if two reactions are the
                same, should metal bonding be taken into account?
            settings: EmmetSettings to use in the build process
        """

        self.assoc = assoc
        self.reactions = reactions
        self.query = query if query else dict()
        self.consider_metal_bonding = consider_metal_bonds
        self.settings = EmmetBuildSettings.autoload(settings)
        self.kwargs = kwargs

        super().__init__(sources=[assoc], targets=[reactions])

    def ensure_indexes(self):
        """
        Ensures indices on the collections needed for building
        """

        # Search index for reactions
        self.assoc.ensure_index("reaction_id")
        self.assoc.ensure_index("transition_state_id")
        self.assoc.ensure_index("reactant_id")
        self.assoc.ensure_index("product_id")
        self.assoc.ensure_index("formla_alphabetical")

        # Search index for reactions
        self.reactions.ensure_index("reaction_id")
        self.reactions.ensure_index("transition_state_id")
        self.reactions.ensure_index("reactant_id")
        self.reactions.ensure_index("product_id")
        self.reactions.ensure_index("formla_alphabetical")

    def prechunk(self, number_splits: int) -> Iterable[Dict]:  # pragma: no cover
        """Prechunk the ReactionBuilder for distributed computation"""

        temp_query = dict(self.query)
        temp_query["deprecated"] = False

        self.logger.info("Finding reactions to process")
        all_rxns = list(
            self.assoc.query(temp_query, [self.assoc.key, "formula_alphabetical"])
        )

        processed_rxns = set(self.reactions.distinct("reaction_id"))
        to_process_rxns = {d[self.assoc.key] for d in all_rxns} - processed_rxns
        to_process_forms = {
            d["formula_alphabetical"]
            for d in all_rxns
            if d[self.assoc.key] in to_process_rxns
        }

        N = ceil(len(to_process_forms) / number_splits)

        for formula_chunk in grouper(to_process_forms, N):
            yield {"query": {"formula_alphabetical": {"$in": list(formula_chunk)}}}

    def get_items(self) -> Iterator[List[Dict]]:
        """
        Gets all reactions to process.

        Returns:
            generator or list relevant reactions to process into new ReactionDocs
        """

        self.logger.info("Reaction Builder started")

        self.logger.info("Setting indexes")
        self.ensure_indexes()

        # Save timestamp to mark buildtime
        self.timestamp = datetime.utcnow()

        # Get all processed reactions
        temp_query = dict(self.query)
        temp_query["deprecated"] = False

        self.logger.info("Finding reactions to process")
        all_rxns = list(
            self.assoc.query(temp_query, [self.assoc.key, "formula_alphabetical"])
        )

        processed_rxns = set(self.reactions.distinct("reaction_id"))
        to_process_rxns = {d[self.assoc.key] for d in all_rxns} - processed_rxns
        to_process_forms = {
            d["formula_alphabetical"]
            for d in all_rxns
            if d[self.assoc.key] in to_process_rxns
        }

        self.logger.info(f"Found {len(to_process_rxns)} unprocessed reactions")
        self.logger.info(f"Found {len(to_process_forms)} unprocessed formulas")

        # Set total for builder bars to have a total
        self.total = len(to_process_forms)

        for formula in to_process_forms:
            rxn_query = dict(temp_query)
            rxn_query["formula_alphabetical"] = formula
            rxns = list(self.assoc.query(criteria=rxn_query))

            # TODO: Do I need to do validation?
            # Presumably if these TS have already been turned into documents
            # using another builder, they should be fine?

            yield rxns

    def process_item(self, items: List[Dict]) -> List[Dict]:
        """
        Process reactions and compile them into ReactionDocs

        Args:
            tasks [dict] : a list of ReactionDocs

        Returns:
            [dict] : a list of new ReactionDocs
        """

        rxns = [ReactionDoc(**item) for item in items]
        formula = rxns[0].formula_alphabetical
        ids = [rxn.reaction_id for rxn in rxns]

        self.logger.debug(f"Processing {formula} : {ids}")
        new_reactions = list()

        for group in group_reactions(rxns, self.consider_metal_bonding):
            # Maybe somehow none get grouped?
            if len(group) == 0:
                continue

            sorted_docs = sorted(group, key=lambda x: x.dE_barrier)

            best_doc = sorted_docs[0]
            if len(sorted_docs) > 1:
                best_doc.similar_reactions = [r.reaction_id for r in sorted_docs[1:]]

            new_reactions.append(best_doc)

        self.logger.debug(f"Produced {len(new_reactions)} reactions for {formula}")

        return jsanitize([doc.dict() for doc in new_reactions], allow_bson=True)

    def update_targets(self, items: List[Dict]):
        """
        Inserts the new reactions into the reactions collection

        Args:
            items [dict]: A list of ReactionDocs to update
        """

        docs = list(chain.from_iterable(items))  # type: ignore

        for item in docs:
            item.update({"_bt": self.timestamp})

        rxn_ids = list({item["reaction_id"] for item in docs})

        if len(docs) > 0:
            self.logger.info(f"Updating {len(docs)} reactions")
            self.reactions.remove_docs({self.reactions.key: {"$in": rxn_ids}})
            self.reactions.update(
                docs=docs,
                key=["reaction_id"],
            )
        else:
            self.logger.info("No items to update")
