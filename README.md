# Prusa CLI Preview

`slice-with-preview` wraps PrusaSlicer 2.9.x CLI slicing and adds the printer
preview images that plain CLI exports omit. It renders the model offscreen,
embeds every thumbnail requested by the selected printer preset, converts the
result with Prusa's `libbgcode`, and validates checksums, block structure,
thumbnail dimensions, and thumbnail formats.

Preview rendering uses PrusaSlicer's default isometric build-plate convention:
the model keeps its sliced XYZ orientation, with world Z vertical in the image.

The command is installed user-wide at:

```text
~/.local/bin/slice-with-preview
```

## Usage

```bash
slice-with-preview model.step \
  --printer "Original Prusa MINI & MINI+ Input Shaper" \
  --print-profile "0.20mm SPEED @MINIIS 0.4" \
  --filament DogPLA \
  --perimeters 5 \
  --output model.bgcode
```

Use `--copy-to-usb LABEL --unmount` for a verified removable-drive copy and
safe unmount. Existing output files are protected unless `--force` is passed.
Run `slice-with-preview --help` for all options.

## Machine integration

The isolated runtime is in `~/.local/share/prusa-cli-preview/.venv`. Its package
is installed editable from this repository, so source changes take effect in
the global command immediately. Dependencies are pinned in `uv.lock`.

Both agent systems use the same canonical skill instructions:

```text
~/.agents/skills/slice-with-preview -> skills/slice-with-preview
~/.claude/skills/slice-with-preview -> skills/slice-with-preview
```

Runtime prerequisites are the stable PrusaSlicer Flatpak and ImageMagick's
`magick` command. PrusaSlicer preset names and configuration come from the
user's normal Flatpak data directory.

## Verification

```bash
~/.local/share/prusa-cli-preview/.venv/bin/python -m unittest discover -s tests -v
python3 ~/.codex/skills/.system/skill-creator/scripts/quick_validate.py \
  skills/slice-with-preview
```
