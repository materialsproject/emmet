import itertools
from operator import attrgetter
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from monty.serialization import loadfn
from pydantic import BaseModel, Field
from pymatgen.analysis.elasticity.elastic import ElasticTensor
from pymatgen.analysis.substrate_analyzer import SubstrateAnalyzer
from pymatgen.core.structure import Structure

from emmet.core.material_property import PropertyDoc
from emmet.core.mpid import MPID


class Substrate(BaseModel):
    name: str
    material_id: MPID
    structure: Structure


DEFAULT_SUBSTRATES = [Substrate(**d) for d in loadfn(Path(__file__).parent.joinpath("structures.json"))]


class SubstrateMatch(BaseModel):
    """A single substrate match"""

    substrate_id: MPID = Field(description="The MPID for the substrate")
    substrate_orientation: Tuple[int, int, int] = Field(description="The miller orientation of the substrate")
    substrate_formula: str = Field(description="The formula of the substrate")
    film_orientation: Tuple[int, int, int] = Field(description="The orientation of the material if grown as a film")
    matching_area: float = Field(
        description="The minimal coinicidence matching area for this film orientation and substrate orientation"
    )
    elastic_energy: float = Field(None, description="The elastic strain energy")
    von_misess_strain: float = Field(None, description="The Von mises strain for the film")

    @classmethod
    def from_structure(
        cls,
        film: Structure,
        substrate: Structure,
        substrate_id: MPID,
        elastic_tensor: Optional[ElasticTensor] = None,
        substrate_analyzer: SubstrateAnalyzer = SubstrateAnalyzer(),
    ):
        # Calculate lowest matches and group by substrate orientation
        matches_by_orient = _groupby_itemkey(
            substrate_analyzer.calculate(
                film=film, substrate=substrate, elasticity_tensor=elastic_tensor, lowest=True,
            ),
            item="match_area",
        )

        # Find the lowest area match for each substrate orientation
        lowest_matches = [min(g, key=lambda x: x.match_area) for _, g in matches_by_orient]

        for match in lowest_matches:
            yield SubstrateMatch(
                substrate_id=substrate_id,
                substrate_orientation=match.substrate_miller,
                substrate_formula=substrate.composition.reduced_formula,
                film_orientation=match.film_miller,
                matching_area=match.match_area,
                elastic_energy=match.elastic_energy,
                strain=match.strain,
            )


class SubstratesDoc(PropertyDoc):
    """Substrate matches computed for the material"""

    property_name = "substrates"

    substrates: List[SubstrateMatch] = Field(description="The list of matches for all given substrates")

    @classmethod
    def from_structure(  # type: ignore[override]
        cls,
        material_id: MPID,
        structure: Structure,
        substrates: Optional[List[Substrate]] = None,
        elastic_tensor: Optional[ElasticTensor] = None,
        **kwargs
    ):
        substrates = substrates or DEFAULT_SUBSTRATES
        all_matches = []
        for substrate in substrates:
            all_matches.extend(
                list(
                    SubstrateMatch.from_structure(
                        film=structure,
                        substrate=substrate.structure,
                        substrate_id=substrate.material_id,
                        elastic_tensor=elastic_tensor,
                    )
                )
            )
        # Sort based on energy if an elastic tensor is present otherwise the area
        if elastic_tensor is not None:
            all_matches = list(sorted(all_matches, key=lambda x: x.elastic_energy))
        else:
            all_matches = list(sorted(all_matches, key=lambda x: x.matching_area))

        return super().from_structure(
            material_id=material_id, meta_structure=structure, substrates=all_matches, **kwargs
        )


def _groupby_itemkey(iterable, item):
    """groupby keyed on (and pre-sorted by) attrgetter(item)."""
    itemkey = attrgetter(item)
    return itertools.groupby(sorted(iterable, key=itemkey), itemkey)
