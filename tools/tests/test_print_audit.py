"""Unit tests for tools/print_audit.py (unittest, standard library only)."""
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import print_audit  # noqa: E402


HEADER = (
    '; HEADER_BLOCK_START\n'
    '; total layer number: {layers}\n'
    '; total filament weight [g] : 10.00,5.00,1.00,1.00\n'
    '; filament_density: 1.24,1.26,1.26,1.22\n'
    '; filament_diameter: 1.75,1.75,1.75,1.75\n'
    '; filament: 1,2,3,4\n'
    '; HEADER_BLOCK_END\n'
)

SETTINGS = {
    'filament_diameter': ['1.75', '1.75', '1.75', '1.75'],
    'filament_density': ['1.24', '1.26', '1.26', '1.22'],
    'filament_map': ['1', '2', '1', '1'],
}


def write_gcode3mf(path: Path, body: str, layers=1, settings=SETTINGS):
    code = HEADER.format(layers=layers) + body
    with zipfile.ZipFile(path, 'w') as z:
        z.writestr('Metadata/plate_1.gcode', code)
        if settings is not None:
            z.writestr('Metadata/project_settings.config', json.dumps(settings))
    return code


class LoadGcodeTests(unittest.TestCase):
    def test_multi_plate_archive_is_rejected_instead_of_silently_auditing_one(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'two.3mf'
            with zipfile.ZipFile(p,'w') as z:
                z.writestr('Metadata/plate_1.gcode','')
                z.writestr('Metadata/plate_2.gcode','')
            with self.assertRaises(ValueError):
                print_audit.load_gcode(p)

    def test_reads_plain_gcode_file(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'plate.gcode'
            p.write_text('T0 H-1\nG1 X1 Y1 E1\n')
            code, settings, kind = print_audit.load_gcode(p)
            self.assertIn('T0', code)
            self.assertIsNone(settings)
            self.assertEqual(kind, 'raw-gcode')

    def test_reads_gcode_inside_3mf_zip(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'plate.gcode.3mf'
            write_gcode3mf(p, 'T0 H-1\n')
            code, settings, kind = print_audit.load_gcode(p)
            self.assertIn('T0', code)
            self.assertIsNotNone(settings)
            self.assertTrue(kind.startswith('zip:'))


class AuditFixtureTests(unittest.TestCase):
    def test_nozzle_replacement_remembers_color_across_other_nozzle_visits(self):
        report = self._audit('M83\n; CHANGE_LAYER\n; FEATURE: Outer wall\n'
                             'T0\nG1 X1 E1\nT1\nG1 X2 E1\nT2\nG1 X3 E1\n')
        # Main yellow -> Aux white -> Main orange still replaces Main's yellow.
        self.assertEqual(report['nozzle_filament_replacement_count'], 1)

    def test_unknown_tower_mass_cannot_pass_waste_budget(self):
        report = self._audit('M83\n; CHANGE_LAYER\n; FEATURE: Prime tower\n'
                             'T0\nG1 X1 E5\n',settings=None)
        self.assertFalse(print_audit.waste_check(report, .1)['passed'])

    def test_nonchanging_tower_fails_requested_budget(self):
        report = self._audit('M83\n; CHANGE_LAYER\n; FEATURE: Prime tower\n'
                             'T0\nG1 X1 E500\n')
        self.assertFalse(print_audit.waste_check(report, .1)['passed'])

    def _audit(self, body, layers=1, settings=SETTINGS, base_color_id=0):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'plate.gcode.3mf'
            write_gcode3mf(p, body, layers=layers, settings=settings)
            return print_audit.audit(p, base_color_id=base_color_id)

    def test_absolute_e_mode_length(self):
        # M82 = absolute E. Two moves each extrude 1mm of filament while
        # travelling 1mm in X: total model extrusion should be 2mm, not 3mm
        # (naive absolute-E-as-length would double count).
        body = (
            'M82\n'
            '; CHANGE_LAYER\n; Z_HEIGHT: 0.2\n'
            '; FEATURE: Outer wall\n'
            'T0 H-1\n'
            'G1 X1 Y0 E1\n'
            'G1 X2 Y0 E2\n'
        )
        report = self._audit(body)
        self.assertAlmostEqual(report['extrusion_mm_by_category_color']['model']['0'], 2.0)

    def test_relative_e_mode_length(self):
        body = (
            'M83\n'
            '; CHANGE_LAYER\n; Z_HEIGHT: 0.2\n'
            '; FEATURE: Outer wall\n'
            'T0 H-1\n'
            'G1 X1 Y0 E1\n'
            'G1 X2 Y0 E1\n'
        )
        report = self._audit(body)
        self.assertAlmostEqual(report['extrusion_mm_by_category_color']['model']['0'], 2.0)

    def test_g92_e_reset_does_not_inflate_absolute_e_length(self):
        # After G92 E0 the next absolute E value is a fresh delta from 0,
        # not from whatever E was before the reset.
        body = (
            'M82\n'
            '; CHANGE_LAYER\n; Z_HEIGHT: 0.2\n'
            '; FEATURE: Outer wall\n'
            'T0 H-1\n'
            'G1 X1 Y0 E5\n'
            'G92 E0\n'
            'G1 X2 Y0 E1\n'
        )
        report = self._audit(body)
        self.assertAlmostEqual(report['extrusion_mm_by_category_color']['model']['0'], 6.0)

    def test_retraction_move_not_counted_as_extrusion(self):
        # A pure E-retraction (no XY motion, negative E) must contribute
        # zero to any category length.
        body = (
            'M83\n'
            '; CHANGE_LAYER\n; Z_HEIGHT: 0.2\n'
            '; FEATURE: Outer wall\n'
            'T0 H-1\n'
            'G1 X1 Y0 E1\n'
            'G1 E-0.8 F1800\n'
            'G1 X2 Y0 E1\n'
        )
        report = self._audit(body)
        self.assertAlmostEqual(report['extrusion_mm_by_category_color']['model']['0'], 2.0)

    def test_same_xy_arc_with_ij_counts_as_real_path(self):
        # G2/G3 whose endpoint equals its start (a full circle) is still a
        # real toolpath when I/J is present.
        body = (
            'M83\n'
            '; CHANGE_LAYER\n; Z_HEIGHT: 0.2\n'
            '; FEATURE: Outer wall\n'
            'T0 H-1\n'
            'G1 X5 Y0 E0\n'
            'G2 X5 Y0 I-2 J0 E3\n'
        )
        report = self._audit(body)
        self.assertAlmostEqual(report['extrusion_mm_by_category_color']['model']['0'], 3.0)

    def test_sentinel_tool_ids_are_not_new_colors(self):
        body = (
            'M83\n'
            '; CHANGE_LAYER\n; Z_HEIGHT: 0.2\n'
            '; FEATURE: Outer wall\n'
            'T0 H-1\n'
            'G1 X1 Y0 E1\n'
            'T65279\n'
            'T65535\n'
            'G1 X2 Y0 E1\n'
        )
        report = self._audit(body)
        # Still all attributed to color 0; sentinels never became "color".
        self.assertAlmostEqual(report['extrusion_mm_by_category_color']['model']['0'], 2.0)
        self.assertEqual(report['tool_change_commands_sentinel_or_out_of_range'],
                          {'65279': 1, '65535': 1})
        self.assertEqual(report['print_color_change_event_count'], 0)

    def test_priming_extrusion_without_xy_motion_is_not_scaffold(self):
        # A bare "prime the nozzle" extrusion (E only, no XY) inside a
        # Custom section contributes zero path length anywhere.
        body = (
            'M83\n'
            '; CHANGE_LAYER\n; Z_HEIGHT: 0.2\n'
            '; FEATURE: Custom\n'
            'T0 H-1\n'
            'G1 E0.8 F1800\n'
        )
        report = self._audit(body)
        self.assertEqual(report['extrusion_mm_by_category_color'].get('custom', {}), {})

    def test_custom_scaffold_move_is_tallied_separately_from_model(self):
        # A Custom-feature purge/scaffold line that does move in XY is
        # real extrusion, but must land in its own "custom" bucket, not be
        # silently dropped nor mixed into "model".
        body = (
            'M83\n'
            '; CHANGE_LAYER\n; Z_HEIGHT: 0.2\n'
            '; FEATURE: Custom\n'
            'T0 H-1\n'
            'G1 X10 Y0 E2\n'
        )
        report = self._audit(body)
        self.assertAlmostEqual(report['extrusion_mm_by_category_color']['custom']['0'], 2.0)
        self.assertEqual(report['extrusion_mm_by_category_color'].get('model', {}), {})

    def test_tower_accumulates_before_first_real_color_change(self):
        # Layer 1: base color only on model + tower (no color change).
        # Layer 2: still base color only (no change) - tower keeps growing.
        # Layer 3: a real non-base model color appears for the first time.
        body = (
            'M83\n'
            '; CHANGE_LAYER\n; Z_HEIGHT: 0.2\n'
            '; FEATURE: Outer wall\nT0 H-1\nG1 X1 Y0 E1\n'
            '; FEATURE: Prime tower\nG1 X10 Y0 E5\n'
            '; CHANGE_LAYER\n; Z_HEIGHT: 0.4\n'
            '; FEATURE: Outer wall\nG1 X1 Y0 E1\n'
            '; FEATURE: Prime tower\nG1 X10 Y0 E5\n'
            '; CHANGE_LAYER\n; Z_HEIGHT: 0.6\n'
            '; FEATURE: Outer wall\nT1 H-1\nG1 X1 Y0 E1\n'
            '; FEATURE: Prime tower\nG1 X10 Y0 E5\n'
        )
        report = self._audit(body, layers=3)
        self.assertEqual(report['first_non_base_color_model_layer'], 3)
        self.assertEqual(report['tower_layer_count_before_first_non_base_color_model_layer'], 2)
        # 2 tower moves of 5mm each, PLA density 1.24: same formula as prod code.
        expected = print_audit.grams(5.0, 1.75, 1.24) * 2
        self.assertAlmostEqual(
            report['tower_grams_before_first_non_base_color_model_layer'], expected, places=6)
        # Layer 3 has a real color change (T0 -> T1), so it must not count
        # toward "layers without a color change".
        self.assertEqual(report['tower_layer_count_without_color_change'], 2)

    def test_multi_color_model_layer_detected(self):
        body = (
            'M83\n'
            '; CHANGE_LAYER\n; Z_HEIGHT: 0.2\n'
            '; FEATURE: Outer wall\nT0 H-1\nG1 X1 Y0 E1\n'
            'T1 H-1\nG1 X2 Y0 E1\n'
        )
        report = self._audit(body)
        self.assertEqual(report['multi_color_model_layers'], [1])
        self.assertEqual(report['multi_color_model_layer_count'], 1)

    def test_declared_vs_computed_residual_reported_separately(self):
        body = (
            'M83\n'
            '; CHANGE_LAYER\n; Z_HEIGHT: 0.2\n'
            '; FEATURE: Outer wall\nT0 H-1\nG1 X1 Y0 E1\n'
        )
        report = self._audit(body)
        self.assertEqual(report['total_declared_grams'], 17.0)  # header sum
        self.assertLess(report['total_computed_grams_conservative'], report['total_declared_grams'])
        self.assertAlmostEqual(
            report['residual_declared_minus_computed_grams'],
            report['total_declared_grams'] - report['total_computed_grams_conservative'])

    def test_unknown_density_is_reported_not_guessed(self):
        body = (
            'M83\n'
            '; CHANGE_LAYER\n; Z_HEIGHT: 0.2\n'
            '; FEATURE: Outer wall\nT0 H-1\nG1 X1 Y0 E1\n'
        )
        report = self._audit(body, settings=None)
        self.assertIsNone(report['filament_diameter_mm'])
        self.assertIn('0', report['unresolved_density_filament_ids'])
        self.assertEqual(report['extrusion_grams_by_category_color']['model'], {})

    def test_same_vs_different_nozzle_color_change_flagged(self):
        # filament_map = ['1','2','1','1']: id0/id2/id3 share nozzle 1,
        # id1 is on nozzle 2.
        body = (
            'M83\n'
            '; CHANGE_LAYER\n; Z_HEIGHT: 0.2\n'
            '; FEATURE: Outer wall\n'
            'T0 H-1\nG1 X1 Y0 E1\n'
            'T2 H-1\nG1 X2 Y0 E1\n'
            'T1 H-1\nG1 X3 Y0 E1\n'
        )
        report = self._audit(body)
        events = report['color_change_events']
        self.assertEqual(len(events), 2)
        self.assertTrue(events[0]['same_nozzle'])   # 0 -> 2, both nozzle '1'
        self.assertFalse(events[1]['same_nozzle'])  # 2 -> 1, nozzle '1' -> '2'

    def test_provenance_sha_and_scope_present(self):
        body = '; CHANGE_LAYER\n; Z_HEIGHT: 0.2\n; FEATURE: Outer wall\nT0 H-1\nG1 X1 Y0 E1\n'
        report = self._audit(body)
        self.assertEqual(len(report['source_sha256']), 64)
        self.assertIn('scope', report)
        self.assertTrue(report['limitations'])


class RealFileSmokeTest(unittest.TestCase):
    """Exercises the CLI against the actual final print G-code, if present."""

    TARGET = (Path(__file__).resolve().parents[2]
              / 'models/524-keychain/statue-v6/print-run-20260927'
              / '524-Keychain-v6-Blue-Mouth-GUI-Verified.gcode.3mf')

    def test_real_gcode3mf_parses_and_reports_findings(self):
        if not self.TARGET.exists():
            self.skipTest(f'fixture not present: {self.TARGET}')
        report = print_audit.audit(self.TARGET, base_color_id=0)
        self.assertEqual(report['status'], 'OK')
        self.assertGreater(report['layer_count'], 0)
        self.assertIsNotNone(report['first_non_base_color_model_layer'])
        self.assertGreaterEqual(report['tower_layer_count_without_color_change'], 0)


if __name__ == '__main__':
    unittest.main()
