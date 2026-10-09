# Quality audit tools

Machine-checkable, read-only checks for print quality/waste issues that
would otherwise only be noticed by eyeballing a slice preview.

## print_audit.py — multi-color / prime-tower waste detector

`../print_audit.py` is a standard-library-only Python CLI that parses a
sliced print's G-code (either a bare `.gcode` file, or the plate G-code
embedded in a `.gcode.3mf`/`.3mf` archive) and reports, per layer and per
filament, how much was actually extruded on the body ("model"), supports,
prime tower, brim/skirt, and "Custom" (priming/macro/scaffold) sections.

It exists to catch, mechanically, the kind of waste a human has to
notice by eye: e.g. the slicer building prime-tower mass on layers where
no print-color change occurred that layer, or unnecessary multi-color
surface layers appearing earlier/more often than intended.

### Usage

```
python3 tools/print_audit.py path/to/plate.gcode.3mf --base-color-id 0 --max-no-change-tower-g 0.1 --output report.json
```

- `--base-color-id` (default `0`): the filament id (0-based, matching
  `filament_colour`/`filament_density` order) treated as the base/dominant
  color, used to compute "first non-base color" and tower-before-that
  figures.
- `--output`: optional path to write the full JSON report. A short
  summary is always printed to stdout.
- `--max-no-change-tower-g`: selected budget for tower extrusion on layers
  with no deposition-stream color change. Exit 2 means budget exceeded or
  required mass data unresolved; inspect `waste_check.passed`, not `status`.
  No argument leaves the tool in report-only mode. Multiple plates are rejected
  instead of silently analyzing only the first.
- `nozzle_filament_replacement_count` tracks each nozzle's last material,
  including when another nozzle was used between visits. This separates
  real material replacement from nozzle switching. The sliced `group_id`
  assignment takes precedence over a project Auto mapping when available.

### What it parses

Bambu Studio G-code comments and commands only: `; CHANGE_LAYER`,
`; Z_HEIGHT:`, `; FEATURE:`, `T<n>` tool-select, `M82`/`M83`
(absolute/relative E), `G90`/`G91` (absolute/relative XY), `G92` (axis
reset), and `G0`/`G1`/`G2`/`G3` motion. It does not parse the 3D mesh and
does not open a GUI or talk to a printer — see `scope`/`limitations` in
every report for the exact boundaries, most importantly: extrusion mass
is a path-based estimate from positive-E, real-XY (or arc with I/J)
motion using nominal `filament_diameter`/`filament_density`, and is
**not** the same as the slicer's declared total (retraction/recovery and
firmware purge are not fully represented by that motion alone). Where the
two differ the report shows both numbers and the residual, rather than
claiming exact consumption.

Sentinel tool-select commands used for end-of-print parking (e.g.
`T65279`, `T65535` on Bambu X-series machines) are recognized and
excluded from color-change counting, as are any `T<n>` outside the
declared filament count when that count is known from
`project_settings.config`.

### Tests

`../tests/test_print_audit.py` (standard library `unittest`, no new
dependencies) covers: absolute/relative E accounting, `G92` E resets,
retraction moves, same-XY-endpoint arcs with `I`/`J` (full circles),
sentinel tool IDs, priming (E-only, no XY) vs. a real Custom-feature
scaffold move, prime-tower mass accumulated before the first real
non-base color, multi-color layer detection, unresolved-density
reporting, same-vs-different-nozzle color changes, and a smoke test that
runs the CLI against the real final print G-code when present in the
repo. Run with:

```
python3 -m unittest discover -s tools/tests -p test_print_audit.py -v
```

### Scope and limitations

- Offline, read-only, single-file analysis. No mesh inspection, no GUI,
  no network/printer communication.
- Extrusion-derived grams are an estimate (not a guaranteed lower bound), not an exact
  consumption figure; the declared slicer total and the residual are
  always reported alongside the computed figure instead of being merged.
- When `filament_density` is unavailable (raw `.gcode` input with no
  embedded `project_settings.config`, or a filament id missing density
  data), that filament's mass is reported as unresolved rather than
  guessed.
- The optional budget is only a waste check, not full print-quality approval.
  See [the 524 corrective comparison](../../models/524-keychain/statue-v7/README.md).
- `total_computed_grams_conservative` retains its initial field name for
  compatibility. Interpret it as a path-based estimate; it has no guaranteed
  lower-bound property. Initial preparation is separately tallied in mm.
