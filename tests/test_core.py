from pathlib import Path

import numpy as np
import pytest
import tifffile

from lutfactory.core import (
    extract_samples, identity_samples, load_atlas, read_cube, resize_cube,
    safe_stem, save_atlas, spec_for_size, write_cube,
)
from lutfactory.cli import main


def test_33_identity_roundtrip(tmp_path):
    filename = tmp_path / "identity_33.tif"
    save_atlas(filename, 33)
    image, spec = load_atlas(filename)
    samples, report = extract_samples(image, spec)
    assert spec.size == 33
    np.testing.assert_allclose(samples, identity_samples(33), atol=0.5 / 65535)
    assert report.max_neighbor_error == 0


def test_65_identity_roundtrip(tmp_path):
    filename = tmp_path / "identity_65.tif"
    save_atlas(filename, 65)
    image, spec = load_atlas(filename)
    samples, report = extract_samples(image, spec)
    assert spec.size == 65
    np.testing.assert_allclose(samples, identity_samples(65), atol=0.5 / 65535)
    assert report.max_neighbor_error == 0


def test_resample_grid_points():
    data = identity_samples(33)
    up = resize_cube(data, 33, 65)
    down = resize_cube(up, 65, 33)
    np.testing.assert_allclose(up, identity_samples(65), atol=1e-12)
    np.testing.assert_allclose(down, data, atol=1e-12)


def test_cube_roundtrip(tmp_path):
    file = tmp_path / "look.cube"
    data = identity_samples(33)
    write_cube(file, data, 33, "CinematicLook", 33)
    size, result = read_cube(file)
    assert size == 33
    np.testing.assert_allclose(result, data, atol=5.1e-9)


def test_filename_sanitization():
    assert safe_stem("Cinematic Look") == "Cinematic_Look"
    with pytest.raises(ValueError):
        safe_stem("///")


def test_wrong_dimensions(tmp_path):
    path = tmp_path / "bad.tif"
    tifffile.imwrite(path, np.zeros((720, 1280, 3), dtype=np.uint16), photometric="rgb")
    with pytest.raises(ValueError, match="Unexpected image dimensions"):
        load_atlas(path)


def test_cli_end_to_end(tmp_path):
    atlas = tmp_path / "chart.tif"
    out = tmp_path / "output"
    assert main(["--no-color", "chart", "--output", str(atlas)]) == 0
    assert main(["--no-color", "validate", str(atlas), "--identity"]) == 0
    assert main(["--no-color", "build", str(atlas), "--name", "TestLook",
                 "--output-dir", str(out)]) == 0
    camera = out / "TestLook_CAMERA_33.cube"
    resolve = out / "TestLook_RESOLVE_65.cube"
    assert camera.exists() and resolve.exists()
    assert read_cube(camera)[0] == 33
    assert read_cube(resolve)[0] == 65
    assert main(["--no-color", "inspect", str(camera)]) == 0


def test_detect_spatial_variation():
    from lutfactory.core import identity_atlas
    atlas = identity_atlas(33)
    atlas[3, 4] = [65535, 65535, 65535]
    _, report = extract_samples(atlas, spec_for_size(33))
    assert report.max_neighbor_error > 0.003


def test_camera_17_exact_subset():
    actual = resize_cube(identity_samples(33), 33, 17)
    np.testing.assert_allclose(actual, identity_samples(17), atol=1e-12)


def test_cube_metadata_is_sanitized(tmp_path):
    path = tmp_path / "safe.cube"
    write_cube(path, identity_samples(17), 17, "Safe", 33, "Input\nUntrusted", "Output")
    assert read_cube(path)[0] == 17
