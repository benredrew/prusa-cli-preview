from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

import pybgcode
import vtk


DEFAULT_APP = "com.prusa3d.PrusaSlicer"
DEFAULT_BRANCH = "stable"
DEFAULT_DATADIR = (
    Path.home()
    / ".var/app/com.prusa3d.PrusaSlicer/config/PrusaSlicer"
)
THUMBNAIL_RE = re.compile(
    r"(?P<width>\d+)x(?P<height>\d+)(?:/(?P<format>PNG|JPG|QOI))?",
    re.IGNORECASE,
)


class ToolError(RuntimeError):
    pass


@dataclass(frozen=True)
class ThumbnailSpec:
    width: int
    height: int
    format: str


def command_text(parts: list[str]) -> str:
    return " ".join(parts)


def run(parts: list[str], *, capture: bool = False) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            parts,
            check=True,
            text=True,
            stdout=subprocess.PIPE if capture else None,
            stderr=subprocess.STDOUT if capture else None,
        )
    except FileNotFoundError as exc:
        raise ToolError(f"required command not found: {parts[0]}") from exc
    except subprocess.CalledProcessError as exc:
        detail = f"\n{exc.stdout.strip()}" if capture and exc.stdout else ""
        raise ToolError(f"command failed: {command_text(parts)}{detail}") from exc


def prusa_command(args: argparse.Namespace) -> list[str]:
    return [
        "flatpak",
        "run",
        f"--branch={args.prusa_branch}",
        "--command=prusa-slicer",
        args.prusa_app,
    ]


def profile_args(args: argparse.Namespace) -> list[str]:
    return [
        "--no-single-instance",
        "--datadir",
        str(args.datadir),
        "--printer-profile",
        args.printer,
        "--print-profile",
        args.print_profile,
        "--material-profile",
        args.filament,
    ]


def check_prusa_version(args: argparse.Namespace) -> str:
    # The 2.9 Flatpak prints its version for --version but exits nonzero because
    # that flag is not formally supported. Its successful --help banner starts
    # with the same version string.
    result = run(prusa_command(args) + ["--help"], capture=True)
    match = re.search(r"PrusaSlicer-(\d+\.\d+\.\d+)", result.stdout)
    if not match:
        raise ToolError(f"could not identify PrusaSlicer version from: {result.stdout.strip()}")
    version = match.group(1)
    if args.require_version and not version.startswith(args.require_version + "."):
        raise ToolError(
            f"PrusaSlicer {version} does not match required series "
            f"{args.require_version}.x"
        )
    return version


def export_ascii_gcode(
    model: Path, destination: Path, args: argparse.Namespace
) -> None:
    cmd = prusa_command(args) + profile_args(args)
    if args.perimeters is not None:
        cmd += ["--perimeters", str(args.perimeters)]
    cmd += [
        "--no-binary-gcode",
        "--export-gcode",
        "--output",
        str(destination),
        str(model),
    ]
    run(cmd)
    if not destination.is_file() or destination.stat().st_size == 0:
        raise ToolError("PrusaSlicer did not create ASCII G-code")


def export_stl(model: Path, destination: Path, args: argparse.Namespace) -> None:
    cmd = prusa_command(args) + profile_args(args) + [
        "--export-stl",
        "--output",
        str(destination),
        str(model),
    ]
    run(cmd)
    if not destination.is_file() or destination.stat().st_size == 0:
        raise ToolError("PrusaSlicer did not create the temporary STL")


def config_value(gcode: str, key: str) -> str | None:
    pattern = re.compile(rf"^;\s*{re.escape(key)}\s*=\s*(.*?)\s*$", re.MULTILINE)
    matches = pattern.findall(gcode)
    return matches[-1] if matches else None


def parse_thumbnail_specs(gcode: str, override: str | None = None) -> list[ThumbnailSpec]:
    raw = override or config_value(gcode, "thumbnails")
    fallback = (config_value(gcode, "thumbnails_format") or "PNG").upper()
    if not raw:
        raise ToolError(
            "the selected printer profile defines no thumbnails; pass "
            "--thumbnails with values such as 220x124/QOI,380x285/PNG"
        )
    specs = [
        ThumbnailSpec(
            int(match.group("width")),
            int(match.group("height")),
            (match.group("format") or fallback).upper(),
        )
        for match in THUMBNAIL_RE.finditer(raw)
    ]
    if not specs:
        raise ToolError(f"invalid thumbnail specification: {raw}")
    for spec in specs:
        if spec.width < 1 or spec.height < 1 or spec.width > 2000 or spec.height > 2000:
            raise ToolError(f"unsafe thumbnail dimensions: {spec.width}x{spec.height}")
    return specs


def render_png(stl: Path, output: Path, width: int, height: int) -> None:
    reader = vtk.vtkSTLReader()
    reader.SetFileName(str(stl))
    reader.Update()
    mesh = reader.GetOutput()
    if mesh.GetNumberOfPoints() == 0:
        raise ToolError("temporary STL contains no renderable geometry")

    normals = vtk.vtkPolyDataNormals()
    normals.SetInputData(mesh)
    normals.SetFeatureAngle(35.0)
    normals.SplittingOn()
    normals.ConsistencyOn()

    mapper = vtk.vtkPolyDataMapper()
    mapper.SetInputConnection(normals.GetOutputPort())
    actor = vtk.vtkActor()
    actor.SetMapper(mapper)
    actor.GetProperty().SetColor(0.93, 0.52, 0.12)
    actor.GetProperty().SetAmbient(0.22)
    actor.GetProperty().SetDiffuse(0.78)
    actor.GetProperty().SetSpecular(0.18)
    actor.GetProperty().SetSpecularPower(24.0)

    renderer = vtk.vtkRenderer()
    renderer.SetBackground(0.08, 0.09, 0.11)
    renderer.SetBackgroundAlpha(0.0)
    renderer.AddActor(actor)

    window = vtk.vtkRenderWindow()
    window.SetOffScreenRendering(1)
    window.SetAlphaBitPlanes(1)
    window.SetMultiSamples(4)
    window.SetSize(width, height)
    window.AddRenderer(renderer)

    renderer.ResetCamera()
    camera = renderer.GetActiveCamera()
    camera.Azimuth(35.0)
    camera.Elevation(25.0)
    camera.OrthogonalizeViewUp()
    camera.Zoom(1.18)
    renderer.ResetCameraClippingRange()
    window.Render()

    capture = vtk.vtkWindowToImageFilter()
    capture.SetInput(window)
    capture.SetInputBufferTypeToRGBA()
    capture.ReadFrontBufferOff()
    capture.Update()

    pixels = capture.GetOutput().GetPointData().GetScalars()
    if pixels is None or pixels.GetNumberOfTuples() == 0:
        raise ToolError("VTK produced an empty preview image")
    color_components = min(3, pixels.GetNumberOfComponents())
    contrast = max(
        pixels.GetRange(component)[1] - pixels.GetRange(component)[0]
        for component in range(color_components)
    )
    if contrast < 8:
        raise ToolError("VTK produced a blank preview image")

    writer = vtk.vtkPNGWriter()
    writer.SetFileName(str(output))
    writer.SetInputConnection(capture.GetOutputPort())
    writer.Write()
    window.Finalize()
    if not output.is_file() or output.stat().st_size == 0:
        raise ToolError("VTK did not create the preview image")


def encode_thumbnail(png: Path, spec: ThumbnailSpec, output: Path) -> None:
    if spec.format == "PNG":
        if png != output:
            shutil.copyfile(png, output)
        return
    target_format = "JPEG" if spec.format == "JPG" else spec.format
    run(["magick", str(png), f"{target_format}:{output}"])
    if not output.is_file() or output.stat().st_size == 0:
        raise ToolError(f"ImageMagick did not create {spec.format} thumbnail")


def thumbnail_block(spec: ThumbnailSpec, data: bytes) -> str:
    encoded = base64.b64encode(data).decode("ascii")
    marker = "thumbnail" if spec.format == "PNG" else f"thumbnail_{spec.format}"
    rows = "\n".join(f"; {encoded[i:i + 78]}" for i in range(0, len(encoded), 78))
    return (
        f";\n; {marker} begin {spec.width}x{spec.height} {len(encoded)}\n"
        f"{rows}\n"
        f"; {marker} end\n;"
    )


def inject_thumbnails(gcode: str, blocks: list[str]) -> str:
    insertion = "\n\n".join(blocks)
    first_newline = gcode.find("\n")
    if first_newline < 0 or not gcode.startswith("; generated by PrusaSlicer"):
        raise ToolError("ASCII G-code lacks the expected PrusaSlicer producer header")
    return gcode[: first_newline + 1] + "\n" + insertion + "\n\n" + gcode[first_newline + 1 :]


def convert_to_bgcode(ascii_path: Path, output: Path) -> None:
    source = pybgcode.open(str(ascii_path), "r")
    target = pybgcode.open(str(output), "wb")
    try:
        result = pybgcode.from_ascii_to_binary(source, target, pybgcode.get_config())
    finally:
        pybgcode.close(target)
        pybgcode.close(source)
    if result != pybgcode.EResult.Success:
        raise ToolError(f"BG-code conversion failed: {pybgcode.translate_result(result)}")


def validate_bgcode(path: Path, specs: list[ThumbnailSpec]) -> dict[str, str]:
    wrapper = pybgcode.open(str(path), "rb")
    try:
        # pybgcode 0.3.0 builds this official binding but accidentally omits it
        # from the package-level re-exports.
        result = pybgcode._bgcode.is_valid_binary_gcode(wrapper, True)
        if result != pybgcode.EResult.Success:
            raise ToolError(f"invalid BG-code: {pybgcode.translate_result(result)}")
        thumbs = pybgcode.read_thumbnails(wrapper)
        format_names = {
            int(pybgcode.EThumbnailFormat.PNG): "PNG",
            int(pybgcode.EThumbnailFormat.JPG): "JPG",
            int(pybgcode.EThumbnailFormat.QOI): "QOI",
        }
        actual = [
            (
                item["meta"].width,
                item["meta"].height,
                format_names.get(int(item["meta"].format), "UNKNOWN"),
            )
            for item in thumbs
        ]
        expected = [(item.width, item.height, item.format) for item in specs]
        if actual != expected:
            raise ToolError(f"thumbnail validation failed: expected {expected}, found {actual}")
        metadata = pybgcode.read_metadata(wrapper) or {}
    finally:
        pybgcode.close(wrapper)
    return {str(key): str(value) for key, value in metadata.items()}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def block_devices() -> list[dict]:
    result = run(
        ["lsblk", "--json", "--output", "NAME,LABEL,TYPE,MOUNTPOINTS"],
        capture=True,
    )
    data = json.loads(result.stdout)
    found: list[dict] = []

    def visit(device: dict) -> None:
        found.append(device)
        for child in device.get("children") or []:
            visit(child)

    for device in data.get("blockdevices", []):
        visit(device)
    return found


def find_usb(label: str) -> tuple[str, Path | None]:
    matches = [item for item in block_devices() if item.get("label") == label]
    if len(matches) != 1:
        raise ToolError(f"expected one block device labelled {label!r}, found {len(matches)}")
    item = matches[0]
    mountpoints = [value for value in item.get("mountpoints") or [] if value]
    return f"/dev/{item['name']}", Path(mountpoints[0]) if mountpoints else None


def copy_to_usb(source: Path, label: str, *, unmount: bool, force: bool) -> Path:
    device, mountpoint = find_usb(label)
    if mountpoint is None:
        run(["udisksctl", "mount", "-b", device])
        device, mountpoint = find_usb(label)
    if mountpoint is None:
        raise ToolError(f"device {device} did not mount")
    destination = mountpoint / source.name
    if destination.exists() and not force:
        raise ToolError(f"USB destination exists; use --force to replace it: {destination}")
    shutil.copy2(source, destination)
    with destination.open("rb") as stream:
        os.fsync(stream.fileno())
    if sha256(source) != sha256(destination):
        raise ToolError("USB verification failed")
    if unmount:
        run(["udisksctl", "unmount", "-b", device])
    return destination


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        prog="slice-with-preview",
        description="Slice a model with PrusaSlicer CLI and embed validated previews.",
    )
    result.add_argument("model", type=Path)
    result.add_argument("--printer", required=True, help="PrusaSlicer printer preset")
    result.add_argument("--print-profile", required=True, help="PrusaSlicer print preset")
    result.add_argument("--filament", required=True, help="PrusaSlicer filament preset")
    result.add_argument("--perimeters", type=int)
    result.add_argument("--output", type=Path)
    result.add_argument("--thumbnails", help="override profile thumbnail sizes/formats")
    result.add_argument("--datadir", type=Path, default=DEFAULT_DATADIR)
    result.add_argument("--prusa-app", default=DEFAULT_APP)
    result.add_argument("--prusa-branch", default=DEFAULT_BRANCH)
    result.add_argument("--require-version", default="2.9")
    result.add_argument("--keep-ascii", action="store_true")
    result.add_argument("--copy-to-usb", metavar="LABEL")
    result.add_argument("--unmount", action="store_true")
    result.add_argument("--force", action="store_true")
    return result


def execute(args: argparse.Namespace) -> None:
    model = args.model.expanduser().resolve()
    args.datadir = args.datadir.expanduser().resolve()
    if not model.is_file():
        raise ToolError(f"model does not exist: {model}")
    if args.perimeters is not None and args.perimeters < 1:
        raise ToolError("--perimeters must be at least 1")
    if args.unmount and not args.copy_to_usb:
        raise ToolError("--unmount requires --copy-to-usb LABEL")
    if not args.datadir.is_dir():
        raise ToolError(f"PrusaSlicer data directory does not exist: {args.datadir}")

    output = (
        args.output.expanduser().resolve()
        if args.output
        else model.with_suffix(".bgcode")
    )
    if output.suffix.lower() != ".bgcode":
        raise ToolError("output filename must end in .bgcode")
    if output.exists() and not args.force:
        raise ToolError(f"output exists; use --force to replace it: {output}")
    ascii_output = output.with_suffix(".gcode")
    if args.keep_ascii and ascii_output.exists() and not args.force:
        raise ToolError(f"ASCII output exists; use --force: {ascii_output}")
    output.parent.mkdir(parents=True, exist_ok=True)

    version = check_prusa_version(args)
    cache = Path.home() / ".cache/slice-with-preview"
    cache.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="job-", dir=cache) as temp_name:
        temp = Path(temp_name)
        ascii_path = temp / "sliced.gcode"
        stl_path = temp / "model.stl"
        injected_path = temp / "with-thumbnails.gcode"
        bgcode_path = temp / "result.bgcode"

        export_ascii_gcode(model, ascii_path, args)
        gcode = ascii_path.read_text(encoding="utf-8", errors="strict")
        specs = parse_thumbnail_specs(gcode, args.thumbnails)
        export_stl(model, stl_path, args)

        blocks: list[str] = []
        for index, spec in enumerate(specs):
            png = temp / f"preview-{index}.png"
            encoded = temp / f"preview-{index}.{spec.format.lower()}"
            render_png(stl_path, png, spec.width, spec.height)
            encode_thumbnail(png, spec, encoded)
            blocks.append(thumbnail_block(spec, encoded.read_bytes()))

        injected_path.write_text(
            inject_thumbnails(gcode, blocks), encoding="utf-8", newline="\n"
        )
        convert_to_bgcode(injected_path, bgcode_path)
        metadata = validate_bgcode(bgcode_path, specs)
        os.replace(bgcode_path, output)

        if args.keep_ascii:
            shutil.copy2(injected_path, ascii_output)

    print(f"PrusaSlicer: {version}")
    print(f"Printer: {args.printer}")
    print(f"Print profile: {args.print_profile}")
    print(f"Filament: {args.filament}")
    if args.perimeters is not None:
        print(f"Perimeters: {args.perimeters}")
    print(
        "Thumbnails: "
        + ", ".join(f"{item.width}x{item.height}/{item.format}" for item in specs)
    )
    if "estimated printing time (normal mode)" in metadata:
        print(f"Estimated time: {metadata['estimated printing time (normal mode)']}")
    if "filament used [g]" in metadata:
        print(f"Filament used: {metadata['filament used [g]']} g")
    print(f"Validated BG-code: {output}")

    if args.copy_to_usb:
        destination = copy_to_usb(
            output,
            args.copy_to_usb,
            unmount=args.unmount,
            force=args.force,
        )
        print(f"Verified USB copy: {destination}")
        if args.unmount:
            print(f"Unmounted USB device labelled {args.copy_to_usb}")


def main() -> None:
    try:
        execute(parser().parse_args())
    except ToolError as exc:
        print(f"slice-with-preview: error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()
