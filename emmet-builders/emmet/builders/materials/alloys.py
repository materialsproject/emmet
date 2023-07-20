from itertools import combinations, chain
from typing import Tuple, List, Dict, Union

from tqdm import tqdm
from maggma.builders import Builder
from pymatgen.core.structure import Structure
from matminer.datasets import load_dataset
from emmet.core.thermo import ThermoType

from pymatgen.analysis.alloys.core import (
    AlloyPair,
    InvalidAlloy,
    KNOWN_ANON_FORMULAS,
    AlloyMember,
    AlloySystem,
)

# rough sort of ANON_FORMULAS by "complexity"
ANON_FORMULAS = sorted(KNOWN_ANON_FORMULAS, key=lambda af: len(af))

# Combinatorially, cannot StructureMatch every single possible pair of materials
# Use a loose spacegroup for a pre-screen (in addition to standard spacegroup)
LOOSE_SPACEGROUP_SYMPREC = 0.5

# A source of effective masses, should be replaced with MP-provided effective masses.
BOLTZTRAP_DF = load_dataset("boltztrap_mp")


class AlloyPairBuilder(Builder):
    """
    This builder iterates over anonymous_formula and builds AlloyPair.
    It does not look for members of an AlloyPair.
    """

    def __init__(
        self,
        materials,
        thermo,
        electronic_structure,
        provenance,
        oxi_states,
        alloy_pairs,
        thermo_type: Union[ThermoType, str] = ThermoType.GGA_GGA_U_R2SCAN,
    ):
        self.materials = materials
        self.thermo = thermo
        self.electronic_structure = electronic_structure
        self.provenance = provenance
        self.oxi_states = oxi_states
        self.alloy_pairs = alloy_pairs

        t_type = thermo_type if isinstance(thermo_type, str) else thermo_type.value
        valid_types = {*map(str, ThermoType.__members__.values())}
        if invalid_types := {t_type} - valid_types:
            raise ValueError(
                f"Invalid thermo type(s) passed: {invalid_types}, valid types are: {valid_types}"
            )

        self.thermo_type = t_type

        super().__init__(
            sources=[materials, thermo, electronic_structure, provenance, oxi_states],
            targets=[alloy_pairs],
            chunk_size=8,
        )

    def ensure_indexes(self):
        self.alloy_pairs.ensure_index("pair_id")
        self.alloy_pairs.ensure_index("_search.id")
        self.alloy_pairs.ensure_index("_search.formula")
        self.alloy_pairs.ensure_index("_search.member_ids")
        self.alloy_pairs.ensure_index("alloy_pair.chemsys")

    def get_items(self):
        self.ensure_indexes()

        for idx, af in enumerate(ANON_FORMULAS):
            # if af != "AB":
            #     continue

            thermo_docs = self.thermo.query(
                criteria={
                    "formula_anonymous": af,
                    "deprecated": False,
                    "thermo_type": self.thermo_type,
                },
                properties=[
                    "material_id",
                    "energy_above_hull",
                    "formation_energy_per_atom",
                ],
            )

            thermo_docs = {d["material_id"]: d for d in thermo_docs}

            mpids = list(thermo_docs.keys())

            docs = self.materials.query(
                criteria={
                    "material_id": {"$in": mpids},
                    "deprecated": False,
                },  # , "material_id": {"$in": ["mp-804", "mp-661"]}},
                properties=["structure", "material_id", "symmetry.number"],
            )
            docs = {d["material_id"]: d for d in docs}

            electronic_structure_docs = self.electronic_structure.query(
                {"material_id": {"$in": mpids}},
                properties=["material_id", "band_gap", "is_gap_direct"],
            )
            electronic_structure_docs = {
                d["material_id"]: d for d in electronic_structure_docs
            }

            provenance_docs = self.provenance.query(
                {"material_id": {"$in": mpids}},
                properties=["material_id", "theoretical", "database_IDs"],
            )
            provenance_docs = {d["material_id"]: d for d in provenance_docs}

            oxi_states_docs = self.oxi_states.query(
                {"material_id": {"$in": mpids}, "state": "successful"},
                properties=["material_id", "structure"],
            )
            oxi_states_docs = {d["material_id"]: d for d in oxi_states_docs}

            for material_id in mpids:
                d = docs[material_id]

                d["structure"] = Structure.from_dict(d["structure"])

                if material_id in oxi_states_docs:
                    d["structure_oxi"] = Structure.from_dict(
                        oxi_states_docs[material_id]["structure"]
                    )
                else:
                    d["structure_oxi"] = d["structure"]

                # calculate loose space group
                d["spacegroup_loose"] = d["structure"].get_space_group_info(
                    LOOSE_SPACEGROUP_SYMPREC
                )[1]

                d["properties"] = {}
                # patch in BoltzTraP data if present
                row = BOLTZTRAP_DF.loc[BOLTZTRAP_DF["mpid"] == material_id]
                if len(row) == 1:
                    d["properties"]["m_n"] = float(row.m_n)
                    d["properties"]["m_p"] = float(row.m_p)

                if material_id in electronic_structure_docs:
                    for key in ("band_gap", "is_gap_direct"):
                        d["properties"][key] = electronic_structure_docs[material_id][
                            key
                        ]

                for key in ("energy_above_hull", "formation_energy_per_atom"):
                    d["properties"][key] = thermo_docs[material_id][key]

                if material_id in provenance_docs:
                    for key in ("theoretical",):
                        d["properties"][key] = provenance_docs[material_id][key]

            print(
                f"Starting {af} with {len(docs)} materials, anonymous formula {idx} of {len(ANON_FORMULAS)}"
            )

            yield docs

    def process_item(self, item):
        pairs = []
        for mpids in tqdm(list(combinations(item.keys(), 2))):
            if (
                item[mpids[0]]["symmetry"]["number"]
                == item[mpids[1]]["symmetry"]["number"]
            ) or (
                item[mpids[0]]["spacegroup_loose"] == item[mpids[1]]["spacegroup_loose"]
            ):
                # optionally, could restrict based on band gap too (e.g. at least one end-point semiconducting)
                # if (item[mpids[0]]["band_gap"] > 0) or (item[mpids[1]]["band_gap"] > 0):
                try:
                    pair = AlloyPair.from_structures(
                        structures=[
                            item[mpids[0]]["structure"],
                            item[mpids[1]]["structure"],
                        ],
                        structures_with_oxidation_states=[
                            item[mpids[0]]["structure_oxi"],
                            item[mpids[1]]["structure_oxi"],
                        ],
                        ids=[mpids[0], mpids[1]],
                        properties=[
                            item[mpids[0]]["properties"],
                            item[mpids[1]]["properties"],
                        ],
                    )
                    pairs.append(
                        {
                            "alloy_pair": pair.as_dict(),
                            "_search": pair.search_dict(),
                            "pair_id": pair.pair_id,
                        }
                    )
                except InvalidAlloy:
                    pass
                except Exception as exc:
                    print(exc)

        if pairs:
            print(f"Found {len(pairs)} alloy(s)")

        return pairs

    def update_targets(self, items):
        docs = list(chain.from_iterable(items))
        if docs:
            self.alloy_pairs.update(docs)


class AlloyPairMemberBuilder(Builder):
    """
    This builder iterates over available AlloyPairs by chemical system
    and searches for possible members of those AlloyPairs.
    """

    def __init__(self, alloy_pairs, materials, snls, alloy_pair_members):
        self.alloy_pairs = alloy_pairs
        self.materials = materials
        self.snls = snls
        self.alloy_pair_members = alloy_pair_members

        super().__init__(
            sources=[alloy_pairs, materials, snls], targets=[alloy_pair_members]
        )

    def ensure_indexes(self):
        self.alloy_pairs.ensure_index("pair_id")
        self.alloy_pairs.ensure_index("_search.id")
        self.alloy_pairs.ensure_index("_search.formula")
        self.alloy_pairs.ensure_index("_search.member_ids")
        self.alloy_pairs.ensure_index("alloy_pair.chemsys")
        self.alloy_pairs.ensure_index("alloy_pair.anonymous_formula")

    def get_items(self):
        all_alloy_chemsys = set(self.alloy_pairs.distinct("alloy_pair.chemsys"))
        all_known_chemsys = set(self.materials.distinct("chemsys")) | set(
            self.snls.distinct("chemsys")
        )
        possible_chemsys = all_known_chemsys.intersection(all_alloy_chemsys)

        print(
            f"There are {len(all_alloy_chemsys)} alloy chemical systems of which "
            f"{len(possible_chemsys)} may have members."
        )

        for idx, chemsys in enumerate(possible_chemsys):
            pairs = self.alloy_pairs.query(criteria={"alloy_pair.chemsys": chemsys})
            pairs = [AlloyPair.from_dict(d["alloy_pair"]) for d in pairs]

            mp_docs = self.materials.query(
                criteria={"chemsys": chemsys, "deprecated": False},
                properties=["structure", "material_id"],
            )
            mp_structures = {
                d["material_id"]: Structure.from_dict(d["structure"]) for d in mp_docs
            }

            snl_docs = self.snls.query({"chemsys": chemsys})
            snl_structures = {d["snl_id"]: Structure.from_dict(d) for d in snl_docs}

            structures = mp_structures
            structures.update(snl_structures)

            if structures:
                yield (pairs, structures)

    def process_item(self, item: Tuple[List[AlloyPair], Dict[str, Structure]]):
        pairs, structures = item

        all_pair_members = []
        for pair in pairs:
            pair_members = {"pair_id": pair.pair_id, "members": []}
            for db_id, structure in structures.items():
                try:
                    if pair.is_member(structure):
                        db, _ = db_id.split("-")
                        member = AlloyMember(
                            id_=db_id,
                            db=db,
                            composition=structure.composition,
                            is_ordered=structure.is_ordered,
                            x=pair.get_x(structure.composition),
                        )
                        pair_members["members"].append(member.as_dict())
                except Exception as exc:
                    print(f"Exception for {db_id}: {exc}")
            if pair_members["members"]:
                all_pair_members.append(pair_members)

        return all_pair_members

    def update_targets(self, items):
        docs = list(chain.from_iterable(items))
        if docs:
            self.alloy_pair_members.update(docs)


class AlloySystemBuilder(Builder):
    """
    This builder stitches together the results of
    AlloyPairBuilder and AlloyPairMemberBuilder. The output
    of this collection is the one served by the AlloyPair API.
    It also builds AlloySystem.
    """

    def __init__(
        self, alloy_pairs, alloy_pair_members, alloy_pairs_merged, alloy_systems
    ):
        self.alloy_pairs = alloy_pairs
        self.alloy_pair_members = alloy_pair_members
        self.alloy_pairs_merged = alloy_pairs_merged
        self.alloy_systems = alloy_systems

        super().__init__(
            sources=[alloy_pairs, alloy_pair_members],
            targets=[alloy_pairs_merged, alloy_systems],
            chunk_size=8,
        )

    def get_items(self):
        for idx, af in enumerate(ANON_FORMULAS):
            # comment out to only calculate a single anonymous formula for debugging
            # if af != "AB":
            #     continue

            docs = list(self.alloy_pairs.query({"alloy_pair.anonymous_formula": af}))
            pair_ids = [d["pair_id"] for d in docs]
            members = {
                d["pair_id"]: d
                for d in self.alloy_pair_members.query({"pair_id": {"$in": pair_ids}})
            }

            if docs:
                yield docs, members

    def process_item(self, item):
        pair_docs, members = item

        for doc in pair_docs:
            if doc["pair_id"] in members:
                doc["alloy_pair"]["members"] = members[doc["pair_id"]]["members"]
                doc["_search"]["member_ids"] = [
                    m["id_"] for m in members[doc["pair_id"]]["members"]
                ]
            else:
                doc["alloy_pair"]["members"] = []
                doc["_search"]["member_ids"] = []

        pairs = [AlloyPair.from_dict(d["alloy_pair"]) for d in pair_docs]
        systems = AlloySystem.systems_from_pairs(pairs)

        system_docs = [
            {
                "alloy_system": system.as_dict(),
                "alloy_id": system.alloy_id,
                "_search": {"member_ids": [m.id_ for m in system.members]},
            }
            for system in systems
        ]

        for system_doc in system_docs:
            # Too big to store, will need to reconstruct separately from pair_ids
            system_doc["alloy_system"]["alloy_pairs"] = None

        return pair_docs, system_docs

    def update_targets(self, items):
        pair_docs, system_docs = [p for p, s in items], [s for p, s in items]

        pair_docs = list(chain.from_iterable(pair_docs))
        if pair_docs:
            self.alloy_pairs_merged._collection.insert_many(pair_docs)

        system_docs = list(chain.from_iterable(system_docs))
        if system_docs:
            self.alloy_systems._collection.insert_many(system_docs)
