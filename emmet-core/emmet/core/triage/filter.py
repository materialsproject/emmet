from __future__ import annotations

from typing import Any, Union


class Filter:
    ref_arg: Any = None
    operation: Union[str, list[str]] = None
    kwargs: dict = None
    reason: str = None

    def __init__(self):
        return

    def eval(self, comp_arg):
        self.comp_arg = comp_arg
        return {
            "value": self.comp_arg,
            "passed": self.passed,
            "reason": None if self.passed else self._reason,
        }

    def _unary_comparator(self):
        ops = {
            "==": "__eq__",
            ">": "__gt__",
            ">=": "__ge__",
            "<": "__lt__",
            "<=": "__le__",
            "in": "__contains__",
        }

        if isinstance(self.operation, list):
            operators = self.operation
            ref_args = self.ref_arg
        else:
            operators = [self.operation]
            ref_args = [self.ref_arg]

        cumulative = True
        for iop, operator in enumerate(operators):
            return_negative = False
            if "not" in operator:
                op_str = operator.split("not ")
                op = ops.get(op_str, op_str)
                return_negative = True
            elif operator == "!=":
                op = ops["=="]
                return_negative = True
            else:
                # allows for using specific operations like issuperset or intersection
                op = ops.get(operator, operator)

            val = ref_args[iop].__getattribute__(op)(self.comp_arg)
            cumulative = cumulative and (not val if return_negative else val)

        return cumulative

    @property
    def passed(self):
        return self._unary_comparator()

    @property
    def _reason(self):
        return NotImplementedError if self.reason is None else self.reason
