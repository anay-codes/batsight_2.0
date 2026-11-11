"""Explicit adapter for the existing calibrated labeled dimension estimator."""

from batsight.datasets import CalibratedTOAObservationSet
from batsight.reconstruction import estimate_shoebox_dimensions


class ReconstructionService:
    def estimate_labeled_shoebox_dimensions(self, observations: CalibratedTOAObservationSet, **options):
        if not observations.labeled_first_order_reflections:
            raise ValueError("the existing estimator requires labeled first-order reflections")
        return estimate_shoebox_dimensions(observations, **options)
