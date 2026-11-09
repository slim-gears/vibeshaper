# VibeShaper JSON DSL Specification

This document provides the definitive specification for the VibeShaper Parametric DSL. Any LLM or generator following this specification will produce valid, syntactically and geometrically correct CAD timelines that build reliably inside Autodesk Fusion 360 without errors.

---

## 1. Top-Level Structure

Every model definition must be a single valid JSON object with exactly two top-level keys:

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

## 4. Sketch Entities

A sketch operation contains an array of `entities`.

### 4.1. Center Rectangle (`center_rectangle`)
A rectangle centered symmetrically around a point. Automatically constrained and dimensioned.
```json
{
  "type": "center_rectangle",
  "center": [0, 0],
  "width": "box_width",
  "height": "box_length"
}
```
* **`center`**: `[x, y]` center coordinate.
* **`width`**: dimension along the sketch's horizontal axis.
* **`height`**: dimension along the sketch's vertical axis.

### 4.2. Circle (`circle`)
A full circle with diameter constraint.
```json
{
  "type": "circle",
  "center": ["bolt_r", 0],
  "diameter": "bolt_dia"
}
```
* **`center`**: `[x, y]` center coordinate.
* **`diameter`**: diameter expression or dimension.

### 4.3. Line (`line`)
A straight line segment between two 2D points.
```json
{
  "type": "line",
  "start": [0, 0],
  "end": ["flange_dia / 2", 0]
}
```

### 4.4. Polyline (`polyline`)
A series of connected line segments. Used primarily as **sweep paths** or open spines.
```json
{
  "type": "polyline",
  "points": [
    [0, "pipe_len"],
    [0, 0],
    ["pipe_len", 0]
  ],
  "closed": false
}
```
* **`points`**: Array of at least two `[x, y]` points.
* **`closed`**: Boolean (`false` for open paths, `true` if closed).

### 4.5. Polygon (`polygon`)
A closed planar polygon (e.g. triangles, brackets, gusset ribs).
```json
{
  "type": "polygon",
  "points": [
    [0, "pipe_len - flange_thick - 5 mm"],
    [0, 0],
    ["pipe_len - 5 mm", 0]
  ],
  "closed": true
}
```
* **`points`**: Array of at least three `[x, y]` points.
* **`closed`**: Defaults to `true`. Connects the last point back to the first point.

### 4.6. Regular Polygon (`regular_polygon`)
A regular polygon (e.g. a hex nut recess), built like Fusion's own polygon tool: corners on a construction circle, equal sides, the bottom side horizontal.
```json
{
  "type": "regular_polygon",
  "center": ["bolt_x", "bolt_y"],
  "sides": 6,
  "across_flats": "nut_af"
}
```
* **`center`**: `[x, y]` center coordinate.
* **`sides`**: Whole number from 3 to 64.
* **`across_flats`** or **`diameter`** *(exactly one)*: Distance between opposite flats, or the diameter of the circle through the corners.

### 4.7. Profile (`profile`)
A closed outline of straight and arc segments, end to end (a slot, a rounded tab, a gear tooth).
```json
{
  "type": "profile",
  "start": [0, 0],
  "segments": [
    {"to": ["slot_len", 0]},
    {"to": ["slot_len", "slot_w"], "through": ["slot_len + slot_w / 2", "slot_w / 2"]},
    {"to": [0, "slot_w"]},
    {"to": [0, 0], "through": ["-slot_w / 2", "slot_w / 2"]}
  ]
}
```
* **`start`**: `[x, y]` of the first corner.
* **`segments`**: Each goes from the previous corner `"to"` the next. With `"through"` it is a circular arc through that point; without, a straight line.
* **`closed`** *(optional)*: Defaults to `true`. If the last segment doesn't end at `start`, a straight line closes the outline.

### 4.8. Mirror (`mirror`)
Copies earlier entities of the same sketch across a line, like Fusion's sketch Mirror. Each copy is tied to its original by symmetry constraints about a construction line, so it follows every parameter change.
```json
{"type": "profile", "id": "right", "closed": false, "start": [0, 0], "segments": [
  {"to": ["w / 2", 0]}, {"to": ["w / 2", "h"]}, {"to": [0, "h"]}]},
{"type": "mirror", "id": "both", "entities": ["right"], "line": [[0, 0], [0, "h"]]}
```
* **`entities`**: IDs of entities defined earlier in the sketch. A mirror's own `id` names the originals plus the copies, so mirroring it again doubles everything (draw 1/4 of a symmetric outline, mirror it twice).
* **`line`**: Two points `[[x1, y1], [x2, y2]]` on the mirror line.
* Points on the line are shared with the copy, so an open chain that starts and ends on the line becomes one closed outline. A curve that is its own mirror image (a circle centered on the line) isn't copied.

---

## 5. Timeline Operations

The `timeline` is an array of objects. Each step must have an `"op"` field specifying one of the 12 supported operations.

### 5.1. `sketch`
Creates a planar sketch containing 2D geometric entities.
```json
{
  "op": "sketch",
  "id": "bracket_sk",
  "plane": "xy",
  "offset": "0 mm",
  "entities": [
    {"type": "line", "id": "arm1", "start": [0, 0], "end": ["arm_len", 0]},
    {"type": "line", "id": "arm2", "start": ["arm_len", 0], "end": ["arm_len", "leg_len"]},
    {"type": "circle", "id": "hole", "center": [0, 0], "diameter": "hole_dia"}
  ],
  "constraints": [
    {"type": "perpendicular", "entities": ["arm1", "arm2"]},
    {"type": "equal", "entities": ["arm1", "arm2"]}
  ]
}
```
* **`id`** *(required string)*: Unique identifier used by subsequent 3D operations.
* **`plane`** *(required string)*: `"xy"`, `"xz"`, or `"yz"`.
* **`offset`** *(optional length)*: Distance along the plane's normal vector. Defaults to `0`.
* **`entities`** *(required array)*: Non-empty list of sketch entities. Any entity can have an optional `"id"` to be referenced by constraints.
* **`constraints`** *(optional array)*: Explicit geometric constraints between sketch entities.
  - `{"type": "perpendicular", "entities": ["l1", "l2"]}`: Right angle between two lines.
  - `{"type": "parallel", "entities": ["l1", "l2"]}`: Parallel orientation.
  - `{"type": "concentric", "entities": ["c1", "c2"]}`: Shared center between circles/arcs.
  - `{"type": "tangent", "entities": ["l1", "arc1"]}`: Tangent transition.
  - `{"type": "equal", "entities": ["e1", "e2"]}`: Equal lengths or diameters.
  - `{"type": "coincident", "entities": ["p1", "p2"]}`: Coincident points.
  - `{"type": "midpoint", "point": "p1", "entity": "l1"}`: Point constrained to curve midpoint.
  - `{"type": "symmetry", "entities": ["l1", "l2"], "symmetry_line": "centerline"}`: Symmetry across a line.

> **Note on Constraint Automation**: Sketches are constrained the way a person would do it, and geometry is never fixed, so changing a parameter later moves it. Rectangles get horizontal/vertical sides, a center on a construction diagonal and width/height dimensions. Axis-aligned segments of lines, polylines and polygons get horizontal/vertical constraints and a length dimension; any coordinate still free gets a distance from the origin (or alignment with it when it is 0). Explicit `constraints` are optional; use them for intent the coordinates don't show, such as angled features.

### 5.2. `extrude`
Extrudes all closed profiles in the sketch along the sketch normal.
```json
{
  "op": "extrude",
  "id": "flange_body",
  "sketch": "flange_sk",
  "distance": "flange_thick",
  "mode": "new_body"
}
```
* **`sketch`** *(required string)*: ID of a sketch defined earlier.
* **`distance`** *(required length)*: Extrusion depth. Positive follows plane normal; negative goes opposite.
* **`mode`** *(optional string)*: `"new_body"` (default), `"join"`, `"cut"`, or `"intersect"`.
* **`id`** *(optional string)*: Identifier to reference this feature later (for patterns, threads, or mirrors).

### 5.3. `revolve`
Revolves sketch profiles around a coordinate axis.
```json
{
  "op": "revolve",
  "id": "pulley_body",
  "sketch": "profile_sk",
  "axis": "z",
  "angle": "360 deg",
  "mode": "new_body"
}
```
* **`sketch`** *(required string)*: Sketch ID containing closed profile(s).
* **`axis`** *(optional string)*: `"x"`, `"y"`, or `"z"` (defaults to `"z"`).
* **`angle`** *(optional angle)*: Revolution sweep angle. Defaults to `"360 deg"`.
* **`mode`** *(optional string)*: `"new_body"`, `"join"`, or `"cut"`.

### 5.4. `sweep`
Sweeps a 2D profile sketch along a 3D path sketch.
```json
{
  "op": "sweep",
  "id": "pipe_body",
  "sketch": "pipe_profile_sk",
  "path": "pipe_path_sk",
  "mode": "new_body"
}
```
* **`sketch`** *(required string)*: Sketch containing the closed cross-section profile.
* **`path`** *(required string)*: Sketch containing the guide curve/polyline.
* **`mode`** *(optional string)*: `"new_body"`, `"join"`, or `"cut"`.

### 5.5. `fillet`
Rounds sharp edges of a solid body.
```json
{
  "op": "fillet",
  "radius": "corner_r",
  "edges": "vertical",
  "target": "outer_body"
}
```
* **`radius`** *(required length)*: Fillet radius expression.
* **`edges`** *(optional string or object)*: Edge selector filter:
  * `"vertical"`: Edges parallel to the Z axis.
  * `"top"`: Edges situated at the maximum Z extent.
  * `"bottom"`: Edges situated at the minimum Z extent.
  * `"circular"`: All circular/arc edges (e.g. rims of cylinders).
  * `"all"`: All edges of the body.
  * An object picks edges by the step that made them, and can narrow them down:
    * `"feature"`: ID of an earlier step; only edges of the faces it made (as they are now, after later steps).
    * `"faces"`: `"all"` (default), `"side"`, `"start"` or `"end"` faces of that step (for an extrude, `"side"` is a hole's bore).
    * `"exclude"`: ID (or list of IDs) of steps whose faces the edge must not touch.
    * `"on"`: ID of an earlier sketch; only edges lying in that sketch's plane (the rims where a hole meets the face it was sketched on).
    * `"type"` (`"circle"` or `"line"`), `"at"` (`"top"` or `"bottom"`) and `"direction"` (`"x"`, `"y"`, `"z"`) filter further.

    Chamfer only the outside rims of screw holes, not the rims inside a pocket:
    ```json
    {"op": "chamfer", "distance": "1.5 mm",
     "edges": {"feature": "screw_cut", "type": "circle", "exclude": "pocket_cut"}}
    ```
* **`target`** *(optional string)*: Target body name or feature ID. Defaults to the active body.

> [!WARNING]
> Never put `thickness` or `remove_faces` in a `fillet` step! Shell and Fillet are strictly separate operations.

### 5.6. `chamfer`
Bevels edges of a solid body by a uniform distance.
```json
{
  "op": "chamfer",
  "distance": "1.5 mm",
  "edges": "circular",
  "target": "boss_body"
}
```
* **`distance`** *(required length)*: Chamfer setback distance.
* **`edges`** *(optional)*: Same selectors as `fillet`, including the object form that picks edges by feature.

### 5.7. `shell`
Hollows out a solid body leaving walls of specified thickness, optionally removing open faces.
```json
{
  "op": "shell",
  "thickness": "wall_thick",
  "remove_faces": "top"
}
```
* **`thickness`** *(required length)*: Wall thickness.
* **`remove_faces`** *(optional string)*: Which face to open up:
  * `"top"`: Removes the highest planar face pointing in $+Z$ (creates an open container/box).
  * `"bottom"`: Removes the lowest planar face pointing in $-Z$.
  * `"none"`: Creates a completely hollow enclosed void inside the body.
  * `"all"`: Removes all matching planar faces.

### 5.8. `circular_pattern`
Replicates a feature or body circularly around an axis.
```json
{
  "op": "circular_pattern",
  "feature": "bolt_cut",
  "axis": "z",
  "quantity": "bolt_qty",
  "angle": "360 deg"
}
```
* **`feature`** *(optional string)*: Feature ID to duplicate. Defaults to the immediately preceding feature.
* **`axis`** *(optional string)*: `"x"`, `"y"`, or `"z"` (defaults to `"z"`).
* **`center`** *(optional point)*: Where the axis passes through, in the coordinates of the plane normal to it: `[x, y]` for `"z"`, `[y, z]` for `"x"`, `[x, z]` for `"y"`. Defaults to the origin. Use it for anything not centered on the origin, such as the second gear of a pair: `"center": ["center_dist", 0]`.
* **`quantity`** *(required)*: Number of instances including the original (must evaluate to a unitless integer $\ge 2$).
* **`angle`** *(optional angle)*: Total span angle. Defaults to `"360 deg"`.

### 5.9. `linear_pattern`
Replicates a feature along a linear coordinate axis with specified spacing.
```json
{
  "op": "linear_pattern",
  "feature": "fin_extrude",
  "direction": "x",
  "distance": "fin_pitch",
  "quantity": "fin_count"
}
```
* **`feature`** *(optional string)*: Feature ID to replicate.
* **`direction`** *(optional string)*: `"x"`, `"y"`, or `"z"` (defaults to `"x"`).
* **`distance`** *(required length)*: Step spacing between instances.
* **`quantity`** *(required)*: Total instance count.
* **`direction2`**, **`quantity2`**, **`distance2`** *(optional)*: A second direction (another axis), its count and spacing, for a grid of copies. Give all three.

### 5.10. `thread`
Applies real modeled 3D threads or cosmetic threads to cylindrical faces (holes or shafts).
```json
{
  "op": "thread",
  "feature": "port_cut",
  "target": "internal",
  "designation": "M20x2.5",
  "modeled": true
}
```
* **`feature`** *(optional string)*: Feature ID producing the cylindrical face (e.g., hole cut or shaft extrude).
* **`target`** *(optional string)*: `"internal"` (holes/bores), `"external"` (shafts/bolts), or `"all"`. Defaults to `"all"`.
* **`designation`** *(optional string)*: Metric designation (e.g. `"M6x1"`, `"M20x2.5"`). Must match the physical diameter of the hole/boss.
* **`modeled`** *(optional boolean)*: `true` generates physical 3D helical geometry (default); `false` generates a cosmetic texture.

### 5.11. `mirror`
Mirrors a feature or body across a symmetry plane.
```json
{
  "op": "mirror",
  "feature": "gusset_body",
  "plane": "xz",
  "combine": true
}
```
* **`feature`** *(optional string)*: Feature ID to mirror. If omitted, mirrors the main body.
* **`plane`** *(optional string)*: Symmetry plane (`"xy"`, `"xz"`, `"yz"`, or a face selector).
* **`combine`** *(optional boolean)*: When mirroring a body, `true` joins the mirrored half into a single solid body.

### 5.12. `combine` (Boolean Operation)
Executes Boolean Join, Cut, or Intersect between solid bodies.
```json
{
  "op": "combine",
  "target": "main_body",
  "tools": ["cutter_body"],
  "mode": "cut",
  "keep_tools": false
}
```
* **`target`** *(optional string)*: Target body name or feature ID.
* **`tools`** *(required array or string)*: Tool body name(s) or feature ID(s) acting on the target.
* **`mode`** *(optional string)*: `"cut"`, `"join"`, or `"intersect"`. Defaults to `"join"`.
* **`keep_tools`** *(optional boolean)*: Whether to preserve tool bodies after operation (`false` by default).

### 5.13. `coil` (Spring / Helix)
Generates a parametric 3D helical coil, compression/extension spring, or spiral wire body.
```json
{
  "op": "coil",
  "id": "main_spring",
  "axis": "z",
  "center": [0, 0, 0],
  "diameter": "coil_dia",
  "section_size": "wire_dia",
  "pitch": "coil_pitch",
  "revolutions": "coil_turns",
  "section": "circle",
  "clockwise": true,
  "mode": "new_body"
}
```
* **`diameter`** *(required length)*: Major/outer cylinder diameter of the coil helix. (Also accepts `"radius"`).
* **`section_size`** *(required length)*: Cross-section diameter / thickness of the wire. (Also accepts `"wire_dia"`).
* **`pitch`** *(optional length)*: Axial distance per turn (e.g. `"8 mm"`).
* **`revolutions`** *(optional count)*: Number of coil turns (e.g. `6` or `"6"`).
* **`height`** *(optional length)*: Total axial height of the coil.
  *(Any combination of `pitch`, `revolutions`, and `height` is automatically resolved: $H = \text{revolutions} \times \text{pitch}$).*
* **`axis`** *(optional string)*: Central axis of the helix (`"z"`, `"x"`, or `"y"`, default `"z"`).
* **`center`** *(optional point)*: Center origin coordinates `[x, y]` or `[x, y, z]` (defaults to `[0, 0, 0]`).
* **`diameter2`** *(optional length)*: End diameter at the top of the coil for conical/tapered springs.
* **`section`** *(optional string)*: Cross-section shape: `"circle"` (default) or `"square"`.
* **`clockwise`** *(optional boolean)*: `true` for standard right-hand helix (default), `false` for left-hand.
* **`mode`** *(optional string)*: `"new_body"` (default), `"join"`, `"cut"`, or `"intersect"`.

### 5.14. Shapes (plugin steps)
Ready-made parts, such as a spur gear, are plugins in the `shapes/` folder. Each adds its own step type (`"op"`), described to the model in the system prompt. VibeShaper turns such a step into ordinary parameters and steps before validating and building, so the timeline holds plain sketches, extrudes and patterns.

* **`id`** *(required)*: Names the finished part, so later steps can refer to it (for example in an edge selector). The parameters and steps a shape adds start with this id (`gear2_pitch_r`, `gear2_tooth_sk`...).
* The available shapes and their keys are listed in each plugin's `prompt` (see `shapes/`):
  * `spur_gear`: an involute spur gear.
  * `bolt_hole`: clearance holes for metric bolts (M2 to M12), with an optional counterbore, countersink or hex nut trap, sized from ISO tables.
  * `vent_grid`: round, hexagonal (honeycomb) or slot vent holes filling a rectangle; the hole count follows the area.
  * `tslot_profile`: an aluminum T-slot extrusion (2020, 2040, 3030, 4040...) with the real section: rounded corner blocks with lips, a core and bore in each cell, diagonal spars, T-shaped slots and hollows between cells.

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
