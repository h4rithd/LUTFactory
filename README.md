# LUTFactory

**Build camera-monitoring and professional color-grading 3D LUTs from graded identity charts.**

LUTFactory is a free, open-source Python command-line application that generates RGB identity charts and converts their graded renders into standard `.cube` LUTs. Works with DaVinci Resolve and other workflows capable of rendering an unmodified 16-bit TIFF chart.

**Developed by [h4rithd](https://github.com/h4rithd) with the help of AI.** MIT licensed.

## Features

- Colorful command-line banner, readable diagnostics, validation, and error messages
- Deterministic **33-point 1920×1080** and **65-point 3840×2160** RGB 16-bit identity charts
- Generates **33-point camera LUT** and **65-point Resolve LUT** in one command
- Supports camera output size 17 or 33, and Resolve output size 33 or 65
- Native measured sampling, exact-subset downsampling, and trilinear interpolation
- Detects TIFF dimensions/bit depth and spatial inconsistencies inside color patches
- Offline: no account, uploading, or cloud processing

## Installation

Python 3.10+ is required. Compatible with macOS, Linux and Windows.

```bash
git clone https://github.com/h4rithd/LUTFactory.git
cd LUTFactory
python3 -m pip install -e .
lutfactory --help
```

For development:

```bash
python3 -m pip install -e '.[dev]'
pytest
```

## Quick start

### 1. Generate an identity chart

```bash
lutfactory chart --size 33 --output identity_33.tif
```

To capture a **native 65-point** transform, start with:

```bash
lutfactory chart --size 65 --output identity_65.tif
```

### 2. Render the graded chart in DaVinci Resolve

1. Import the chart into Resolve. Use a **1920×1080** timeline for the 33-point chart or **3840×2160** for the 65-point chart.
2. Do not crop, resize, stabilize, reposition, or otherwise alter the pixel geometry.
3. Apply your complete intended input conversion, color grade, and output conversion. Disable automatic transforms that are *not* intended to become part of the LUT.
4. Disable grain, blur, glow, overlays, sharpening, power windows, and other spatial or time-varying operations. A LUT captures only static per-pixel color operations.
5. In Deliver, mark **In and Out on the same frame**, select **In/Out Range**, and export **one frame** as **TIFF / RGB 16 bits / Full data levels** at the chart's exact dimensions.

### 3. Convert the graded render

```bash
lutfactory validate graded_chart.tif

lutfactory build graded_chart.tif \
  --name CinematicLook \
  --output-dir output \
  --input-space 'Sony S-Gamut3.Cine / S-Log3' \
  --output-space 'Rec.709 / Gamma 2.4'
```

Files produced:

```text
output/
  CinematicLook_CAMERA_33.cube
  CinematicLook_RESOLVE_65.cube
```

Inspect any generated LUT:

```bash
lutfactory inspect output/CinematicLook_CAMERA_33.cube
```

**Important:** `--input-space` and `--output-space` write *descriptive comments* into the LUT. They do not perform color transforms. Your graded chart determines the actual RGB conversion. When the grade already included input and output CSTs, do **not** add them again around the LUT.

## Accuracy: 33-point vs 65-point

| Source chart | Camera 33-point LUT | Resolve 65-point LUT |
| --- | --- | --- |
| 33-point | Direct samples | Interpolated from 33 |
| 65-point | Exact subset of 65 samples | Direct samples |

**Interpolating a 33-point LUT to 65 points does not create new measured color information.** For a genuinely native 65-point LUT, generate and render the 65-point chart.

The identity-chart resolution does **not** determine the resolution of footage on which the final LUT can be used. Both LUTs can be applied to 4K or higher-resolution footage.

## Commands

```text
lutfactory [--no-color] chart [--size {33,65}] [--output PATH]
lutfactory [--no-color] build GRADED_TIFF [--name NAME] [--output-dir DIR]
    [--camera-size {17,33}] [--resolve-size {33,65}]
    [--input-space TEXT] [--output-space TEXT]
    [--strict] [--threshold FLOAT]
lutfactory [--no-color] validate TIFF [--identity] [--threshold FLOAT]
lutfactory [--no-color] inspect LUT.cube
lutfactory --version
```

Use `--strict` to reject graded renders with patch inconsistencies beyond `--threshold` (default 0.003 in normalized RGB). Use `validate --identity` only for an original, *ungraded* identity chart.

## Camera and grading software

For **Sony A7 V**, copy the compatible 33-point LUT to the SD card folder:

```text
/Private/Sony/PRO/LUT/
```

Import it using the camera's user LUT management menu, and ensure the source Log gamut/gamma matches the format represented in your LUT.

For **DaVinci Resolve**, install the 65-point LUT in the LUT directory and refresh LUTs. Apply it to footage matching the captured input encoding. If your chart render already included the final Rec.709 transform, do not add another output transform.

## Limitations and verification

- 3D LUTs approximate a static RGB-to-RGB conversion; they cannot capture grain, spatial effects, masks, tracking, or frame-dependent operations.
- Unsupported processing, chart scaling, incorrect data levels, or unintended display transforms may compromise accuracy.
- A finite 3D lattice approximates complex nonlinear transformations between samples.
- **Always compare** the exported LUT against the complete original grade on representative footage before using it for exposure monitoring or final production.

## Author and license

**Developed by h4rithd with the help of AI.** MIT licensed, see [LICENSE](LICENSE).

LUTFactory is an independent open-source project, not a product of a camera or editing-software company.
