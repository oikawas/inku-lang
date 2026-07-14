"""Compatibility exports for the shared, read-only composition mirror.

Generation modules must not import this module or ``inku_analysis``.
"""

from inku_analysis import (
    composition_distance,
    composition_family,
    composition_vector,
    motif_signatures,
)

__all__ = [
    "composition_distance",
    "composition_family",
    "composition_vector",
    "motif_signatures",
]
