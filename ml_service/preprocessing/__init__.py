"""Multimodal preprocessing for FairHireAI."""

from ml_service.preprocessing.alignment import (
    ACOUSTIC_DIM,
    VISUAL_DIM,
    align_sample,
    load_aligned_sample,
)

__all__ = [
    "ACOUSTIC_DIM",
    "VISUAL_DIM",
    "align_sample",
    "load_aligned_sample",
]
