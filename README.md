# Prusa CLI Preview

`slice-with-preview` wraps PrusaSlicer 2.9.x CLI slicing and adds the printer
preview images that plain CLI exports omit. It renders the model offscreen,
embeds every thumbnail requested by the selected printer preset, converts the
result with Prusa's `libbgcode`, and validates checksums, block structure,
thumbnail dimensions, and thumbnail formats.

Preview rendering uses PrusaSlicer's default isometric build-plate convention:
the model keeps its sliced XYZ orientation, with world Z vertical in the image.

## Install

This repository is self-contained: it does not need Aquarium, CadKit, Fitkit,
or any other design project. It is tested on Linux with the stable PrusaSlicer
Flatpak.

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) and the
two system prerequisites first:

```bash
flatpak install flathub com.prusa3d.PrusaSlicer
# Install ImageMagick with your operating system's package manager.
```

Open PrusaSlicer once to create its configuration directory and add the
printer and filament presets you intend to use. Then install the Python tool:

```bash
git clone https://github.com/benredrew/prusa-cli-preview.git
cd prusa-cli-preview
uv sync
uv run slice-with-preview --doctor
```

`--doctor` checks the PrusaSlicer version, its configuration directory, and
ImageMagick before any model is sliced. It reports every missing prerequisite
without touching a model or removable drive.

## Usage

```bash
uv run slice-with-preview model.step \
  --printer "Original Prusa MINI & MINI+ Input Shaper" \
  --filament DogPLA \
  --perimeters 5 \
  --output model.bgcode
```

The standard print profile is `0.20mm STRUCTURAL @MINIIS 0.4`. Pass
`--print-profile` to select a different PrusaSlicer print preset.
Use `--supports grid`, `--supports snug`, or `--supports organic` to enable
automatic support generation in the selected style.

Use `--copy-to-usb LABEL --unmount` for a verified removable-drive copy and
safe unmount. Existing output files are protected unless `--force` is passed.
Run `slice-with-preview --help` for all options.

## Machine integration

`uv sync` creates an isolated `.venv` in this checkout and uses the pinned
versions in `uv.lock`. Run commands through `uv run` from the checkout, so
there is no hidden user-wide installation path.

Both agent systems use the same canonical skill instructions:

```text
~/.agents/skills/slice-with-preview -> skills/slice-with-preview
~/.claude/skills/slice-with-preview -> skills/slice-with-preview
```

Runtime prerequisites are the stable PrusaSlicer Flatpak and ImageMagick's
`magick` command. PrusaSlicer preset names and configuration come from the
user's normal Flatpak data directory; pass `--datadir` to use another one.

## Verification

```bash
uv run python -m unittest discover -s tests -v
```
