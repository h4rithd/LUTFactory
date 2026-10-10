"""LUTFactory command-line user interface."""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from . import __version__
from .core import (
    extract_samples, identity_samples, load_atlas, read_cube, resize_cube,
    safe_stem, save_atlas, spec_for_size, write_cube,
)

BANNER = r"""
 _     _   _ _____ _____           _
| |   | | | |_   _|  ___|_ _  ___| |_ ___  _ __ _   _
| |   | | | | | | | |_ / _` |/ __| __/ _ \| '__| | | |
| |___| |_| | | | |  _| (_| | (__| || (_) | |  | |_| |
|_____|\___/  |_| |_|  \__,_|\___|\__\___/|_|   \__, |
                                                |___/
"""


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="lutfactory",
        description="Generate graded camera and Resolve .cube LUTs from RGB identity charts.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--version", action="version", version=f"LUTFactory {__version__}")
    p.add_argument("--no-color", action="store_true", help="Disable ANSI styling")
    commands = p.add_subparsers(dest="command", required=True)

    chart = commands.add_parser("chart", help="Create a 16-bit RGB identity TIFF")
    chart.add_argument("--size", type=int, choices=(33, 65), default=33)
    chart.add_argument("--output", type=Path)

    build = commands.add_parser("build", help="Convert graded TIFF to camera and Resolve .cube files")
    build.add_argument("input", type=Path, help="Full-range RGB 16-bit graded TIFF")
    build.add_argument("--name", default="MyLook", help="Output filename prefix")
    build.add_argument("--output-dir", type=Path, default=Path("dist"))
    build.add_argument("--camera-size", type=int, choices=(17, 33), default=33)
    build.add_argument("--resolve-size", type=int, choices=(33, 65), default=65)
    build.add_argument("--input-space", default="Unspecified", help="Descriptive .cube metadata only")
    build.add_argument("--output-space", default="Unspecified", help="Descriptive .cube metadata only")
    build.add_argument("--strict", action="store_true", help="Reject nonuniform chart patches")
    build.add_argument("--threshold", type=float, default=0.003)

    validate = commands.add_parser("validate", help="Validate an identity or graded TIFF chart")
    validate.add_argument("input", type=Path)
    validate.add_argument("--identity", action="store_true", help="Check source chart is ungraded")
    validate.add_argument("--threshold", type=float, default=0.003)

    inspect = commands.add_parser("inspect", help="Validate and summarize a .cube file")
    inspect.add_argument("input", type=Path)
    return p


def show_banner(console: Console) -> None:
    title = Text(BANNER.strip("\n"), style="bold bright_cyan")
    title.append("\n  CAMERA + EDITING LUT TOOLKIT", style="bold magenta")
    title.append("\n  Developed by h4rithd with the help of AI", style="dim")
    console.print(Panel(title, border_style="bright_blue", expand=False))


def show_patch_check(console: Console, error: float, count: int, threshold: float) -> None:
    if error > threshold:
        console.print(
            f"[yellow]WARNING[/] Patch neighbors differ: max={error:.6f}; "
            f"affected={count:,}. Check image scaling or spatial effects."
        )
    else:
        console.print(f"[green]PASS[/] Patch consistency: max error={error:.6f}")


def cmd_chart(args: argparse.Namespace, console: Console) -> int:
    spec = spec_for_size(args.size)
    path = args.output or Path(f"LUTFactory_Identity_{spec.size}.tif")
    save_atlas(path, spec.size)
    console.print(f"[green]CREATED[/] {path.resolve()}")
    console.print(
        f"[cyan]CHART[/] {spec.width}x{spec.height} | RGB16 | "
        f"{spec.count:,} samples | patch={spec.patch}px"
    )
    console.print("[dim]Grade and export one full-range RGB16 TIFF frame without resizing.[/]")
    return 0


def cmd_build(args: argparse.Namespace, console: Console) -> int:
    if not 0 <= args.threshold <= 1:
        raise ValueError("--threshold must be in 0..1")
    image, spec = load_atlas(args.input)
    samples, report = extract_samples(image, spec)
    show_patch_check(console, report.max_neighbor_error, report.affected_patches, args.threshold)
    if args.strict and report.max_neighbor_error > args.threshold:
        raise ValueError("Spatial patch consistency check failed (--strict)")
    name = safe_stem(args.name)
    table = Table(title="Generated 3D LUTs", header_style="bold cyan")
    table.add_column("Target", style="bold magenta")
    table.add_column("Samples")
    table.add_column("Sampling")
    table.add_column("File", overflow="fold")
    for label, size in (("CAMERA", args.camera_size), ("RESOLVE", args.resolve_size)):
        values = resize_cube(samples, spec.size, size)
        output = args.output_dir / f"{name}_{label}_{size}.cube"
        write_cube(output, values, size, f"{name}_{label}_{size}", spec.size,
                   args.input_space, args.output_space)
        method = "direct" if spec.size == size else ("interpolated" if size > spec.size else "subset")
        table.add_row(label, f"{size}³ ({size**3:,})", method, str(output))
    console.print(table)
    if args.resolve_size > spec.size:
        console.print("[yellow]NOTE[/] The Resolve LUT is interpolated from fewer measured points.")
    console.print("[green]DONE[/] Compare both LUTs against your original color grade.")
    return 0


def cmd_validate(args: argparse.Namespace, console: Console) -> int:
    if not 0 <= args.threshold <= 1:
        raise ValueError("--threshold must be in 0..1")
    image, spec = load_atlas(args.input)
    samples, report = extract_samples(image, spec)
    console.print(f"[cyan]CHART[/] {spec.size}³ | {spec.width}x{spec.height} | RGB16")
    show_patch_check(console, report.max_neighbor_error, report.affected_patches, args.threshold)
    error = report.max_neighbor_error
    if args.identity:
        delta = np.abs(samples - identity_samples(spec.size))
        error = max(error, float(delta.max()))
        console.print(f"[cyan]IDENTITY[/] max delta={float(delta.max()):.8f}")
    if error > args.threshold:
        console.print("[red]FAIL[/] Validation exceeds threshold")
        return 2
    console.print("[green]PASS[/]")
    return 0


def cmd_inspect(args: argparse.Namespace, console: Console) -> int:
    size, data = read_cube(args.input)
    table = Table(title=".cube Inspection", header_style="bold cyan")
    table.add_column("Property", style="magenta")
    table.add_column("Value")
    table.add_row("File", str(args.input))
    table.add_row("LUT grid", f"{size}³")
    table.add_row("RGB samples", f"{len(data):,}")
    table.add_row("Min RGB", ", ".join(f"{x:.6f}" for x in data.min(axis=0)))
    table.add_row("Max RGB", ", ".join(f"{x:.6f}" for x in data.max(axis=0)))
    console.print(table)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    console = Console(no_color=args.no_color, highlight=False)
    show_banner(console)
    try:
        return {
            "chart": cmd_chart, "build": cmd_build,
            "validate": cmd_validate, "inspect": cmd_inspect,
        }[args.command](args, console)
    except (ValueError, OSError) as exc:
        console.print(f"[bold red]ERROR[/] {exc}")
        return 1
