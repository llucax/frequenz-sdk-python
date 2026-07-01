# License: MIT
# Copyright © 2025 Frequenz Energy-as-a-Service GmbH

"""Deprecated Formula Engine."""

from typing_extensions import TypeAlias

from .._base_types import QuantityT
from ..formulas._formula import Formula
from ..formulas._formula_3_phase import Formula3Phase

FormulaEngine: TypeAlias = Formula[QuantityT]
"""A deprecated alias for the formula engine."""

FormulaEngine3Phase: TypeAlias = Formula3Phase[QuantityT]
"""A deprecated alias for the three-phase formula engine."""


__all__ = ["FormulaEngine", "FormulaEngine3Phase"]
