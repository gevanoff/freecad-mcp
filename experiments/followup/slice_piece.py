"""Run Bambu Studio locally with explicit, flattened installed system profiles."""
import hashlib
import json
import math
from collections import Counter
from pathlib import Path
import subprocess
import time
import zipfile
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
INSTALL = Path(r"C:\Program Files\Bambu Studio")
PROFILES = INSTALL / "resources/profiles/BBL"

def profile(kind, name, stack=()):
    assert name not in stack, "Profile inheritance cycle"
    matches = list((PROFILES / kind).rglob(name + ".json"))
    assert len(matches) == 1, (name, matches)
    data = json.loads(matches[0].read_text(encoding="utf-8"))
    base = profile(kind, data["inherits"], stack + (name,)) if data.get("inherits") else {}
    base.update(data)
    base.pop("inherits", None)
    return base

def main():
    output = HERE / "slicer"
    output.mkdir(exist_ok=True)
    for kind, name in [("machine", "Bambu Lab X1E 0.4 nozzle"),
                       ("process", "0.20mm Standard @BBL X1C"),
                       ("filament", "Generic PLA")]:
        (output / (kind + ".json")).write_text(json.dumps(profile(kind, name), indent=2))
    model = HERE.parent / "chatturanga/artifacts/ChatturangaFootSoldier.stl"
    command = [str(INSTALL / "bambu-studio.exe"), "--load-settings",
               str(output / "machine.json") + ";" + str(output / "process.json"),
               "--load-filaments", str(output / "filament.json"),
               "--curr-bed-type", "Textured PEI Plate", "--arrange", "1",
               "--slice", "0", "--export-3mf", "Chatturanga-X1E-PLA.3mf", str(model)]
    started = time.time()
    result = subprocess.run(command, cwd=output, capture_output=True, timeout=180)
    assert (output / "result.json").stat().st_mtime >= started - 1, "Stale slicer result"
    (output / "stdout.log").write_bytes(result.stdout)
    (output / "stderr.log").write_bytes(result.stderr)
    report = {"exit_code": result.returncode, "command": command,
              "input_sha256": hashlib.sha256(model.read_bytes()).hexdigest(),
              "slicer_result": json.loads((output / "result.json").read_text())}
    archive = output / "Chatturanga-X1E-PLA.3mf"
    if archive.exists():
        assert archive.stat().st_mtime >= started - 1, "Stale sliced artifact"
        with zipfile.ZipFile(archive) as z:
            config = json.loads(z.read("Metadata/project_settings.config"))
            keys = ["printer_model", "printer_variant", "nozzle_diameter", "filament_type",
                    "filament_settings_id", "layer_height", "enable_support", "curr_bed_type",
                    "wall_loops", "sparse_infill_density"]
            report["effective_settings"] = {key: config.get(key) for key in keys}
            assert config["printer_model"] == "Bambu Lab X1E"
            assert config["nozzle_diameter"] == ["0.4"]
            assert config["filament_type"] == ["PLA"]
            for name in ["Metadata/plate_1.png", "Metadata/top_1.png"]:
                (output / Path(name).name).write_bytes(z.read(name))
            report["archive_files"] = z.namelist()
            models = []
            for name in z.namelist():
                if name.endswith(".model"):
                    root = ET.fromstring(z.read(name))
                    pts = [tuple(float(v.attrib[a]) for a in ("x", "y", "z"))
                           for v in root.findall(".//{*}vertex")]
                    if pts:
                        bounds = [max(p[i] for p in pts) - min(p[i] for p in pts) for i in range(3)]
                        faces = [tuple(int(t.attrib[k]) for k in ("v1", "v2", "v3"))
                                 for t in root.findall(".//{*}triangle")]
                        directed = Counter((f[i], f[(i+1) % 3]) for f in faces for i in range(3))
                        assert all(n == 1 and directed[(b, a)] == 1 for (a, b), n in directed.items()), "Open or inconsistently oriented mesh"
                        assert root.get("unit", "millimeter") == "millimeter"
                        assert all(math.isclose(a, b, abs_tol=0.001) for a, b in zip(bounds, [22, 22, 31.5]))
                        models.append({"file": name, "unit": root.get("unit", "millimeter"),
                                       "bounds_mm": bounds, "vertices": len(pts),
                                       "triangles": len(faces), "closed_oriented_mesh": True})
            report["models"] = models
            for name in z.namelist():
                if name.endswith(".gcode"):
                    lines = z.read(name).decode().splitlines()
                    report.setdefault("gcode", {})[name] = [line for line in lines if line.startswith(";") and any(k in line.lower() for k in ("total estimated", "total layer", "filament used", "model printing time"))][:30]
    (output / "report.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    assert result.returncode == 0 and report["slicer_result"]["return_code"] == 0
    assert len(report.get("models", [])) == 1
    assert report.get("gcode"), "No actual sliced G-code in exported archive"

if __name__ == "__main__":
    main()
