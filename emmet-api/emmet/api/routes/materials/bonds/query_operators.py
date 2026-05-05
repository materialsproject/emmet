from fastapi import Query

from emmet.api.query_operator import QueryOperator, RangeQuery
from emmet.api.utils import STORE_PARAMS


class BondLengthQuery(RangeQuery):
    """
    Method to generate a query on bond length data.
    """

    def query(
        self,
        max_bond_length_max: float | None = Query(
            None,
            description="Maximum value for the maximum bond length in the structure.",
        ),
        max_bond_length_min: float | None = Query(
            None,
            description="Minimum value for the maximum bond length in the structure.",
        ),
        min_bond_length_max: float | None = Query(
            None,
            description="Maximum value for the minimum bond length in the structure.",
        ),
        min_bond_length_min: float | None = Query(
            None,
            description="Minimum value for the minimum bond length in the structure.",
        ),
        mean_bond_length_max: float | None = Query(
            None,
            description="Maximum value for the mean bond length in the structure.",
        ),
        mean_bond_length_min: float | None = Query(
            None,
            description="Minimum value for the mean bond length in the structure.",
        ),
    ) -> STORE_PARAMS:
        return self._prepare_query(
            value_dict={
                "bond_length_stats.max": [max_bond_length_min, max_bond_length_max],
                "bond_length_stats.min": [min_bond_length_min, min_bond_length_max],
                "bond_length_stats.mean": [mean_bond_length_min, mean_bond_length_max],
            }
        )


class CoordinationEnvsQuery(QueryOperator):
    """
    Method to generate a query on coordination environment data.
    """

    def query(
        self,
        coordination_envs: str | None = Query(
            None,
            description="Query by coordination environments in the material composition as a comma-separated list\
 (e.g. 'Mo-S(6),S-Mo(3)')",
        ),
        coordination_envs_anonymous: str | None = Query(
            None,
            description="Query by anonymous coordination environments in the material composition as a comma-separated\
 list (e.g. 'A-B(6),A-B(3)')",
        ),
    ) -> STORE_PARAMS:
        crit = {}  # type: dict

        if coordination_envs:
            env_list = [env.strip() for env in coordination_envs.split(",")]
            crit["coordination_envs"] = {"$all": [str(env) for env in env_list]}

        if coordination_envs_anonymous:
            env_list = [env.strip() for env in coordination_envs_anonymous.split(",")]
            crit["coordination_envs_anonymous"] = {
                "$all": [str(env) for env in env_list]
            }

        return {"criteria": crit}
