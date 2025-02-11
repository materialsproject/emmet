__version__ = "dev3"
__author__ = "Alex Nguyen - dknguyenngoc@lbl.gov"
from maggma.stores import MongoStore
from maggma.builders import MapBuilder
from pymatgen.core.structure import Structure
from pymatgen.core.periodic_table import Element
from pymatgen.analysis.diffusion.neb.full_path_mapper import MigrationGraph
from pymatgen.analysis.chemenv.coordination_environments.coordination_geometry_finder import (
    LocalGeometryFinder,
)
from pymatgen.analysis.chemenv.coordination_environments.coordination_geometries import *
from pymatgen.analysis.chemenv.coordination_environments.structure_environments import (
    LightStructureEnvironments,
)
from pymatgen.analysis.chemenv.connectivity import (
    structure_connectivity,
    connectivity_finder,
)
from pymatgen.analysis.chemenv.coordination_environments import (
    chemenv_strategies,
    structure_environments,
)
import networkx as nx
import numpy as np
from collections import deque
from itertools import combinations
from pymatgen.analysis.chemenv.utils.defs_utils import AdditionalConditions


class OverlapScreeningBuilder(MapBuilder):
    """
    Look for periodic paths with the overlapping polyhedra motif. Polyhedra are identified with ChemEnv LocalGeometryFinder.
    
    Args:
    migration_graph_store (Store): store of migration graphs docs (output of migration graph builder)
    electrode_store (Store): store of electrode docs - for information on voltage, stability, etc.,
    target_store (Store): store for overlap results,
    specie (str): specie of interest
    coordination ([int]): coordination number for the wi sites
    overlap ([int]): degrees of overlap to look for between wi polyhedral sites
    distance_cutoff (float): distance between polyhedra, cutoff to determine
        structure connectivity
    """

    def __init__(
        self,
        migration_graph_store: MongoStore,
        electrode_store: MongoStore,
        target_store: MongoStore,
        specie: str,
        cn: [int],
        overlap_cn: [int],
        distance_cutoff: float = 2,
        csm_cutoff: float = 8.0,
        query: dict = None,
    ):
        self.migration_graph_store = migration_graph_store
        self.electrode_store = electrode_store
        self.target_store = target_store
        self.query = query
        self.specie = specie
        self.cn = cn
        self.overlap_cn = overlap_cn
        self.distance_cutoff = distance_cutoff
        self.csm = csm_cutoff

        super().__init__(source=electrode_store, target=target_store, query=query)
        self.connect()
        migration_graph_store.connect()

    def intersect_sites(self, sites1, sites2, edge_data):
        intersect = []
        for site1 in sites1:
            coords1 = site1.frac_coords + edge_data
            for site2 in sites2:
                coords2 = site2.frac_coords + edge_data
                if site1.specie != site2.specie: continue
                if all(np.isclose(site1.frac_coords, site2.frac_coords)):
                    intersect.append(site1.frac_coords)
                    continue
                elif all(np.isclose(site1.frac_coords, coords2)):
                    intersect.append(coords2)
                    continue
                elif all(np.isclose(coords1, site2.frac_coords)):
                    intersect.append(coords1)
        intersect_set = []
        for coord in intersect:
            if any(
                [all(np.isclose(coord, unique_cord)) for unique_cord in intersect_set]
            ):
                continue
            intersect_set.append(coord)
        return intersect_set

    def get_cycle_basis(self, graph):
        cycles = []
        graph_cp = graph.copy()
        for comp in nx.connected_components(graph):
            temp_cycles = []
            root = list(comp)[0]
            T = {i: i for i in graph.nodes}
            tree = nx.DiGraph()
            tree.add_nodes_from(graph.nodes)
            Q = deque()
            Q.append(root)
            while Q:
                v = Q.popleft()
                for u in graph.nodes:
                    if u == root or not graph_cp.has_edge(u, v):
                        continue
                    if T[u] != u:
                        pu = nx.shortest_path(tree, root, u)
                        pv = nx.shortest_path(tree, root, v)
                        pu_edges = [
                            graph.get_edge_data(pu[i], pu[i + 1])
                            for i in range(len(pu) - 1)
                        ]
                        pv_edges = [
                            graph.get_edge_data(pv[i], pv[i + 1])
                            for i in range(len(pv) - 1)
                        ]
                        d = pu_edges + pv_edges + [graph.get_edge_data(u, v)]
                        temp_cycles.append(
                            [i for n, i in enumerate(d) if i not in d[n + 1 :]]
                        )
                    else:
                        Q.append(u)
                        T[u] = v
                        tree.add_edge(v, u)
                    graph_cp.remove_edge(u, v)

            for n in range(1, len(temp_cycles) + 1):
                for combo in combinations(temp_cycles, n):
                    d = [j for i in combo for j in i]
                    cycles.append([i for n, i in enumerate(d) if i not in d[n + 1 :]])

        return cycles

    def overlap_find(self, mg):
        try:
            if mg is None:
                return
            struct = Structure.from_dict(mg["structure"])
            lgf = LocalGeometryFinder()
            lgf.setup_structure(struct)
            se = lgf.compute_structure_environments(
                maximum_distance_factor=self.distance_cutoff,
                only_atoms=[self.specie],  # must identify specie interested in
                max_cn=max(self.cn),
                min_cn=min(self.cn),
                minimum_angle_factor=0.05,
            )
            strategy = chemenv_strategies.MultiWeightsChemenvStrategy(
                structure_environments=se,
                dist_ang_area_weight=chemenv_strategies.DistanceAngleAreaNbSetWeight(
                    surface_definition={
                        "type": "standard_elliptic",
                        "distance_bounds": {"lower": 1.2, "upper": 1.8},
                        "angle_bounds": {"lower": 0.1, "upper": 0.8},
                    }
                ),
                self_csm_weight=chemenv_strategies.SelfCSMNbSetWeight(
                    effective_csm_estimator={'function': 'power2_inverse_decreasing', 'options': {'max_csm': self.csm}},
                    weight_estimator={'function': 'power2_decreasing_exp', 'options': {'max_csm': self.csm, 'alpha': 1.0}},
                    symmetry_measure_type='csm_wcs_ctwcc',
                ),
                ce_estimator={'function': 'power2_inverse_power2_decreasing', 'options': {'max_csm': self.csm}},
                additional_condition=AdditionalConditions.NO_AC,
            )
            lse = LightStructureEnvironments.from_structure_environments(
                strategy=strategy, structure_environments=se
            )
            struct_graph = MigrationGraph.from_dict(mg).m_graph
            sites_from_mg = struct_graph.structure.sites
            inserted_sites = {
                i: struct.sites[i].frac_coords
                for i in struct.indices_from_symbol(self.specie)
            }
            neighbor_sets = {}
            coords_env = {}

            # get neighbor sets
            temp_struct = struct.copy()
            temp_struct.remove_species([self.specie])
            for site_i in inserted_sites:
                temp_struct.insert(0, self.specie, inserted_sites[site_i])
                temp_lgf = LocalGeometryFinder()
                temp_lgf.setup_structure(temp_struct)
                # compute environments, and get structure connectivity
                temp_se = temp_lgf.compute_structure_environments(
                    maximum_distance_factor=self.distance_cutoff,
                    only_atoms=[self.specie],  # must identify specie interested in
                    max_cn=max(self.cn),
                    min_cn=min(self.cn),
                    minimum_angle_factor=0.05,
                )

                temp_lse = LightStructureEnvironments.from_structure_environments(
                    strategy=chemenv_strategies.MultiWeightsChemenvStrategy(
                        structure_environments=temp_se,
                        dist_ang_area_weight=chemenv_strategies.DistanceAngleAreaNbSetWeight(
                            surface_definition={
                                "type": "standard_elliptic",
                                "distance_bounds": {"lower": 1.2, "upper": 1.8},
                                "angle_bounds": {"lower": 0.1, "upper": 0.8},
                            }
                        ),
                        self_csm_weight=chemenv_strategies.SelfCSMNbSetWeight(
                            effective_csm_estimator={'function': 'power2_inverse_decreasing', 'options': {'max_csm': self.csm}},
                            weight_estimator={'function': 'power2_decreasing_exp', 'options': {'max_csm': self.csm, 'alpha': 1.0}},
                            symmetry_measure_type='csm_wcs_ctwcc',
                        ),
                        ce_estimator={'function': 'power2_inverse_power2_decreasing', 'options': {'max_csm': self.csm}},
                        additional_condition=AdditionalConditions.ONLY_ACB,
                    ),
                    structure_environments=temp_se,
                )

                neighbor_sets[site_i] = temp_lse.neighbors_sets[0]
                coords_env[site_i] = temp_lse.coordination_environments[0]
                temp_struct.remove_sites([0])
            for i in range(len(lse.neighbors_sets)):
                if lse.neighbors_sets[i] is None:
                    continue
                if i not in neighbor_sets or len(neighbor_sets[i]) == 0:
                    if lse.neighbors_sets[i] == []:
                        lse.neighbors_sets[i] = None
                    continue
                lse.neighbors_sets[i] += neighbor_sets[i]
                lse.coordination_environments[i] += coords_env[i]

            for i in range(len(lse.coordination_environments)):
                if (
                    lse.coordination_environments[i] is not None
                    and len(lse.coordination_environments[i]) > 0
                ):
                    n = range(len(lse.coordination_environments[i]))
                    imax = max(
                        sorted(
                            list(
                                filter(
                                    lambda x: lse.coordination_environments[i][x]["csm"]
                                    < 8,
                                    n,
                                )
                            ),
                            key=lambda x: lse.coordination_environments[i][x][
                                "ce_fraction"
                            ],
                            reverse=True,
                        ),
                        key=lambda x: int(
                            lse.coordination_environments[i][x]["ce_symbol"][-1]
                        ),
                    )
                    lse.coordination_environments[i] = [
                        lse.coordination_environments[i][imax]
                    ]
                    lse.neighbors_sets[i] = [lse.neighbors_sets[i][imax]]
                    
            connFinder = connectivity_finder.ConnectivityFinder(
                multiple_environments_choice="TAKE_HIGHEST_FRACTION"
            )
            structConnectivty = connFinder.get_structure_connectivity(lse)

            env_graph = structConnectivty.environment_subgraph()
            env_graph = nx.Graph(env_graph)

            # filter connectivty graph based on migration_graph
            
            # nx.draw_networkx(env_graph)
            # nx.draw_networkx(struct_graph.graph.to_undirected())
            for node in structConnectivty.environment_subgraph().nodes:
                for (n1, n2, data,) in (
                    structConnectivty.environment_subgraph()
                    .copy()
                    .edges(node, data=True)
                ):
                    node1 = [
                        i
                        for i in range(len(sites_from_mg))
                        if n1.central_site == sites_from_mg[i]
                    ][0]
                    node2 = [
                        i
                        for i in range(len(sites_from_mg))
                        if n2.central_site == sites_from_mg[i]
                    ][0]

                    if env_graph.has_edge(
                        n1, n2
                    ) and not struct_graph.graph.to_undirected().has_edge(node1, node2):
                        env_graph.remove_edge(n1, n2)

            # nx.draw_networkx(env_graph)

            # filter coordination species along path
            paths = []
            invalid_nodes = []
            for comp in nx.connected_components(env_graph):
                connected_comp = {}
                for node in comp:
                    if node.isite in neighbor_sets:
                        connected_comp[node] = neighbor_sets[node.isite]
                    else:
                        invalid_nodes.append(node)
                # get the octahedrons along each connected path
                paths.append(connected_comp)

            for node in invalid_nodes:
                env_graph.remove_node(node)

            # nx.draw_networkx(env_graph)

            # remove paths without tetrahedral overlap
            # remove paths without tetrahedral overlap
            edge_jimages = {}
            for path in paths:
                for n1 in path:
                    for n2 in path:
                        if (
                            env_graph.has_edge(n1, n2)
                            and n1.i_central_site <= n2.i_central_site
                        ):
                            node1 = [
                                i
                                for i in range(len(sites_from_mg))
                                if n1.central_site == sites_from_mg[i]
                            ][0]
                            node2 = [
                                i
                                for i in range(len(sites_from_mg))
                                if n2.central_site == sites_from_mg[i]
                            ][0]

                            # check for tetrahedral overlap, if not, remove edge
                            edge_data = [
                                i["to_jimage"]
                                for i in struct_graph.graph.to_undirected()
                                .get_edge_data(node1, node2)
                                .values()
                            ]
                            overlap_bool = False
                            for data in edge_data:
                                intersect = []
                                for nb_sites1 in path[n1]:
                                    for nb_sites2 in path[n2]:
                                        if (len(nb_sites1.neighb_sites) not in self.cn 
                                            or len(nb_sites2.neighb_sites) not in self.cn): continue
                                        intersect = max(
                                            [
                                                intersect,
                                                self.intersect_sites(
                                                    nb_sites1.neighb_sites,
                                                    nb_sites2.neighb_sites,
                                                    data,
                                                ),
                                            ],
                                            key=lambda x: len(x),
                                        )
                                if len(intersect) not in self.overlap_cn:
                                    continue
                                if (n1, n2) in edge_jimages:
                                    edge_jimages[(n1, n2)]["to_jimage"] += [data]
                                else:
                                    edge_jimages[(n1, n2)] = {
                                        "to_jimage": [data],
                                    }
                                overlap_bool = True
                            if overlap_bool == False:
                                env_graph.remove_edge(n1, n2)

            nx.set_edge_attributes(env_graph, edge_jimages)

            # get cycles and check for periodicity along cycle paths
            cycles = self.get_cycle_basis(env_graph)
            if len(cycles) == 0:
                env_graph.clear()
            else:
                for cycle in cycles:
                    edge_dir = [
                        edge["to_jimage"][0]
                        for edge in cycle
                        if "to_jimage" in edge.keys()
                    ]
                    if all(np.sum(np.row_stack(edge_dir), axis=0) == 0):
                        for edge in cycle:
                            if env_graph.has_node(edge["start"]):
                                env_graph.remove_node(edge["start"])
                            if env_graph.has_node(edge["end"]):
                                env_graph.remove_node(edge["end"])
            return env_graph
        except:
            return None

    def get_items(self) -> dict:
        """
        get info from electrode store for post-screening filter
        """
        for item in super(OverlapScreeningBuilder, self).get_items():
            mg_doc = self.migration_graph_store.query_one(
                {"battery_id": {"$in": [item["battery_id"]]}}
            )
            item["migration_graph"] = (
                mg_doc["migration_graph"]
                if mg_doc is not None and "migration_graph" in mg_doc.keys()
                else None
            )
            yield item

    def unary_function(self, item: dict) -> dict:
        new_item = dict(item)
        result = self.overlap_find(item["migration_graph"])
        new_item[
            "overlap_"
            + "+".join(map(str, self.cn))
            + "cn_"
            + "+".join(map(str, self.overlap_cn))
            + "o"
        ] = not (result is None or len(result.nodes) == 0)
        new_item[
            "overlap_graph_"
            + "+".join(map(str, self.cn))
            + "cn_"
            + "+".join(map(str, self.overlap_cn))
            + "o"
        ] = (None if result is None else nx.to_dict_of_dicts(result))
        return new_item
