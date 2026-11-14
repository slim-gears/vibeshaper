---
name: vibeshaper-dsl
description: >-
  Generate, edit, or validate VibeShaper Fusion 360 CAD DSL JSON designs (parametric parts,
  multi-component assemblies, standard hardware shapes, and BOMs). Use when the user asks to
  create or modify a VibeShaper JSON design.
---

# VibeShaper DSL JSON Generator

Generate valid, parametric VibeShaper CAD DSL JSON by consulting the live specification rather than relying on memorized schema details.

## Authoritative Specification

Always fetch the latest spec before authoring or reviewing DSL JSON:

- **Live DSL Spec (GitHub raw):** `https://raw.githubusercontent.com/slim-gears/vibeshaper/main/DSL_SPEC.md`
- If working inside a local `VibeShaper` checkout, you may read `DSL_SPEC.md` directly (it matches the live spec).

## Workflow

1. **Read the spec first:** Fetch `https://raw.githubusercontent.com/slim-gears/vibeshaper/main/DSL_SPEC.md` (or local `DSL_SPEC.md`) to check the current top-level keys, feature `"op"`s, sketch entity types, shape macros, coordinate conventions, and BOM rules.
2. **Design parametrically:**
   - Put key dimensions and counts in `"parameters"` with explicit units (e.g. `"40 mm"`, `"4"`).
   - Keep `"timeline"` steps minimal and ordered cleanly; prefer documented shape `"op"`s (fastener holes, gears, motors, rails, profiles, etc.) over hand-drawn geometry where appropriate.
   - For multi-part designs, define each part in `"components"` and position them via `"instances"` rather than building everything in the root timeline.
3. **Include BOM metadata when helpful:**
   - Set `"material"` on custom `"components"`.
   - On `bolt_hole` joints, add `"screw"` on **one side of the joint only** to avoid double-counting fasteners.
   - Add explicit `"bom"` entries (with `"whole": true` if a component represents a purchased part) when needed.
4. **Validate before returning:**
   - Ensure the output is strict JSON (no comments, no trailing commas).
   - If a local `VibeShaper` checkout and Python are available, validate the JSON offline with `dsl.validate(data)` and `bom.collect(data)`.
5. **Present the result:** Output clean, ready-to-paste JSON for the VibeShaper panel in Fusion 360.
