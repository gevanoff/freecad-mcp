"""Fail unless the recorded live A/B evidence and final artifact hashes agree."""
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parent


def records(run):
    return json.loads((root / "results" / run / "responses.json").read_text(encoding="utf-8"))


def data(record):
    value = record["result"]
    return json.loads(value[0]) if isinstance(value, list) and len(value) == 1 else value


baseline = records("addon-fixed")
fixed = records("fixed")
assert [r["tool"] for r in baseline] == [r["tool"] for r in fixed]
assert [r["arguments"] for r in baseline] == [r["arguments"] for r in fixed]
old_bounds = data(baseline[3])["bounds"]
assert abs(old_bounds["max"][0] - old_bounds["min"][0] - 22) > 0.01
for index in (3, 5):
    assert data(fixed[index])["bounds"] == {"min": [-11, -11, 0], "max": [11, 11, 4]}
for run in ("fixed", "model", "validation"):
    for record in records(run):
        assert not record["isError"], record
        result = data(record)
        if isinstance(result, dict):
            assert result.get("success", True), result
            if "image_file" in result:
                assert (root / "results" / run / result["image_file"]).read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
report = json.loads((root / "artifacts/validation.json").read_text(encoding="utf-8"))
for name, digest in report["artifact_sha256"].items():
    assert hashlib.sha256((root / "artifacts" / name).read_bytes()).hexdigest() == digest, name
for stage in ("native", "reopened_native", "step_reimport"):
    result = report[stage]
    assert result["valid"] and result["closed"] and result["solids"] == 1
    assert result["bounds_mm"] == [22, 22, 31.5]
assert report["stl_reimport"]["solid"]
handler = root.parents[1] / "freecad_addon/handlers/document.py"
assert hashlib.sha256(handler.read_bytes()).hexdigest() == report["installed_document_handler_sha256"]
print("PASS: equivalent A/B requests, exact live bounds, successful model/export tools, matching artifact and installed-code hashes")
