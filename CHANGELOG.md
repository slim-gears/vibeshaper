# Changelog

All notable changes to VibeShaper (called PromptCAD up to 0.2.0). The format follows [Keep a Changelog](https://keepachangelog.com/), and versions follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.9.0]

### Added
- **Loft feature (`loft`) and 3D sketches (`"plane": "3d"`).** Added the `loft` timeline operation (blending 2+ cross-section sketches with optional guide `"rails"`, `"centerline"`, and `"closed"` loop support) and `"plane": "3d"` sketches for `line`, `polyline`, `spline`, and `profile` curves using 3D world coordinates `[x, y, z]`.
- **Zero-config web search & page reading (`tools/web.py`).** Added `web_search` (DuckDuckGo Lite + Wikipedia fallback) and `fetch_web_page` so models can look up real-world object dimensions, datasheets, and mounting hole spacings, running off the main thread so network I/O never blocks Fusion's UI.
- **Viewport screenshot capture (`tools/view.py`).** Added `capture_viewport` (`needs = ('images',)`), allowing vision-capable models to render and inspect 1–4 camera views (`"iso"`, `"front"`, `"back"`, `"top"`, `"bottom"`, `"left"`, `"right"`, `"current"`) with multimodal tool results in both Ollama and Gemini.
- **Real-time tool call logging.** Tool calls and results are now logged immediately to `vibeshaper.log` as they execute, and summarized under `--- TOOLS ---` in the transcript.

### Fixed
- **Tools offered before opening the model menu.** Starting a turn before opening the model dropdown now defaults to offering tool-calling toolkits (with automatic retry without tools if an older Ollama model rejects them).
- **Tool summary label in the chat panel.** The collapsed tool pill in `palette/app.js` now displays the actual tool labels (`Searched the web for “…”`, `Captured viewport (…)`, etc.) instead of always saying `"Looked at your design"`.
- **Parameter expressions validated before building.** `dsl.validate()` now evaluates parameter expressions with `bom.Evaluator` so non-numeric strings or undefined parameter references are caught immediately in the LLM validation loop.
- **Removed mock backend from production palette code.** Extracted `MockBackend` and standalone mock fallbacks out of `palette/app.js` and `palette/bom.html`, and added a cross-platform Node.js test suite for `palette/app.js` in `test_dsl.py`.

## [0.8.0]

### Added
- **Fitted spline curves (`spline` and `profile` `"spline"` segments).** Added the `spline` sketch entity (open or closed periodic splines) and `"spline"` intermediate fit-point segments inside `profile`, dimensioned parametrically on every fit point and reported by `design.inspect_sketch`.
- **`"offset"` support on 3D `mirror`.** `mirror` steps now accept an optional `"offset"` distance on base planes (`"xy"`, `"xz"`, `"yz"`), and `tslot_profile` now extrudes one quadrant and completes the profile in 3D via native `mirror` features.
- **Auto-generated plugin reference in `DSL_SPEC.md`.** `dsl.sync_spec()` keeps Sections 4 and 5 of `DSL_SPEC.md` synchronized with live feature, sketch entity, and shape plugin `.prompt` specifications whenever `test_dsl.py` runs.

### Fixed
- **Stopping a build in progress.** Clicking **Stop** during geometry generation now immediately aborts remaining steps and rolls back the partial Fusion 360 transaction (including restoring any prior version replaced by a modification build).
- **Bill of Materials palette startup handshake.** Opening the Bill of Materials window for the first time in a session now waits for Fusion's asynchronous `window.adsk` bridge injection before sending `bom_ready`, instead of falling into standalone preview mode and staying on "Waiting for design…".

### Removed
- **2D sketch `mirror` entity.** Symmetric designs now model one half/quadrant and use native 3D `mirror` (`features/mirror.py`) instead of custom sketch solver mirroring.

## [0.7.0]

### Added
- **Floating Bill of Materials window.** Each built version card now has a `BOM` button that opens a wider floating palette (`palette/bom.html`) with `All` / `To Buy` / `To Make` filtering, search, live updates on parameter, build, chat, and theme changes, `Copy CSV`, and `Save CSV…`.

## [0.6.1]

### Fixed
- **Updating a design in an existing chat no longer crashes or stays stuck on "Building…".** Timeline group lookup now handles Fusion's `InternalValidationError` on `.index` for expanded or collapsed groups, and errors before a build starts cleanly end the active job.

## [0.6.0]

### Added
- **Per-component timeline groups.** Multi-component assemblies now group each part's occurrences and features into its own collapsed `<version> / <part>` timeline group instead of one monolithic group, while keeping version replace, undo detection, and suppression atomic.
- **Declarative JSON shape macros (`shapes/*.json`).** Any single-part design JSON can now serve as a parametric shape plugin in `shapes/` alongside Python `BaseShape` plugins, with auto-prefixed parameters and step IDs, optional `"inputs"`, `"presets"`, `"bom"`, and multi-pass nested shape expansion; `nema_motor`, `lead_screw`, `pillow_block`, and `spindle` now use `.json` macros.
- **Pluggable DSL features and sketch entities.** Timeline operations (`features/`) and sketch entities (`features/entities/`) are now auto-discovered plugins, each owning its schema, system-prompt syntax, validation, and Fusion build logic while keeping `dsl.py` plugin-neutral.
- **Bill of materials.** `python bom.py design.json bom.csv` lists everything to buy and make, with quantities: bought parts, screws, cut lengths, cables in metres, and the parts to print or machine. Counts follow instances and patterns. Designs, components and shapes can add items with `"bom"`; components can name their `"material"`.
- **Screws for bolt holes.** A `bolt_hole` with `"screw": {"length": ...}` adds its screws (rounded up to a stock length), nuts, T-nuts or heat-set inserts, and washers to the bill of materials.
- **Bought parts as shapes:** `nema_motor` (NEMA 14/17/23), `linear_rail` and `rail_carriage` (MGN7 to MGN15), `lead_screw` and `lead_nut` (T8), `pillow_block` (KP08), `shaft_coupler` and `spindle` (ER collet). Each has its mounting holes and the details that take up space (a motor's chamfered corners and cable connector, a carriage's end caps and grease nipple, a spindle's collet nut and power terminals), to design the parts around it, and lists itself in the bill of materials. `tslot_profile` lists its cut length too.

### Fixed
- **A cut in one part no longer cuts the parts placed against it.** Joins, cuts and intersects (extrude, revolve, sweep, coil) change only the bodies of their own component, so a carriage's channel no longer cuts into its rail.

## [0.5.0]

### Added
- **Assemblies.** A design can list several parts under `components`, each a Fusion component with its own timeline, sharing the design's parameters. `instances` place identical parts as copies of one component (turned and moved), so the parts list counts them and editing the component changes every copy. Changing a parameter that moves copies from VibeShaper's parameter list rebuilds the design so they move.
- **Build progress.** While Fusion builds a design, the panel shows a progress bar with the step being built.

### Fixed
- A length whose name contains "angle" (a rack angle's `angle_t`: "2 mm") is no longer created as an angle, which Fusion rejected.

## [0.4.0]

### Added
- **Pick edges by the step that made them.** Fillets and chamfers take `"edges": {"feature": "screw_cut", "exclude": "pocket_cut"}` to change only the edges a named step created.
- **Circular patterns around any point.** `circular_pattern` takes a `"center"`, so a part away from the origin (the second gear of a pair, say) is patterned around its own axis instead of the origin.
- **Spur gears in one step.** `{"op": "spur_gear", "module": ..., "teeth": ...}` builds an involute gear (one arc per tooth flank, within a few hundredths of a millimetre) that follows its parameters, including module and tooth count, when they change in Fusion.
- **Shape plugins** (`shapes/`): ready-made parts that expand into ordinary steps.
- **Bolt holes in one step.** `bolt_hole` cuts clearance holes for M2 to M12 bolts, with an optional counterbore, countersink or hex nut trap, sized from ISO tables plus a printing tolerance.
- **Vent grids.** `vent_grid` fills an area with round, hexagonal (honeycomb) or slot holes; the number of holes follows the area and hole size when they change.
- **T-slot profiles.** `tslot_profile` builds a 2020, 2040, 3030, 4040 (and similar) aluminum extrusion with its real section: corner blocks with lips, diagonal spars, a core with a bore, T-shaped slots and hollows between cells. Its sketch draws 1/8 of the section (1/4 for a 2040 or longer) and mirrors it. Every size can be overridden.
- **Grid patterns.** `linear_pattern` takes a second direction (`direction2`, `quantity2`, `distance2`).
- **Pick edges in a sketch's plane.** Edge selectors take `"on": sketch_id`, e.g. to chamfer only the rim of a hole at the face it was sketched on.
- **`profile` sketch entity**: a closed outline of lines and arcs (slots, rounded tabs).
- **`mirror` sketch entity**: copies earlier entities across a line, tied by symmetry constraints, like Fusion's sketch Mirror. Symmetric outlines are drawn once in part and mirrored.
- **`regular_polygon` sketch entity** (e.g. hex nut recesses), constrained like Fusion's polygon tool.

### Fixed
- Parameters such as `pitch_r * cos(20 deg)` are created as lengths, not angles.
- **Sketches follow parameter changes.** Sketch geometry is no longer fixed in place. Rectangles, lines and polygons get the constraints and dimensions you'd add by hand, so editing a parameter (a wall thickness, say) moves the geometry.

## [0.3.0]

### Changed
- **Renamed from PromptCAD to VibeShaper.** The add-in folder, its files, the settings folder (`%APPDATA%\VibeShaper`, `~/Library/Application Support/VibeShaper`) and the timeline group names all use the new name. To keep your settings, move them over from the old `PromptCAD` folder. Chats saved in designs by PromptCAD aren't shown.

## [0.2.0]

First public version.

### Added
- **Chat panel** docked in Fusion: describe a part, then refine it in follow-up messages. The model keeps the whole conversation.
- **Regenerate in place**: each chat owns one timeline group, and a new version replaces the previous one in a single undoable step. A failed rebuild leaves the previous version untouched.
- **Versions, JSON and parameters**: restore an earlier version, view or edit a version's JSON and build it, or change a parameter without asking the model.
- **Chats saved in the design**, so you can reopen a file later and keep refining. A chat can be deleted from the chat menu; the parts it built stay in the timeline.
- **Self-healing builds**: build errors go back to the model for a corrected design (up to 5 tries, configurable).
- **Build into a new component or a new body**, per chat.
- **Live streaming** of the model's reasoning, with Stop (Esc) at any time.
- **Pluggable providers**: Ollama (local) and Google Gemini, with model capabilities (images, thinking, tools) shown in the model menu and a per-model Think switch.
- **Design tools**: models that support tool calling can look at the open design (components, bodies, sketches, the timeline, parameters, the selection, distances) before building. Other models get a short text summary instead.
- **Pluggable tools**: toolkits are plugins in `tools/`, like providers.
- Settings and logs are kept in the user's own folder (`%APPDATA%\PromptCAD`, `~/Library/Application Support/PromptCAD`), outside the add-in.

[Unreleased]: https://github.com/slim-gears/vibeshaper/compare/v0.9.0...HEAD
[0.9.0]: https://github.com/slim-gears/vibeshaper/compare/v0.8.0...v0.9.0
[0.8.0]: https://github.com/slim-gears/vibeshaper/compare/v0.7.0...v0.8.0
[0.7.0]: https://github.com/slim-gears/vibeshaper/compare/v0.6.1...v0.7.0
[0.6.1]: https://github.com/slim-gears/vibeshaper/compare/v0.6.0...v0.6.1
[0.6.0]: https://github.com/slim-gears/vibeshaper/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/slim-gears/vibeshaper/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/slim-gears/vibeshaper/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/slim-gears/vibeshaper/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/slim-gears/vibeshaper/releases/tag/v0.2.0
