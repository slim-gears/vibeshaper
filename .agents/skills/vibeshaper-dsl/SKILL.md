---
name: vibeshaper-dsl
description: >-
  Generate, edit, or validate VibeShaper Fusion 360 CAD DSL JSON designs (parametric parts,
  multi-component assemblies, standard hardware shapes, and BOMs). Use when the user asks to
  create or modify a VibeShaper JSON design.
---

# VibeShaper DSL JSON Generator

Generate valid, parametric VibeShaper CAD DSL JSON directly from `DSL_SPEC.md`, whose Sketch Entities, Timeline Operations, and Shape plugin sections are auto-generated from the live plugins.

## Authoritative Specification (Self-Contained)

- **Local checkout (preferred when inside the repo):** `VibeShaper/DSL_SPEC.md`
- **Live DSL Spec (GitHub raw, when outside the repo):** `https://raw.githubusercontent.com/slim-gears/vibeshaper/main/DSL_SPEC.md`

> **Do NOT explore source or unrelated files:** `DSL_SPEC.md` is auto-generated from all registered `features/`, `features/entities/`, and `shapes/` plugins and is 100% self-contained (including every shape macro's keys, presets, coordinate frame, and edge selector options). Do **not** list directories or read `VibeShaper/*.py`, `features/*.py`, `shapes/*.py`, `examples/*.json`, or unrelated `.json` files in the workspace unless the user explicitly asks to inspect or edit them.

## Workflow

1. **Read `DSL_SPEC.md` once:** Read local `VibeShaper/DSL_SPEC.md` (or fetch `https://raw.githubusercontent.com/slim-gears/vibeshaper/main/DSL_SPEC.md` if outside the repo) to check the top-level keys, feature `"op"`s, sketch entity types, shape macros, coordinate conventions, and BOM rules.
2. **Design parametrically:**
   - Put every meaningful dimension and count in `"parameters"` with explicit units (`"40 mm"`, `"45 deg"`, `"4"`).
   - Keep `"timeline"` steps minimal and ordered cleanly; prefer documented shape `"op"`s (`bolt_hole`, `vent_grid`, `spur_gear`, `tslot_profile`, bought parts) over hand-drawn geometry where appropriate.
   - For multi-part designs (e.g. a box and lid, or an assembly), define each part in `"components"` and position them via `"instances"` rather than building everything in the root timeline.
3. **Include BOM metadata when helpful:**
   - Set `"material"` on custom fabricated `"components"`.
   - On `bolt_hole` joints, add `"screw"` on **one side of the joint only** to avoid double-counting fasteners.
   - Add explicit `"bom"` entries (with `"whole": true` if a component represents a purchased part) when needed.
4. **Validate via CLI (never by reading Python code):**
   - Ensure the output is strict JSON (no comments, no trailing commas).
   - If a local `VibeShaper` checkout and Python are available, run a single validation command on your generated JSON:
     ```powershell
     python -c "import sys, json; sys.path.insert(0, 'VibeShaper'); import dsl, bom; d = json.load(open('design.json', encoding='utf-8')); dsl.validate(d); bom.collect(d); print('ok')"
     ```
5. **Present the result:** Save the `.json` file if requested and output clean, ready-to-paste JSON for the VibeShaper panel in Fusion 360.
