"""Fast regression tests for the R1 auto-vectorization PoC (synthetic data only, no real maps)."""
import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from scan2arcgis.synth.generate import SynthConfig, generate  # noqa: E402
from scan2arcgis.recog.legend_classifier import LegendClass, classify  # noqa: E402
from scan2arcgis.eval.raster_metrics import (pixel_metrics, line_buffer_f1, object_f1,  # noqa: E402
                                             class_boundaries, auroc)
from scan2arcgis.vector.polygonize import polygons_from_labels, contacts_from_polygons, topology_report  # noqa: E402
from scan2arcgis.confidence.decide import decide_region, decide_line  # noqa: E402
from scan2arcgis.export.gpkg import d0_record, write_layers  # noqa: E402
from scan2arcgis.d0 import validate_record  # noqa: E402


@pytest.fixture(scope="module")
def small_map():
    sm = generate(SynthConfig(seed=7, size=512, n_seeds=12, n_lenses=2, n_faults=2))
    x, y, w, h = sm.map_box
    valid = np.zeros(sm.labels.shape, bool); valid[y:y + h, x:x + w] = True
    classes = [LegendClass(e["class_id"], e["legend_code"], tuple(e["swatch_box"])) for e in sm.legend]
    return sm, valid, classes


def test_generator_is_deterministic():
    a = generate(SynthConfig(seed=3, size=256, n_seeds=8))
    b = generate(SynthConfig(seed=3, size=256, n_seeds=8))
    assert np.array_equal(a.image, b.image) and np.array_equal(a.labels, b.labels)


def test_metrics_on_perfect_prediction(small_map):
    sm, valid, _ = small_map
    pm = pixel_metrics(sm.labels, sm.labels, valid)
    assert pm["pixel_accuracy"] == 1.0 and pm["miou"] == 1.0
    b = class_boundaries(sm.labels, valid)
    assert line_buffer_f1(b, b, 2.0, valid)["f1"] == 1.0
    ob = object_f1(sm.labels, sm.labels, sm.instances, valid, min_gt_px=50)
    assert ob["fp"] == 0 and ob["fn"] == 0


def test_auroc_basic():
    assert auroc(np.array([0.1, 0.2, 0.8, 0.9]), np.array([0, 0, 1, 1])) == 1.0
    assert auroc(np.array([0.5, 0.5]), np.array([1, 1])) is None


def test_legend_classifier_reaches_baseline_on_clean_synthetic(small_map):
    sm, valid, classes = small_map
    r = classify(sm.image, valid, classes, n_estimators=20)
    pm = pixel_metrics(r.labels, sm.labels, valid)
    # regression guards only (observed 0.986 / 0.95 at commit time), NOT acceptance thresholds
    assert pm["pixel_accuracy"] > 0.95 and pm["miou"] > 0.85
    assert r.margin.min() >= 0 and r.margin.max() <= 1


def test_polygons_form_a_partition_and_contacts_agree(small_map):
    sm, valid, _ = small_map
    polys = polygons_from_labels(sm.labels, valid, min_area_px=1, simplify_px=0)
    topo = topology_report(polys, float(valid.sum()))
    assert topo["invalid"] == 0 and topo["overlap_area_px"] < 1e-6
    assert abs(topo["coverage_ratio"] - 1.0) < 1e-6
    contacts = contacts_from_polygons(polys)
    assert contacts and all(ca != cb for _, ca, cb, _, _ in contacts)


def test_decision_policy_never_auto_accepts():
    hard_ok = [{"check_id": "geom_valid", "status": "PASS"}]
    for m in (0.0, 0.3, 0.6, 0.99):
        assert decide_region({"mean_margin": m, "low_margin_frac": 0.0}, hard_ok) != "AUTO_ACCEPT"
    assert decide_region({"mean_margin": 0.99, "low_margin_frac": 0.0}, [{"check_id": "x", "status": "FAIL"}]) == "BLOCKED"
    assert decide_line({"side_margins": [0.9, 0.9]}, hard_ok, "contact") != "AUTO_ACCEPT"


def test_gpkg_export_is_unreferenced_and_d0_valid(tmp_path, small_map):
    import pyogrio
    sm, valid, _ = small_map
    polys = polygons_from_labels(sm.labels, valid, min_area_px=20, simplify_px=0)
    items = []
    for k, (g, c) in enumerate(polys[:5]):
        rec = d0_record(f"t_u{k}", "synthetic", "stratigraphic_unit", "X", f"L{c}", 0.5, "test", ("hybrid", "t", "m0"),
                        "test", "run0", "NONE", [{"check_id": "geom_valid", "status": "PASS"}], {})
        assert validate_record(rec) == []
        items.append((g, rec))
    out = tmp_path / "t.gpkg"
    write_layers(out, {"geologic_units": items})
    info = pyogrio.read_info(out, layer="geologic_units")
    assert info["crs"] is None
    df = pyogrio.read_dataframe(out, layer="geologic_units")
    assert set(df["coord_space"]) == {"image_px_unreferenced"}
    assert set(df["calibration_status"]) == {"UNCALIBRATED"}
    assert df["calibrated_p_correct"].isna().all()


def test_export_rejects_fake_probability(tmp_path, small_map):
    sm, valid, _ = small_map
    g, c = polygons_from_labels(sm.labels, valid, min_area_px=20, simplify_px=0)[0]
    rec = d0_record("bad", "synthetic", "stratigraphic_unit", "X", "L0", 0.95, "test", ("hybrid", "t", "m0"),
                    "test", "run0", "NONE", [], {})
    rec["calibrated_p_correct"] = 0.95       # UNCALIBRATED record claiming a probability
    with pytest.raises(ValueError):
        write_layers(tmp_path / "bad.gpkg", {"geologic_units": [(g, rec)]})


def test_known_limitation_small_intrusive_body_can_be_lost():
    """Documents a real failure mode (R1 finding): on a 384 px map a small intrusive lens
    is merged away by small-region removal. If this test starts failing, the limitation
    was fixed -- update docs/research/auto_vectorization_r1/comparison_experiment.md."""
    sm = generate(SynthConfig(seed=7, size=384, n_seeds=10, n_lenses=2, n_faults=2))
    x, y, w, h = sm.map_box
    valid = np.zeros(sm.labels.shape, bool); valid[y:y + h, x:x + w] = True
    classes = [LegendClass(e["class_id"], e["legend_code"], tuple(e["swatch_box"])) for e in sm.legend]
    r = classify(sm.image, valid, classes, n_estimators=20)
    ious = pixel_metrics(r.labels, sm.labels, valid)["iou_per_class"]
    assert ious.get(11, 0.0) < 0.2
