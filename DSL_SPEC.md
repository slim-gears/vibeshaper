# VibeShaper JSON DSL Specification

This document provides the definitive specification for the VibeShaper Parametric DSL. Any LLM or generator following this specification will produce valid, syntactically and geometrically correct CAD timelines that build reliably inside Autodesk Fusion 360 without errors.

---

## 1. Top-Level Structure

Every model definition is a single JSON object with two required top-level keys (a design of several parts adds `components` and `instances`, see section 5.15):

```json
{
  "name": "part_name",
  "parameters": {
    "<param_name>": "<expression>"
  },
  "timeline": [
    { "<operation_1>" },
    { "<operation_2>" }
  ]
}
```

* **`name`** *(optional string)*: Base identifier for the part. Used as a prefix if parameter names must be disambiguated when loaded alongside existing designs.
* **`parameters`** *(required object)*: Key-value map of user parameters driving the geometry.
* **`timeline`** *(required array)*: Ordered list of modeling operations executed sequentially to build the 3D parametric history.

---

## 2. Parameters & Expressions

Every meaningful dimension must be defined in `parameters` and referenced throughout sketches, offsets, extrusions, and patterns.

### Parameter Rules
1. **Identifier Syntax**: Parameter names must use `snake_case` matching regex `^[A-Za-z_][A-Za-z0-9_]*$`.
2. **Component Prefixing**: Always prefix parameter names with the component or feature name (e.g., `flange_dia`, `pipe_od`, `bolt_qty`, `boss_len`) rather than generic names (`dia`, `len`, `r`), preventing collisions when multiple parts coexist in the same Fusion document.
3. **Unit Defaults**:
   * **Lengths**: Default to millimeters (`mm`). Can be a number (`40`), literal string (`"40 mm"`), or arithmetic expression (`"flange_dia - 2 * wall_thick"`).
   * **Angles**: Include `deg` in the string (`"360 deg"`, `"45 deg"`).
   * **Quantities / Counts**: Unitless numbers or strings (`"6"`, `6`, `"bolt_count"`). Do **not** append `mm` to quantity variables.
4. **Expressions**: Standard arithmetic operators `+`, `-`, `*`, `/` and parentheses `(` `)` are supported. Fusion's unit manager evaluates them parametrically.

```json
"parameters": {
  "flange_dia": "80 mm",
  "flange_thick": "10 mm",
  "pipe_od": "30 mm",
  "pipe_wall": "3 mm",
  "pipe_id": "pipe_od - 2 * pipe_wall",
  "bolt_qty": "6",
  "bolt_r": "30 mm",
  "bolt_dia": "8 mm",
  "draft_angle": "5 deg"
}
```

---

## 3. Coordinate System & Planes

Fusion 360 uses a right-handed Cartesian coordinate system where **Z is up**.

| Plane | Orientation | Sketch Coordinates `[a, b]` | Positive Extrude Direction |
| :--- | :--- | :--- | :--- |
| **`"xy"`** | Ground / Top-down | `[X, Y]` (Z = 0) | Upwards (`+Z`) |
| **`"xz"`** | Front view | `[X, Z]` (Y = 0) | Outward (`+Y`) |
| **`"yz"`** | Side view | `[Y, Z]` (X = 0) | Rightward (`+X`) |

### Sketch Plane Offset
Sketches can be created on offset construction planes using `"offset"`:
* `"plane": "xy"`, `"offset": "50 mm"` $\rightarrow$ plane at $Z = 50\text{ mm}$.
* Negative offsets move along the negative axis normal.

---

<!-- BEGIN AUTO-GENERATED PLUGINS -->
<!-- Auto-generated from features/, features/entities/, and shapes/ plugins via dsl.sync_spec(). -->

## 4. Sketch Entities

A sketch step contains a non-empty `entities` array. Every entity may include an optional `"id"` to be referenced by sketch constraints.

### 4.1. Center rectangle (`center_rectangle`)
```text
{"type": "center_rectangle", "center": [a, b], "width": along a, "height": along b}
```
* **Keys**: `type` *(required)*, `center` *(required)*, `width` *(required)*, `height` *(required)*, `id` *(optional)*

### 4.2. Circle (`circle`)
```text
{"type": "circle", "center": [a, b], "diameter": d}
```
* **Keys**: `type` *(required)*, `center` *(required)*, `diameter` *(required)*, `id` *(optional)*

### 4.3. Polygon (`polygon`)
```text
{"type": "polygon", "points": [[a, b], ...], "closed": true}   at least 3 points
```
* **Keys**: `type` *(required)*, `points` *(required)*, `closed` *(optional)*, `id` *(optional)*

### 4.4. Line (`line`)
```text
{"type": "line", "start": [a, b], "end": [c, d]}
```
* **Keys**: `type` *(required)*, `start` *(required)*, `end` *(required)*, `id` *(optional)*

### 4.5. Polyline (`polyline`)
```text
{"type": "polyline", "points": [[a, b], ...], "closed": false}  open spine/path for sweeps or wires
```
* **Keys**: `type` *(required)*, `points` *(required)*, `closed` *(optional)*, `id` *(optional)*

### 4.6. Spline (`spline`)
```text
{"type": "spline", "points": [[a, b], ...], "closed": false}   smooth fitted spline curve through points (periodic loop when "closed": true)
```
* **Keys**: `type` *(required)*, `points` *(required)*, `closed` *(optional)*, `id` *(optional)*

### 4.7. Regular polygon (`regular_polygon`)
```text
{"type": "regular_polygon", "center": [a, b], "sides": n, "across_flats": d}   or "diameter" (through the corners) instead of across_flats; e.g. hex nut recesses
```
* **Keys**: `type` *(required)*, `center` *(required)*, `sides` *(required)*, `diameter` *(optional)*, `across_flats` *(optional)*, `id` *(optional)*

### 4.8. Profile (`profile`)
```text
{"type": "profile", "start": [a, b], "segments": [{"to": [c, d]}, {"to": [e, f], "through": [mx, my]}, {"to": [g, h], "spline": [[p1x, p1y], ...]}], "closed": true}   outline of lines, 3-point arcs ("through"), and fitted splines ("spline": intermediate fit points)
```
* **Keys**: `type` *(required)*, `start` *(required)*, `closed` *(optional)*, `segments` *(required)*, `id` *(optional)*

---

## 5. Timeline Operations

The `timeline` is an ordered array of step objects. Each step specifies `"op"` from the 13 core operations below or the shape plugins in Section 5.14.

### 5.1. `sketch` (Sketch)
```text
Sketch:
   {"op": "sketch", "id": unique_name, "plane": "xy"|"xz"|"yz", "offset": length (optional), "entities": [entity, ...], "constraints": [{"type": "perpendicular"|"parallel"|"concentric"|"tangent"|"equal"|"coincident", "entities": [id1, id2]}, {"type": "midpoint", "point": pt_id, "entity": line_id}, {"type": "symmetry", "entities": [id1, id2], "symmetry_line": line_id}, ...] (optional)}
```
* **Step keys**: `op`, `id` *(optional unless required above)*, `plane`, `offset`, `entities`, `constraints`

### 5.2. `extrude` (Extrude)
```text
Extrude:
   {"op": "extrude", "id": optional_name, "sketch": sketch_id, "distance": length, "mode": "new_body"|"join"|"cut"|"intersect"}
```
* **Step keys**: `op`, `id` *(optional unless required above)*, `sketch`, `distance`, `mode`
- An extrude or revolve uses EVERY closed region of its sketch. Never draw a shape inside another shape in the same sketch.

### 5.3. `revolve` (Revolve)
```text
Revolve:
   {"op": "revolve", "id": optional_name, "sketch": sketch_id, "axis": "x"|"y"|"z", "angle": "360 deg" (optional), "mode": "new_body"|"join"|"cut"}
```
* **Step keys**: `op`, `id` *(optional unless required above)*, `sketch`, `axis`, `angle`, `mode`

### 5.4. `fillet` (Fillet)
```text
Fillet (ONLY uses radius and edges! NEVER put thickness or remove_faces here!):
   {"op": "fillet", "radius": length, "edges": "vertical"|"top"|"bottom"|"circular"|"all"|edge_object}
```
* **Step keys**: `op`, `id` *(optional unless required above)*, `radius`, `edges`, `target`
- For rounded corners or chamfered rims, use `fillet` or `chamfer` with edge selectors (`"vertical"`, `"top"`, `"circular"`).

### 5.5. `chamfer` (Chamfer)
```text
Chamfer (ONLY uses distance and edges!):
   {"op": "chamfer", "distance": length, "edges": "vertical"|"top"|"bottom"|"circular"|"all"|edge_object}
   edge_object picks edges made by an earlier step: {"feature": step_id, "faces": "all"|"side"|"start"|"end" (optional), "exclude": step_id or [ids] (optional, drops edges touching those steps' faces), "on": sketch_id (optional, only edges in that sketch's plane), "type": "circle"|"line" (optional), "at": "top"|"bottom" (optional, highest/lowest Z), "direction": "x"|"y"|"z" (optional, line edge axis)}.
   Prefer it over the broad words when only some edges should change, e.g. {"feature": "screw_cut", "type": "circle", "exclude": "pocket_cut"}.
```
* **Step keys**: `op`, `id` *(optional unless required above)*, `distance`, `edges`, `target`

### 5.6. `shell` (Shell)
```text
Shell (ONLY uses thickness and remove_faces! NEVER put radius or edges here!):
   {"op": "shell", "thickness": length, "remove_faces": "top"|"bottom"|"none"}
```
* **Step keys**: `op`, `id` *(optional unless required above)*, `thickness`, `remove_faces`, `target`
- For hollow boxes or open containers, prefer `shell` with `remove_faces: "top"` over manual pocket cuts!
- When making an open box with rounded corners: FIRST `extrude`, NEXT `fillet` the vertical corners, THEN `shell` the top face (or shell first, then fillet). They are two distinct steps!

### 5.7. `circular_pattern` (Circular pattern)
```text
Circular Pattern:
   {"op": "circular_pattern", "feature": feature_id (optional), "axis": "z", "center": [a, b] (optional, default [0, 0]), "quantity": count, "angle": "360 deg"}
   The axis passes through "center" ([x, y] for "z", [y, z] for "x", [x, z] for "y"). Set it whenever the patterned part is not centered on the origin.
```
* **Step keys**: `op`, `id` *(optional unless required above)*, `feature`, `axis`, `center`, `quantity`, `angle`
- For radial arrays (e.g. 6 bolt holes on a flange), draw ONE hole and use `circular_pattern`!

### 5.8. `linear_pattern` (Linear pattern)
```text
Linear Pattern:
   {"op": "linear_pattern", "feature": feature_id (optional), "direction": "x"|"y"|"z", "distance": spacing, "quantity": count,
    "direction2": another axis, "distance2": spacing, "quantity2": count (optional, all three for a grid)}
```
* **Step keys**: `op`, `id` *(optional unless required above)*, `feature`, `direction`, `distance`, `quantity`, `direction2`, `distance2`, `quantity2`

### 5.9. `thread` (Thread)
```text
Thread:
   {"op": "thread", "feature": feature_id (optional), "target": "internal"|"external"|"all" (optional), "modeled": true|false (optional, default true), "designation": "M6x1" (optional)}
```
* **Step keys**: `op`, `id` *(optional unless required above)*, `feature`, `target`, `modeled`, `designation`, `thread_class`, `diameter`
- To thread a hole, bore, or bolt, add a `thread` step specifying the cut feature: `{"op": "thread", "feature": "bore_cut", "target": "internal", "designation": "M20x2.5"}`. Physical 3D threads are modeled by default (`modeled: true`).

### 5.10. `mirror` (Mirror)
```text
Mirror:
   {"op": "mirror", "feature": feature_id (optional), "target": body_or_feature_id (optional), "plane": "xy"|"xz"|"yz"|"top"|"bottom", "offset": length (optional), "combine": true|false (optional, default true)}
```
* **Step keys**: `op`, `id` *(optional unless required above)*, `feature`, `plane`, `offset`, `combine`, `target`
- For symmetric designs, model ONE half and use `mirror` across "xz" or "yz" with `combine: true` to complete the full symmetric body!

### 5.11. `combine` (Combine)
```text
Combine (Boolean):
   {"op": "combine", "target": body_or_feature_id (optional), "tools": [tool_id, ...], "mode": "cut"|"join"|"intersect", "keep_tools": false}
```
* **Step keys**: `op`, `id` *(optional unless required above)*, `target`, `tools`, `mode`, `keep_tools`
- To carve or combine separate bodies, use `combine` with `mode: "cut"` / `"join"` and list tool body IDs in `tools`.

### 5.12. `sweep` (Sweep)
```text
Sweep:
   {"op": "sweep", "sketch": profile_sketch_id, "path": path_sketch_id, "mode": "new_body"|"join"|"cut"}
```
* **Step keys**: `op`, `id` *(optional unless required above)*, `sketch`, `path`, `mode`
- For bent pipes, tubing, wire routing, or rails, draw a cross-section `sketch` and a spine/route `path` sketch, then use `sweep`.
- For hollow pipes or conduit: to ensure fluid can pass through, FIRST sweep the outer pipe body (`mode: "new_body"`), THEN sweep an inner bore circle with a smaller diameter along the path (`mode: "cut"`) so the pipe is hollow and has a through-bore from end to end.
- When modeling a gusset rib against a round pipe or cylinder: rib sketch points MUST extend into the body centerline (e.g. at [0, 0] or into the wall), NOT stop on the outer radius. Because round cylinders curve away from the offset sketch plane, stopping at the outer radius causes floating gaps!

### 5.13. `coil` (Coil)
```text
Coil (Spring / Helix):
   {"op": "coil", "diameter": coil_dia, "pitch": pitch, "revolutions": count, "height": length (optional; any 2 of pitch, revolutions, height), "section_size": wire_dia, "section": "circle"|"square" (optional, default "circle"), "center": [x, y, z] (optional, default [0, 0, 0]), "clockwise": true|false (optional, default true), "axis": "z"|"x"|"y" (optional, default "z"), "mode": "new_body"|"join"|"cut" (optional, default "new_body")}
```
* **Step keys**: `op`, `id` *(optional unless required above)*, `diameter`, `pitch`, `revolutions`, `section_size`, `section`, `axis`, `center`, `mode`, `clockwise`
- For springs, coils, or screw helices, use `coil` with `diameter` (major coil diameter), `section_size` (wire diameter), and `pitch` / `revolutions` (or `height`).

### 5.14. Shapes (plugin steps)
Ready-made parametric parts and features in `shapes/`. Each expands into ordinary parameters and timeline steps before validation and build, prefixed by its required `"id"` (`<id>_...`). Every preset dimension can be overridden.

#### `spur_gear` — Spur gear
```text
{"op": "spur_gear", "id": name, "module": length, "teeth": count, "thickness": length,
 "center": [a, b] (optional, default [0, 0]), "plane": "xy"|"xz"|"yz" (optional, default "xy"), "offset": length (optional),
 "pressure_angle": angle (optional, default "20 deg"), "rotate": angle (optional), "bore": diameter (optional),
 "mode": "new_body"|"join" (optional)}
  An involute spur gear in one step; its pitch diameter is module * teeth. The step's "id" names the finished gear.
  Gears that mesh share module and pressure angle; their centers are module * (teeth1 + teeth2) / 2 apart.
  A gear at the origin has a tooth pointing along +a. For a second gear placed along +a, set "rotate": "180 deg / teeth2"
  when teeth2 is even (so a gap faces the first gear's tooth); leave rotate out when teeth2 is odd.
  Example: {"op": "spur_gear", "id": "gear2", "module": "gear_module", "teeth": "gear2_teeth", "thickness": "gear_thick",
   "center": ["gear_module * (gear1_teeth + gear2_teeth) / 2", 0], "bore": "8 mm"}
```
* **Step keys**: `op`, `id` *(required)*, `module`, `teeth`, `thickness`, `pressure_angle`, `rotate`, `bore`

#### `bolt_hole` — Bolt hole
```text
{"op": "bolt_hole", "id": name, "size": "M2"|"M2.5"|"M3"|"M4"|"M5"|"M6"|"M8"|"M10"|"M12", "plane": "xy"|"xz"|"yz", "offset": length,
 "points": [[a, b], ...] (or "center": [a, b]), "depth": length,
 "head": "none"|"counterbore"|"countersink"|"nut_trap" (optional, default "none"), "fit": "close"|"normal"|"loose" (optional, default "normal"),
 "tolerance": length (optional, default "0.3 mm", added to head and nut pockets)}
  Cuts standard clearance holes for metric bolts into the existing body, with the head or nut pocket sized from ISO tables;
  use it instead of drawing bolt holes, counterbores or nut traps by hand. Put the sketch plane (plane + offset) on the face
  the bolt enters; "depth" is signed like an extrude distance (negative cuts against the plane's normal, e.g. down from a top face).
  The pocket is cut at that face. The step's "id" names the hole cut.
  Optional "screw": {"length": length, "head": "socket"|"button"|"countersunk", "nut": "none"|"hex"|"nyloc"|"t_nut_20"|"t_nut_30"|"t_nut_40"|"insert",
   "washer": true|false} puts one screw per hole (and per copy a pattern makes) into the bill of materials. "length" is the
   shortest that reaches; the next stock length is ordered. Defaults: head "countersunk" for a countersink, else "socket";
   nut "hex" for a nut trap, else "none". Give "screw" on one side of a joint only, so screws aren't counted twice.
  Example: {"op": "bolt_hole", "id": "mount_bolts", "size": "M5", "plane": "xy", "offset": "base_thick", "depth": "-base_thick",
   "head": "nut_trap", "points": [["-hole_off", "-hole_off"], ["hole_off", "-hole_off"], ["hole_off", "hole_off"], ["-hole_off", "hole_off"]]}
```
* **Step keys**: `op`, `id` *(required)*, `size`, `points`, `depth`, `head`, `fit`, `tolerance`, `screw`

#### `vent_grid` — Vent grid
```text
{"op": "vent_grid", "id": name, "plane": "xy"|"xz"|"yz", "offset": length, "center": [a, b] (optional, default [0, 0]),
 "width": length, "height": length, "size": length, "depth": length,
 "hole": "circle"|"hexagon"|"slot" (optional, default "circle"), "length": length (slots only: overall slot length, along b),
 "wall": length (optional, default "2 mm", material between holes), "layout": "grid"|"staggered" (optional; default "staggered", "grid" for slots),
 "columns": count, "rows": count (optional; by default as many as fit)}
  Cuts a pattern of vent holes, filling a width x height area (along a and b) centered on "center", into the existing body.
  "size" is the hole diameter, the hexagon's width across flats, or the slot width. Put the sketch plane on the face to cut
  through; "depth" is signed like an extrude distance. Hexagons with "staggered" make a honeycomb. The step's "id" names
  the last pattern.
  Example: {"op": "vent_grid", "id": "lid_vent", "plane": "xy", "offset": "lid_thick", "width": "60 mm", "height": "40 mm",
   "hole": "hexagon", "size": "5 mm", "wall": "1.6 mm", "depth": "-lid_thick"}
```
* **Step keys**: `op`, `id` *(required)*, `width`, `height`, `hole`, `size`, `length`, `wall`, `layout`, `depth`, `columns`, `rows`

#### `tslot_profile` — T-slot profile
```text
{"op": "tslot_profile", "id": name, "series": "2020"|"2040"|"2060"|"2080"|"3030"|"3060"|"4040"|"4080", "length": length,
 "plane": "xy"|"xz"|"yz" (optional, default "xy"; the profile runs along the plane's normal), "offset": length (optional),
 "center": [a, b] (optional, default [0, 0]), "mode": "new_body" (optional),
 overrides (optional lengths): "slot" (opening), "chamber" (width under the lips), "lip", "spar" (diagonal web), "core",
 "core_shape": "square"|"round", "bore" (center hole, 0: none), "corner_hole" (0: none), "corner_hole_shape": "square"|"round",
 "fillet" (outer corners), "recess_width", "recess_depth" (shallow cut along each opening, 0: none)}
  An aluminum T-slot extrusion with the real section: rounded corner blocks with lips, a core with a bore in each cell,
  diagonal spars, slots that widen under the lips, and hollows between cells. For mockups and for designing parts
  that fit it. "2040" is 20 mm along a and 40 mm along b. "length" is signed like an extrude distance. The preset
  sizes are typical; override them from the supplier's drawing. The step's "id" names the extrusion.
  Example: {"op": "tslot_profile", "id": "rail", "series": "2040", "length": "rail_len"}
```
* **Step keys**: `op`, `id` *(required)*, `series`, `length`, `slot`, `chamber`, `lip`, `spar`, `core`, `core_shape`, `bore`, `corner_hole`, `corner_hole_shape`, `fillet`, `recess_width`, `recess_depth`

#### `linear_rail` — Linear rail
```text
{"op": "linear_rail", "id": name, "series": "MGN7"|"MGN9"|"MGN12"|"MGN15", "length": length, "note": text (optional)}
  A miniature linear guide rail cut to length (bought part), with counterbored holes centered along it. It runs along +x
  from x = 0, centered on y = 0, bottom on z = 0. Parameters: "<id>_rail_w", "<id>_rail_h", "<id>_pitch" (hole spacing),
  "<id>_count" (holes), "<id>_start" (x of the first hole). Pair it with rail_carriage steps of the same series.
```
* **Step keys**: `op`, `id` *(required)*, `series`, `length`, `note`

#### `nema_motor` — NEMA stepper motor
```text
{"op": "nema_motor", "id": name, "size": "14"|"17"|"23", "length": body length (e.g. 40 mm), "note": text (optional, e.g. "1.5 A, 0.42 N·m")}
  A stepper motor (bought part): square body, pilot boss, shaft, the 4 tapped holes on the face and the cable connector
  on the -y side near the back. The face is the xy plane at z = 0, the body goes down, the shaft points up (+z) from [0, 0]. Model it in its own component and place it
  with instances; design mounts around "<id>_pitch" (hole spacing), "<id>_pilot" (boss) and "<id>_face" (body width).
```
* **Step keys**: `op`, `id` *(required)*, `note`, `size`, `length`

#### `rail_carriage` — Rail carriage
```text
{"op": "rail_carriage", "id": name, "series": "MGN7"|"MGN9"|"MGN12"|"MGN15", "block": "H"|"C" (optional, default "H": long; "C": short), "note": text (optional)}
  The carriage (block) of a linear_rail (bought part), centered on x = y = 0 in the rail's axes (rail bottom on z = 0),
  with 4 tapped holes on top, plastic end caps and a grease nipple on the +x end. Parameters: "<id>_height" (top above the rail's bottom), "<id>_width", "<id>_length",
  "<id>_hole_b" (hole spacing across), "<id>_hole_c" (along). Make it its own component and place each carriage with
  an instance at its spot along the rail.
```
* **Step keys**: `op`, `id` *(required)*, `series`, `block`, `note`

#### `lead_screw` — Lead screw
```text
{"op": "lead_screw", "id": name, "length": length, "diameter": mm (optional, default 8), "lead": mm per turn (optional, default 2), "note": text (optional)}
  A trapezoidal lead screw (bought part), drawn as a plain rod along +z from z = 0. Order lengths are rounded up to the
  next stock length (100, 150, 200 ... mm), so pick one of those. Pair it with a lead_nut.
```
* **Step keys**: `op`, `id` *(required)*, `note`, `length`, `diameter`, `lead`

#### `lead_nut` — Lead screw nut
```text
{"op": "lead_nut", "id": name, "lead": mm (optional, default 2), "anti_backlash": true|false (optional, default true), "note": text (optional)}
  The flanged nut of a T8 lead_screw (bought part). Its flange face is the xy plane at z = 0: the flange is above it,
  the body below, the screw passes along z. Parameters: "<id>_flange" (diameter), "<id>_flange_t", "<id>_body"
  (diameter), "<id>_pcd" (circle of the 4 mounting holes, on the x and y axes), "<id>_hole", "<id>_length".
```
* **Step keys**: `op`, `id` *(required)*, `anti_backlash`, `lead`, `note`

#### `pillow_block` — Pillow block bearing
```text
{"op": "pillow_block", "id": name, "model": "KP08" (optional, default "KP08"), "note": text (optional)}
  A pillow block bearing (bought part) for the free end of a lead screw. Base on z = 0, centered on the origin, shaft
  along y at height "<id>_center_h". Parameters: "<id>_bore", "<id>_length" (base, along x), "<id>_width" (along y),
  "<id>_hole_spacing" (2 base holes on the x axis), "<id>_hole".
```
* **Step keys**: `op`, `id` *(required)*, `note`, `model`

#### `shaft_coupler` — Shaft coupler
```text
{"op": "shaft_coupler", "id": name, "bore1": mm (optional, default 5), "bore2": mm (optional, default 8), "diameter": mm (optional, default 19), "length": mm (optional, default 25), "note": text (optional)}
  A flexible shaft coupler (bought part) along +z from z = 0: "bore1" from the bottom (the motor shaft), "bore2" from the
  top (the screw). Parameters: "<id>_diameter", "<id>_length".
```
* **Step keys**: `op`, `id` *(required)*, `bore1`, `bore2`, `note`

#### `spindle` — Spindle
```text
{"op": "spindle", "id": name, "collet": "ER8"|"ER11"|"ER16"|"ER20" (optional, default "ER11"), "diameter": body (optional, default 52 mm),
 "length": body (optional, default 160 mm), "nose": collet nut diameter (optional, default 19 mm), "nose_len": (optional, default 25 mm), "note": text (optional, e.g. "300 W, 48 V")}
  A DC milling spindle (bought part). The bottom face of the body is the xy plane at z = 0; the body goes up, the
  collet nose down to z = -"<id>_nose_len". Clamp it around "<id>_diameter".
```
* **Step keys**: `op`, `id` *(required)*, `note`, `collet`, `diameter`, `length`, `nose`, `nose_len`
<!-- END AUTO-GENERATED PLUGINS -->

### 5.15. Assemblies: `components` and `instances`
A design made of separate parts lists them under `components`. Each becomes a Fusion component with its own timeline; identical parts are one component placed several times by `instances`, so the parts list counts them and editing the component changes every copy.

```json
{
  "parameters": {"leg_len": "400 mm", "top_w": "600 mm", "top_d": "400 mm", "top_t": "18 mm", "leg_inset": "40 mm"},
  "timeline": [],
  "components": [
    {"id": "leg", "name": "Leg", "timeline": [
      {"op": "sketch", "id": "leg_sk", "plane": "xy", "entities": [{"type": "center_rectangle", "center": [0, 0], "width": "40 mm", "height": "40 mm"}]},
      {"op": "extrude", "sketch": "leg_sk", "distance": "leg_len", "mode": "new_body"}]},
    {"id": "top", "name": "Table top", "timeline": [
      {"op": "sketch", "id": "top_sk", "plane": "xy", "offset": "leg_len", "entities": [{"type": "center_rectangle", "center": [0, 0], "width": "top_w", "height": "top_d"}]},
      {"op": "extrude", "sketch": "top_sk", "distance": "top_t", "mode": "new_body"}]}
  ],
  "instances": [
    {"component": "leg", "position": ["top_w / 2 - leg_inset", "top_d / 2 - leg_inset", 0]},
    {"component": "leg", "position": ["leg_inset - top_w / 2", "top_d / 2 - leg_inset", 0]},
    {"component": "leg", "position": ["leg_inset - top_w / 2", "leg_inset - top_d / 2", 0]},
    {"component": "leg", "position": ["top_w / 2 - leg_inset", "leg_inset - top_d / 2", 0]}
  ]
}
```
* **`parameters`** are shared by every component.
* **`components`**: each has an **`id`** (snake_case), an optional **`name`** shown in Fusion, and a non-empty **`timeline`**. Sketch and feature ids belong to their component, so two components may both have a `base_sk`. The rules of section 6 apply to each timeline.
* **`instances`** *(optional)*: each names a **`component`**, with an optional **`id`**, a **`position`** `[x, y, z]` (default the origin) and **`rotate`**, a list of `{"axis": "x"|"y"|"z", "angle": angle}`. The component is turned about the world axes through its own origin, in the order given, then moved to `position`. A component with no instances is placed once, where its timeline modeled it.
* The top-level **`timeline`** may be empty; steps in it are built in the design's own component.
* Copies can't be mirror images of their component: turn the part instead, or make a separate component. Parts that differ in any size are separate components.
* Fusion doesn't move a placed copy when a parameter changes. When a parameter an instance's `position` or `rotate` depends on is changed from VibeShaper's parameter list, VibeShaper rebuilds the design so the copies move; a change made in Fusion's own Change Parameters dialog doesn't move them.
* Part Design documents hold a single component, so a design with `components` can't be built there.

### 5.16. Bill of materials: `bom` and `material`
A design meant to be built can produce its bill of materials: everything to buy and make, with quantities. Run `python bom.py design.json bom.csv` (no Fusion needed). It writes a CSV with the columns Category, Item, Qty, Unit, Note and Link.

Items come from three places:
* **Shape steps.** Bought parts (`nema_motor`, `linear_rail`, `tslot_profile`...) list themselves, and a `bolt_hole` with a `"screw"` lists its screws, nuts and washers. Give `"screw"` on one side of a joint only.
* **A component's `"bom"`**: extra items for that part (a T-nut, grease).
* **The design's top-level `"bom"`**: anything not modeled (wires, a power supply, consumables).

```json
"bom": [
  {"category": "Electronics", "item": "24 V 6 A power supply", "qty": 1, "link": "https://..."},
  {"category": "Wiring", "item": "4-core 22 AWG cable", "unit": "m", "qty": "x_travel + 400 mm", "round": 0.5}
]
```
* **`category`**, **`item`** *(required strings)*: Items with the same category, item text, unit, note and link are added into one line.
* **`qty`** *(optional, default 1)*: A number or an expression over the design's parameters. When `unit` is a length (`"mm"`, `"cm"`, `"m"`) and `qty` is an expression, it is a length and is converted to that unit; a plain number is already in it.
* **`unit`** *(optional string, default `"pcs"`)*.
* **`length`** *(optional expression)*: The length of one piece. It fills `{length}` (`"300 mm"`) or `{length_mm}` (`"300"`) in the item text, and a negative length counts as positive.
* **`stock`** *(optional list of mm)*: Lengths sold. The piece's length is rounded up to the next one.
* **`round`** *(optional number)*: The line's total is rounded up to a multiple of it (`0.5` for half metres of cable).
* **`whole`** *(optional boolean)*: This item is the bought part itself, so its component isn't also listed as a part to make. Shapes set it.
* **`note`**, **`link`** *(optional strings)*: A rating or a seller's model number, and where to buy it.

A component's items, and the items of the shapes in its timeline, count once per instance. A shape's items also count once per copy that a later `circular_pattern` or `linear_pattern` makes of it. A component (or a single-part design) that no item marks as `whole` is listed under **Made**, once per instance, with its **`material`** (an optional string on the component, e.g. `"PETG"`) as the note.

---

## 6. Critical CAD Modeling Rules

To ensure 100% reliable execution without geometric failures:

1. **First 3D Step Must Be `new_body`**:
   The very first 3D operation in the timeline must use `"mode": "new_body"`. Subsequent operations can use `"join"`, `"cut"`, or `"new_body"`.
2. **Never Draw Concentric Shapes in One Sketch**:
   Fusion 360's API selects **every** closed profile in a sketch during extrusion. If you draw two concentric circles in one sketch, Fusion will extrude both (or fail profile selection).
   * **Correct Way to Make a Hollow Cylinder/Pipe**:
     1. Sketch outer circle $\rightarrow$ Extrude `new_body`.
     2. Sketch inner circle $\rightarrow$ Extrude `cut`.
     *(Or use `shell`)*.
3. **Never Combine Operations in a Single Timeline Step**:
   Every operation (`extrude`, `fillet`, `shell`, `chamfer`, etc.) **must** be its own distinct object in the `timeline` array. Never add `remove_faces` or `thickness` to an `extrude` or `fillet` step.
4. **Hollow Swept Tubing / Elbows**:
   To model a hollow pipe through which fluid can pass:
   1. Draw outer circle sketch $\rightarrow$ Sweep along path (`mode: "new_body"`).
   2. Draw inner circle sketch $\rightarrow$ Sweep along path (`mode: "cut"`).
5. **Gusset Ribs Against Round Cylinders**:
   When drawing a triangular gusset rib or bracket against a cylindrical pipe:
   * Rib sketch points must extend **into the cylinder centerline** (`[0, 0]` or past the wall), **not** stop on the outer radius.
   * Because round cylinders curve away from the offset sketch plane, stopping at the outer radius creates an airborne gap and causes `join` to fail.
6. **Thread Diameter Consistency**:
   The thread `"designation"` (e.g. `"M20x2.5"`) must match the nominal diameter of the hole/boss (20 mm). The add-in automatically matches thread sizes to compatible cylinders.
7. **Springs and Helices**:
   Use the dedicated `"op": "coil"` operation. Specify the major coil diameter (`"diameter"`), wire thickness (`"section_size"`), and turn spacing (`"pitch"` and/or `"revolutions"`). Any two of (`pitch`, `revolutions`, `height`) will automatically derive the third.

---

## 7. Complete Reference Examples

### Example 1: Enclosure Box with Rounded Corners and Shell
```json
{
  "name": "enclosure",
  "parameters": {
    "box_width": "80 mm",
    "box_length": "120 mm",
    "box_height": "40 mm",
    "wall_thick": "3 mm",
    "corner_r": "6 mm"
  },
  "timeline": [
    {
      "op": "sketch",
      "id": "base_sk",
      "plane": "xy",
      "entities": [
        {
          "type": "center_rectangle",
          "center": [0, 0],
          "width": "box_width",
          "height": "box_length"
        }
      ]
    },
    {
      "op": "extrude",
      "id": "outer_body",
      "sketch": "base_sk",
      "distance": "box_height",
      "mode": "new_body"
    },
    {
      "op": "fillet",
      "edges": "vertical",
      "radius": "corner_r"
    },
    {
      "op": "shell",
      "remove_faces": "top",
      "thickness": "wall_thick"
    }
  ]
}
```

### Example 2: Flanged Hub with Bolt Pattern and Center Bore
```json
{
  "name": "flanged_hub",
  "parameters": {
    "flange_dia": "80 mm",
    "flange_thick": "8 mm",
    "boss_dia": "40 mm",
    "boss_h": "30 mm",
    "bore_dia": "20 mm",
    "bolt_dia": "6 mm",
    "bolt_r": "30 mm",
    "bolt_qty": "6"
  },
  "timeline": [
    {
      "op": "sketch",
      "id": "flange_sk",
      "plane": "xy",
      "entities": [
        {
          "type": "circle",
          "center": [0, 0],
          "diameter": "flange_dia"
        }
      ]
    },
    {
      "op": "extrude",
      "sketch": "flange_sk",
      "distance": "flange_thick",
      "mode": "new_body"
    },
    {
      "op": "sketch",
      "id": "boss_sk",
      "plane": "xy",
      "offset": "flange_thick",
      "entities": [
        {
          "type": "circle",
          "center": [0, 0],
          "diameter": "boss_dia"
        }
      ]
    },
    {
      "op": "extrude",
      "sketch": "boss_sk",
      "distance": "boss_h",
      "mode": "join"
    },
    {
      "op": "sketch",
      "id": "bore_sk",
      "plane": "xy",
      "entities": [
        {
          "type": "circle",
          "center": [0, 0],
          "diameter": "bore_dia"
        }
      ]
    },
    {
      "op": "extrude",
      "sketch": "bore_sk",
      "distance": "flange_thick + boss_h",
      "mode": "cut"
    },
    {
      "op": "sketch",
      "id": "one_bolt_sk",
      "plane": "xy",
      "entities": [
        {
          "type": "circle",
          "center": ["bolt_r", 0],
          "diameter": "bolt_dia"
        }
      ]
    },
    {
      "op": "extrude",
      "id": "bolt_cut",
      "sketch": "one_bolt_sk",
      "distance": "flange_thick",
      "mode": "cut"
    },
    {
      "op": "circular_pattern",
      "feature": "bolt_cut",
      "axis": "z",
      "quantity": "bolt_qty"
    },
    {
      "op": "chamfer",
      "edges": "circular",
      "distance": "1 mm"
    }
  ]
}
```

### Example 3: Swept 90° Pipe Elbow with Flange, Threaded Port, and Mirrored Ribs
```json
{
  "name": "elbow_assembly",
  "parameters": {
    "pipe_od": "30 mm",
    "pipe_id": "16 mm",
    "pipe_len": "80 mm",
    "flange_dia": "80 mm",
    "flange_thick": "10 mm",
    "boss_dia": "40 mm",
    "boss_len": "25 mm",
    "bore_dia": "20 mm",
    "gusset_thick": "4 mm"
  },
  "timeline": [
    {
      "op": "sketch",
      "id": "path_sk",
      "plane": "xz",
      "entities": [
        {
          "type": "polyline",
          "points": [
            [0, "pipe_len"],
            [0, 0],
            ["pipe_len", 0]
          ],
          "closed": false
        }
      ]
    },
    {
      "op": "sketch",
      "id": "outer_profile_sk",
      "plane": "xy",
      "offset": "pipe_len",
      "entities": [
        {
          "type": "circle",
          "center": [0, 0],
          "diameter": "pipe_od"
        }
      ]
    },
    {
      "op": "sweep",
      "id": "pipe_body",
      "sketch": "outer_profile_sk",
      "path": "path_sk",
      "mode": "new_body"
    },
    {
      "op": "sketch",
      "id": "flange_sk",
      "plane": "xy",
      "offset": "pipe_len - flange_thick",
      "entities": [
        {
          "type": "circle",
          "center": [0, 0],
          "diameter": "flange_dia"
        }
      ]
    },
    {
      "op": "extrude",
      "sketch": "flange_sk",
      "distance": "flange_thick",
      "mode": "join"
    },
    {
      "op": "sketch",
      "id": "boss_sk",
      "plane": "yz",
      "offset": "pipe_len",
      "entities": [
        {
          "type": "circle",
          "center": [0, 0],
          "diameter": "boss_dia"
        }
      ]
    },
    {
      "op": "extrude",
      "sketch": "boss_sk",
      "distance": "boss_len",
      "mode": "join"
    },
    {
      "op": "sketch",
      "id": "inner_profile_sk",
      "plane": "xy",
      "offset": "pipe_len",
      "entities": [
        {
          "type": "circle",
          "center": [0, 0],
          "diameter": "pipe_id"
        }
      ]
    },
    {
      "op": "sketch",
      "id": "cut_path_sk",
      "plane": "xz",
      "entities": [
        {
          "type": "polyline",
          "points": [
            [0, "pipe_len + 2 mm"],
            [0, 0],
            ["pipe_len + boss_len + 2 mm", 0]
          ],
          "closed": false
        }
      ]
    },
    {
      "op": "sweep",
      "id": "bore_sweep",
      "sketch": "inner_profile_sk",
      "path": "cut_path_sk",
      "mode": "cut"
    },
    {
      "op": "sketch",
      "id": "port_sk",
      "plane": "yz",
      "offset": "pipe_len + boss_len",
      "entities": [
        {
          "type": "circle",
          "center": [0, 0],
          "diameter": "bore_dia"
        }
      ]
    },
    {
      "op": "extrude",
      "id": "port_cut",
      "sketch": "port_sk",
      "distance": "-boss_len",
      "mode": "cut"
    },
    {
      "op": "thread",
      "feature": "port_cut",
      "target": "internal",
      "designation": "M20x2.5",
      "modeled": true
    },
    {
      "op": "sketch",
      "id": "gusset_sk",
      "plane": "xz",
      "offset": "pipe_od / 4",
      "entities": [
        {
          "type": "polygon",
          "points": [
            [0, "pipe_len - flange_thick - 5 mm"],
            [0, 0],
            ["pipe_len - 5 mm", 0]
          ],
          "closed": true
        }
      ]
    },
    {
      "op": "extrude",
      "id": "gusset",
      "sketch": "gusset_sk",
      "distance": "gusset_thick",
      "mode": "join"
    },
    {
      "op": "mirror",
      "feature": "gusset",
      "plane": "xz",
      "combine": true
    }
  ]
}
```
