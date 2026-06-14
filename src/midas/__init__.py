"""MIDAS — autonomous revenue operator.

A general, reusable, trustworthy core (`midas.core`) + a focused revenue-operator
flagship (`midas.flagship`). The flagship may import the core; the core must never
import the flagship (enforced in CI via import-linter).
"""

__version__ = "0.0.1"
