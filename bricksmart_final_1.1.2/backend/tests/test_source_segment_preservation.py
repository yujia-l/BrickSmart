import numpy as np

from bricksmart.geometry.source_segment_preservation import (
    evaluate_source_segment_preservation,
    recommend_grid_size,
)


def test_source_segment_loss_is_reported_separately_from_build_failure():
    raw = np.zeros((4, 4, 4), dtype=int)
    raw[0, 0, 0] = 1
    raw[1, 1, 1] = 2
    clean = np.zeros_like(raw)
    clean[0, 0, 0] = 1
    report = evaluate_source_segment_preservation(
        source_segment_ids=[1, 2], raw_grid=raw, clean_grid=clean
    )
    assert report.status == "FAIL_SOURCE_SEGMENTS_LOST"
    assert report.missing_segment_ids == (2,)
    assert recommend_grid_size(current_grid_size=16, report=report) > 16


def test_component_lineage_maps_back_to_source_segments():
    raw = np.zeros((4, 4, 4), dtype=int)
    raw[0, 0, 0] = 5
    raw[3, 3, 3] = 5
    clean = np.zeros_like(raw)
    clean[0, 0, 0] = 1
    clean[3, 3, 3] = 2
    report = evaluate_source_segment_preservation(
        source_segment_ids=[5],
        raw_grid=raw,
        clean_grid=clean,
        clean_to_source={1: 5, 2: 5},
    )
    assert report.status == "PASS"
    assert report.clean_counts[5] == 2
