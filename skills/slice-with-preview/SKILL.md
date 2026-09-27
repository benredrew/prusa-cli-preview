---
name: slice-with-preview
description: Slice FFF models with PrusaSlicer CLI while embedding printer preview thumbnails in validated BG-code. Use for Prusa printer slicing, previewless CLI output, and optional verified USB export.
---

# Slice with preview

Use `uv run slice-with-preview` from an installed Prusa CLI Preview checkout.
Do not recreate its thumbnail or BG-code logic in a project.

Require the model path plus exact PrusaSlicer printer and filament preset names. The standard print profile is `0.20mm STRUCTURAL @MINIIS 0.4`; preserve a different print profile when the user specifies one. If a material or printer choice is missing and cannot be established from the active PrusaSlicer presets, ask before slicing.

Example:

```bash
uv run slice-with-preview model.step \
  --printer "Original Prusa MINI & MINI+ Input Shaper" \
  --filament DogPLA \
  --perimeters 5 \
  --output model.bgcode \
  --copy-to-usb LABEL \
  --unmount
```

The command refuses to overwrite files unless `--force` is supplied. Use `--supports grid`, `--supports snug`, or `--supports organic` when the user requests automatically generated supports in that style. Add `--copy-to-usb LABEL` only when the user requests removable-media export; when copying to USB, also add `--unmount` so the verified copy is safely unmounted at the end. USB operations remain subject to the agent host's normal permission approval.

Treat success as all of the following: PrusaSlicer completed, the BG-code checksum and block sequence validate, every requested thumbnail is present at the expected dimensions, and any requested USB copy matches byte-for-byte.

Use this completion summary, in this order:

- Printer: resolved PrusaSlicer printer preset.
- File: output filename or path.
- Filament: resolved PrusaSlicer filament preset.
- Estimated print time: from PrusaSlicer.
- Print cost: from the validated BG-code's total filament-cost metadata, using the filament preset's configured currency; say `not configured` if absent.
- Print mass: from PrusaSlicer's total filament use in grams.
- External dimensions: `X × Y × Z mm` from the model bounds, excluding a brim, skirt, or supports.

Then report the thumbnail set, validation result, verified USB-copy result when requested, and USB unmount status. Do not substitute filament length or volume for print mass, and do not infer cost from mass.

Run `slice-with-preview --help` for available flags.
