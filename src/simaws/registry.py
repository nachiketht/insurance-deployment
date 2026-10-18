"""ECR-like registry. Images are content-addressed; the digest is the identity."""

import hashlib
import io
import tarfile
from pathlib import Path

from simaws import ACCOUNT, REGION


def repo_arn(name: str) -> str:
    return f"arn:simaws:ecr:{REGION}:{ACCOUNT}:repository/{name}"


def build_archive(root: Path, include: list[str]) -> bytes:
    """Deterministic image-layer stand-in: sorted entries, zero mtime/uid/gid, no gzip header time.
    Same source tree always gives the same sha256 (the discipline a real image digest gives)."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.PAX_FORMAT) as tar:
        for rel in include:
            base = root / rel
            files = [base] if base.is_file() else sorted(p for p in base.rglob("*") if p.is_file())
            for p in sorted(files):
                if "__pycache__" in p.parts or p.suffix == ".pyc":
                    continue
                data = p.read_bytes()
                info = tarfile.TarInfo(str(p.relative_to(root)))
                info.size, info.mtime, info.uid, info.gid, info.mode = len(data), 0, 0, 0, 0o644
                tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def digest(blob: bytes) -> str:
    return "sha256:" + hashlib.sha256(blob).hexdigest()


def create_repo(state: dict, name: str) -> str:
    state["repos"].setdefault(name, {"Arn": repo_arn(name), "images": {}})
    return repo_arn(name)


def push(state: dict, name: str, blob: bytes, tag: str) -> str:
    d = digest(blob)
    path = Path(state.get("_blob_dir", ".simaws/blobs"))
    path.mkdir(parents=True, exist_ok=True)
    (path / d.replace(":", "-")).write_bytes(blob)
    state["repos"][name]["images"][d] = {"tags": [tag], "size": len(blob)}
    return d


def pull(state: dict, name: str, d: str) -> bytes:
    blob = (Path(state.get("_blob_dir", ".simaws/blobs")) / d.replace(":", "-")).read_bytes()
    if digest(blob) != d:
        raise ValueError(f"image {d} failed digest verification")
    return blob
