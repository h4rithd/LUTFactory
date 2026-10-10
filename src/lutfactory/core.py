"""Identity TIFF sampling and .cube file generation."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import math
import re

import numpy as np
import tifffile


@dataclass(frozen=True)
class AtlasSpec:
    size: int
    width: int
    height: int
    patch: int
    columns: int

    @property
    def count(self) -> int:
        return self.size ** 3

    @property
    def rows(self) -> int:
        return math.ceil(self.count / self.columns)

    def validate(self) -> None:
        if self.columns * self.patch > self.width or self.rows * self.patch > self.height:
            raise ValueError("Identity chart patches do not fit frame")
        if self.patch < 3 or self.patch % 2 != 1:
            raise ValueError("Patch size must be odd and at least 3")


SPECS = {
    33: AtlasSpec(33, 1920, 1080, 7, 256),
    65: AtlasSpec(65, 3840, 2160, 5, 768),
}


def spec_for_size(size: int) -> AtlasSpec:
    if size not in SPECS:
        raise ValueError("Supported chart sizes: 33 and 65")
    spec = SPECS[size]
    spec.validate()
    return spec


def spec_for_image(image: np.ndarray) -> AtlasSpec:
    if image.ndim != 3 or image.shape[2] != 3:
        raise ValueError(f"Expected RGB TIFF (height, width, 3), got {image.shape}")
    for spec in SPECS.values():
        if image.shape[:2] == (spec.height, spec.width):
            return spec
    raise ValueError(
        f"Unexpected image dimensions {image.shape[1]}x{image.shape[0]}; "
        "expected 1920x1080 (33) or 3840x2160 (65). Do not rescale charts."
    )


def identity_samples(size: int) -> np.ndarray:
    """RGB sample lattice in .cube order: R changes fastest, then G, then B."""
    idx = np.arange(size ** 3, dtype=np.int64)
    step = float(size - 1)
    return np.column_stack((
        (idx % size) / step,
        ((idx // size) % size) / step,
        (idx // (size * size)) / step,
    ))


def identity_atlas(size: int) -> np.ndarray:
    spec = spec_for_size(size)
    flat = np.zeros((spec.rows * spec.columns, 3), dtype=np.uint16)
    flat[:spec.count] = np.rint(identity_samples(size) * 65535).astype(np.uint16)
    patches = flat.reshape(spec.rows, spec.columns, 3)
    pixels = np.repeat(np.repeat(patches, spec.patch, axis=0), spec.patch, axis=1)
    atlas = np.zeros((spec.height, spec.width, 3), dtype=np.uint16)
    atlas[:pixels.shape[0], :pixels.shape[1]] = pixels
    return atlas


def save_atlas(path: Path, size: int) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tifffile.imwrite(
        path, identity_atlas(size), photometric="rgb",
        compression=None, metadata=None,
        description=f"LUTFactory identity chart {size}^3; full RGB range; do not scale",
    )


def load_atlas(path: Path) -> tuple[np.ndarray, AtlasSpec]:
    path = Path(path)
    if not path.is_file():
        raise ValueError(f"File does not exist: {path}")
    try:
        image = tifffile.imread(path)
    except Exception as exc:
        raise ValueError(f"Cannot read TIFF: {exc}") from exc
    spec = spec_for_image(image)
    if image.dtype != np.uint16:
        raise ValueError(f"Expected 16-bit unsigned RGB TIFF; got {image.dtype}")
    return image, spec


@dataclass(frozen=True)
class PatchAnalysis:
    max_neighbor_error: float
    mean_neighbor_error: float
    affected_patches: int
    total_patches: int


def extract_samples(image: np.ndarray, spec: AtlasSpec) -> tuple[np.ndarray, PatchAnalysis]:
    """Sample centers and check adjacent pixels remain constant."""
    spec.validate()
    if image.shape != (spec.height, spec.width, 3) or image.dtype != np.uint16:
        raise ValueError("Atlas dimensions/bit depth do not match the specified chart")
    idx = np.arange(spec.count, dtype=np.int64)
    x = (idx % spec.columns) * spec.patch + spec.patch // 2
    y = (idx // spec.columns) * spec.patch + spec.patch // 2
    centers = image[y, x].astype(np.float64) / 65535.0
    errors = np.zeros(spec.count, dtype=np.float64)
    for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        neighbors = image[y + dy, x + dx].astype(np.float64) / 65535.0
        errors = np.maximum(errors, np.max(np.abs(neighbors - centers), axis=1))
    return centers, PatchAnalysis(
        max_neighbor_error=float(errors.max()),
        mean_neighbor_error=float(errors.mean()),
        affected_patches=int(np.count_nonzero(errors > 0.003)),
        total_patches=spec.count,
    )


def to_grid(samples: np.ndarray, size: int) -> np.ndarray:
    if samples.shape != (size ** 3, 3):
        raise ValueError(f"Expected {size ** 3} RGB triples")
    return samples.reshape(size, size, size, 3)  # B, G, R, channels


def resize_cube(samples: np.ndarray, source_size: int, target_size: int) -> np.ndarray:
    """Trilinear resampling of B/G/R axes without inventing new measurements."""
    if source_size not in SPECS or target_size not in (17, 33, 65):
        raise ValueError("Unsupported LUT size")
    if source_size == target_size:
        return samples.copy()
    grid = to_grid(samples, source_size)
    if (source_size - 1) % (target_size - 1) == 0:
        step = (source_size - 1) // (target_size - 1)
        return grid[::step, ::step, ::step, :].reshape(-1, 3).copy()

    t = np.linspace(0.0, source_size - 1, target_size)
    lo = np.floor(t).astype(np.intp)
    hi = np.minimum(lo + 1, source_size - 1)
    fb = (t - lo).reshape(target_size, 1, 1, 1)
    data = np.take(grid, lo, axis=0) * (1 - fb) + np.take(grid, hi, axis=0) * fb
    fg = (t - lo).reshape(1, target_size, 1, 1)
    data = np.take(data, lo, axis=1) * (1 - fg) + np.take(data, hi, axis=1) * fg
    fr = (t - lo).reshape(1, 1, target_size, 1)
    data = np.take(data, lo, axis=2) * (1 - fr) + np.take(data, hi, axis=2) * fr
    return data.reshape(-1, 3)


def safe_stem(name: str) -> str:
    result = re.sub(r"[^A-Za-z0-9_-]+", "_", name).strip("_-")
    if not result:
        raise ValueError("LUT name must contain a letter or digit")
    return result[:80]


def write_cube(
    path: Path, samples: np.ndarray, size: int, title: str, source_size: int,
    input_space: str = "Unspecified", output_space: str = "Unspecified",
) -> None:
    path = Path(path)
    if size not in (17, 33, 65):
        raise ValueError("Unsupported .cube size")
    if samples.shape != (size ** 3, 3) or not np.isfinite(samples).all():
        raise ValueError("Incorrect or non-finite LUT samples")
    if np.any((samples < 0) | (samples > 1)):
        raise ValueError("TIFF-derived LUT samples must be in 0..1")
    path.parent.mkdir(parents=True, exist_ok=True)
    title = safe_stem(title)
    input_space = re.sub(r"[\r\n\x00]+", " ", input_space).strip()
    output_space = re.sub(r"[\r\n\x00]+", " ", output_space).strip()
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write("# LUTFactory - Developed by h4rithd with the help of AI\n")
        stream.write(f"# Input: {input_space}\n# Output: {output_space}\n")
        if source_size == size:
            stream.write(f"# Direct {source_size}-point identity-chart measurements\n")
        else:
            stream.write(f"# Resampled from {source_size}-point measurements; no additional measured detail\n")
        stream.write(f'TITLE "{title}"\nLUT_3D_SIZE {size}\n')
        stream.write("DOMAIN_MIN 0.0 0.0 0.0\nDOMAIN_MAX 1.0 1.0 1.0\n")
        for r, g, b in samples:
            stream.write(f"{r:.8f} {g:.8f} {b:.8f}\n")


def read_cube(path: Path) -> tuple[int, np.ndarray]:
    size = None
    samples = []
    with Path(path).open("r", encoding="utf-8") as stream:
        for n, raw in enumerate(stream, 1):
            line = raw.strip()
            if not line or line.startswith("#") or line.startswith(("TITLE", "DOMAIN_")):
                continue
            if line.startswith("LUT_3D_SIZE"):
                size = int(line.split()[1])
                continue
            try:
                vals = [float(v) for v in line.split()]
            except ValueError as exc:
                raise ValueError(f"Invalid .cube data on line {n}") from exc
            if len(vals) != 3:
                raise ValueError(f"Expected RGB triple on line {n}")
            samples.append(vals)
    if size is None or size < 2:
        raise ValueError("Missing LUT_3D_SIZE")
    data = np.asarray(samples, dtype=np.float64)
    if data.shape != (size ** 3, 3) or not np.isfinite(data).all():
        raise ValueError(f"Incorrect number of .cube rows for size {size}")
    return size, data
