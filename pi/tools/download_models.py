"""Download the face models into /models (bind-mounted to ./models).

    docker compose run --rm recognizer python tools/download_models.py

- YuNet face detector (OpenCV Zoo, MIT).
- MobileFaceNet embedder: w600k_mbf.onnx from InsightFace's buffalo_s pack.
  InsightFace's pretrained models are licensed for non-commercial use only,
  which fits a private home project; swap in SFace (Apache 2.0) if that changes.

Already-present files are skipped. SHA-256 is printed so it can be pinned below.
"""
import argparse
import hashlib
import io
import sys
import urllib.request
import zipfile
from pathlib import Path

YUNET_URL = (
    "https://github.com/opencv/opencv_zoo/raw/main/models/"
    "face_detection_yunet/face_detection_yunet_2023mar.onnx"
)
BUFFALO_S_URL = "https://github.com/deepinsight/insightface/releases/download/v0.7/buffalo_s.zip"

# Pinned from the first verified download (2026-10-25) to detect tampering or corruption.
EXPECTED_SHA256: dict[str, str] = {
    "face_detection_yunet_2023mar.onnx": "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4",
    "w600k_mbf.onnx": "9cc6e4a75f0e2bf0b1aed94578f144d15175f357bdc05e815e5c4a02b319eb4f",
}


def fetch(url: str) -> bytes:
    print(f"  downloading {url}")
    with urllib.request.urlopen(url, timeout=120) as resp:
        return resp.read()


def save(dest: Path, data: bytes) -> None:
    digest = hashlib.sha256(data).hexdigest()
    expected = EXPECTED_SHA256.get(dest.name)
    if expected and expected != digest:
        sys.exit(f"  sha256 mismatch for {dest.name}: got {digest}, expected {expected}")
    dest.write_bytes(data)
    print(f"  saved {dest} ({len(data) / 1e6:.1f} MB) sha256={digest}")


def get_yunet(out: Path) -> None:
    dest = out / "face_detection_yunet_2023mar.onnx"
    if dest.exists():
        print(f"  {dest.name} present, skipping")
        return
    save(dest, fetch(YUNET_URL))


def get_mobilefacenet(out: Path) -> None:
    dest = out / "w600k_mbf.onnx"
    if dest.exists():
        print(f"  {dest.name} present, skipping")
        return
    with zipfile.ZipFile(io.BytesIO(fetch(BUFFALO_S_URL))) as zf:
        member = next(n for n in zf.namelist() if n.endswith("w600k_mbf.onnx"))
        save(dest, zf.read(member))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=Path("/models"))
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    print("YuNet face detector")
    get_yunet(args.out)
    print("MobileFaceNet embedder")
    get_mobilefacenet(args.out)


if __name__ == "__main__":
    main()
