from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools/verification/generate_build_equivalence_report.py"


def _load_report_module():
    """Load report module.
    
    :returns: The result produced by the function.
    """
    spec = importlib.util.spec_from_file_location("build_equivalence_report", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_equivalence_report_generator_accepts_identical_baseline(tmp_path: Path) -> None:
    """Test that equivalence report generator accepts identical baseline.
    
    :param tmp_path: Temporary filesystem path provided by pytest.
    :type tmp_path: Path
    """
    module = _load_report_module()
    baseline = ROOT / "tests/regression/bird/expected"
    output = tmp_path / "bird-equivalence.html"

    result = module.generate_report(
        baseline_dir=baseline,
        candidate_dir=baseline,
        output_path=output,
        baseline_label="baseline",
        candidate_label="candidate",
        model_name="bird",
        catalog_path=ROOT / "block_catalog/block_definitions.csv",
    )

    assert result.equivalent is True
    assert result.placement_equal is True
    assert result.timeline_equal is True
    assert result.metrics_equal is True
    assert output.is_file()
    report = output.read_text(encoding="utf-8")
    assert "PASS — equivalent build output" in report
    assert "Canonical artifact comparison" in report
