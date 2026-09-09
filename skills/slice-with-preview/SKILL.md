---
name: slice-with-preview
description: Slice FFF models with PrusaSlicer CLI while embedding printer preview thumbnails in validated BG-code. Use for Prusa printer slicing, previewless CLI output, and optional verified USB export.
---

# Slice with preview

Use the user-wide `slice-with-preview` command. Do not recreate its thumbnail or BG-code logic in a project.

Require the model path plus exact PrusaSlicer printer, print, and filament preset names. Preserve settings the user specifies. If a material or printer choice is missing and cannot be established from the active PrusaSlicer presets, ask before slicing.

Example:

```bash
slice-with-preview model.step \
  --printer "Original Prusa MINI & MINI+ Input Shaper" \
  --print-profile "0.20mm SPEED @MINIIS 0.4" \
  --filament DogPLA \
  --perimeters 5 \
  --output model.bgcode
```

The command refuses to overwrite files unless `--force` is supplied. Add `--copy-to-usb LABEL` only when the user requests removable-media export. Add `--unmount` only when the user asks to unmount or safely remove it. USB operations remain subject to the agent host's normal permission approval.

Treat success as all of the following: PrusaSlicer completed, the BG-code checksum and block sequence validate, every requested thumbnail is present at the expected dimensions, and any requested USB copy matches byte-for-byte. Report the resolved PrusaSlicer version, profiles, thumbnail set, output path, and USB unmount status.

Run `slice-with-preview --help` for available flags.
