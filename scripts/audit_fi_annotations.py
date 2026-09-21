import io
import math
import pickle
import pickletools
import statistics
import zipfile
from pathlib import Path

import numpy as np

ROOT = Path(r"D:\FairHireAI-data\raw\FirstImpressionsV2\annotations")
TRAIN = ROOT / "annotation_training.pkl"
VAL_ZIP = ROOT / "val-annotation-e.zip"
VAL_DIR = ROOT / "validation"
PASSWORD = b"zeAzLQN7DnSIexQukc9W"

ALLOWED_GLOBALS = {
    ("numpy.core.multiarray", "scalar"): np.core.multiarray.scalar,
    ("numpy", "dtype"): np.dtype,
}
ALLOWED_GLOBAL_NAMES = {
    f"{module} {name}" for module, name in ALLOWED_GLOBALS
}
FORBIDDEN = {
    "STACK_GLOBAL", "OBJ", "INST", "NEWOBJ", "NEWOBJ_EX",
    "EXT1", "EXT2", "EXT4", "PERSID", "BINPERSID",
}


class RestrictedUnpickler(pickle.Unpickler):
    def find_class(self, module, name):
        key = (module, name)
        if key not in ALLOWED_GLOBALS:
            raise pickle.UnpicklingError(f"Forbidden global: {module}.{name}")
        return ALLOWED_GLOBALS[key]

    def persistent_load(self, _pid):
        raise pickle.UnpicklingError("Persistent IDs are forbidden")


def safe_load(path):
    payload = path.read_bytes()
    operations = list(pickletools.genops(payload))
    globals_found = {
        argument
        for opcode, argument, _ in operations
        if opcode.name == "GLOBAL"
    }
    forbidden_found = {
        opcode.name for opcode, _, _ in operations
        if opcode.name in FORBIDDEN
    }

    if globals_found - ALLOWED_GLOBAL_NAMES:
        raise RuntimeError(f"Unexpected globals: {globals_found}")
    if forbidden_found:
        raise RuntimeError(f"Forbidden opcodes: {forbidden_found}")

    return RestrictedUnpickler(
        io.BytesIO(payload), encoding="latin1"
    ).load()


def extract_validation():
    VAL_DIR.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(VAL_ZIP) as archive:
        for member in archive.infolist():
            if member.is_dir():
                continue
            target = (VAL_DIR / member.filename).resolve()
            if VAL_DIR.resolve() not in target.parents:
                raise RuntimeError(f"Unsafe ZIP path: {member.filename}")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(member, pwd=PASSWORD))

    matches = list(VAL_DIR.rglob("*annotation*.pkl"))
    if len(matches) != 1:
        raise RuntimeError(f"Expected one validation pickle: {matches}")
    return matches[0]


def summarize(name, path):
    data = safe_load(path)
    if not isinstance(data, dict) or "interview" not in data:
        raise RuntimeError(f"{name}: interview labels missing")

    scores = data["interview"]
    values = [float(value) for value in scores.values()]

    if not values or not all(math.isfinite(value) for value in values):
        raise RuntimeError(f"{name}: invalid scores")
    if min(values) < 0 or max(values) > 1:
        raise RuntimeError(f"{name}: scores outside [0,1]")

    print(f"{name} keys: {sorted(data.keys())}")
    print(f"{name} samples: {len(values)}")
    print(f"{name} range: {min(values):.6f} to {max(values):.6f}")
    print(f"{name} mean: {statistics.fmean(values):.6f}")


validation = extract_validation()
summarize("TRAIN", TRAIN)
summarize("VALIDATION", validation)
print(f"Validation file: {validation}")
print("ANNOTATION AUDIT PASSED")
