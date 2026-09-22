"""Offline tests: genuine prior slice is read-only; small fixtures test parser branches."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[2]
spec = importlib.util.spec_from_file_location('slicing_support', ROOT / 'slicing_support.py')
s = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s)
GENUINE = REPO / 'models/ramiel/printing/star-v4/sliced-preview/black-stand.3mf'


class SlicingSupportTests(unittest.TestCase):
    def test_installed_presets_resolve_templates_density_and_intent(self):
        root = s.find_preset_root()
        machine = s.resolve_preset(root / 'machine', s.MACHINE_NAME)
        for color in s.COLORS:
            with tempfile.TemporaryDirectory() as tmp:
                bundle = s.prepare_settings(Path(tmp), color)
                process = json.loads(bundle['process'].read_text())
                filament = json.loads(bundle['filament'].read_text())
                actual_machine = json.loads(bundle['machine'].read_text())
                self.assertEqual(actual_machine['machine_start_gcode'], machine['machine_start_gcode'])
                self.assertEqual(actual_machine['machine_end_gcode'], machine['machine_end_gcode'])
                self.assertGreater(len(machine['machine_start_gcode']), 1000)
                self.assertEqual(machine['printer_model'], 'Bambu Lab X2D')
                self.assertGreater(float(filament['filament_density'][0]), 0)
                self.assertEqual(process['layer_height'], '0.16')
                self.assertEqual(process['wall_loops'], '3')
                self.assertEqual(process['sparse_infill_density'], '15%')
                self.assertEqual(process['sparse_infill_pattern'], 'gyroid')
                self.assertEqual(process['enable_support'], '0')
                self.assertEqual(process['enable_prime_tower'], '0')
                self.assertEqual(process['support_filament'], '0')
                self.assertEqual(process['support_interface_filament'], '0')
                self.assertEqual(filament['filament_colour'], [s.COLORS[color]['hex']])
                self.assertEqual(bundle['filament'].stat().st_mode & 0o777, 0o600)
        self.assertIn('Translucent', s.COLORS['translucent_blue']['preset'])

    def test_support_uses_same_material_on_build_plate(self):
        with tempfile.TemporaryDirectory() as tmp:
            bundle = s.prepare_settings(Path(tmp), 'white', support=True)
            data = json.loads(bundle['process'].read_text())
            self.assertEqual(data['enable_support'], '1')
            self.assertEqual(data['support_type'], 'tree(auto)')
            self.assertEqual(data['support_on_build_plate_only'], '1')
            self.assertEqual(data['support_filament'], '0')
            self.assertIn('enable_support', bundle['deltas'][0].split(';'))

    def test_inheritance_include_precedence_and_cycle(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name, data in {'base': {'a': 1}, 'extra': {'a': 2, 'b': 1},
                               'leaf': {'inherits': 'base', 'include': ['extra'], 'b': 3},
                               'cycle': {'inherits': 'cycle'}}.items():
                (root / f'{name}.json').write_text(json.dumps(data))
            self.assertEqual(s.resolve_preset(root, 'leaf'), {'a': 2, 'b': 3})
            with self.assertRaisesRegex(ValueError, 'cycle'):
                s.resolve_preset(root, 'cycle')

    def test_parser_excludes_macros_travel_and_retract_and_counts_arcs(self):
        # Synthetic fixture, not evidence that any model is printable.
        code = '''M83
G1 X20 Y20 E10
; CHANGE_LAYER
; Z_HEIGHT: 0.2
; OBJECT_ID: 4
; FEATURE: Outer wall
G1 X21 E1
G1 X22
G1 X23 E-1
G1 E1
G2 X24 Y21 I0 J1 E.2
M82
G92 E0
G1 X25 E.5
G1 X26 E.2
G91
G1 X1 E.6
G90
; CHANGE_LAYER
; Z_HEIGHT: 0.36
; FEATURE: Support
G1 X29 E1.6
; FEATURE: Custom
G1 X30 E12
'''
        report = s.summarize_gcode(code)
        self.assertEqual(report['layer_count'], 2)
        self.assertEqual(report['extrusion_moves'], 5)
        self.assertEqual(report['arc_extrusion_moves'], 1)
        self.assertEqual(report['support_extrusion_moves'], 1)
        self.assertEqual(report['layers'][0]['extrusion_moves'], 4)
        self.assertEqual(report['objects']['4']['first_layer'], 1)
        self.assertEqual(report['objects']['4']['last_layer'], 1)

    def test_genuine_prior_archive_metadata_and_real_extrusions(self):
        report = s.inspect_3mf(GENUINE)
        self.assertEqual(report['printer_model'], 'Bambu Lab X2D')
        self.assertEqual(report['layer_count'], 150)
        self.assertEqual(report['estimated_seconds'], 3406)
        self.assertEqual(report['estimated_filament_g'], 16.51)
        self.assertGreater(report['extrusion_moves'], 10000)
        self.assertEqual(report['support_extrusion_moves'], 0)
        self.assertEqual(report['empty_layers'], [])
        self.assertEqual(report['physical_print'], 'NOT_RUN')

    def mutated_archive(self, directory, change):
        path = Path(directory) / 'synthetic-mutated-prior.3mf'
        with zipfile.ZipFile(GENUINE) as src, zipfile.ZipFile(path, 'w') as dst:
            data = {name: src.read(name) for name in src.namelist()}
            change(data)
            for name, value in data.items():
                dst.writestr(name, value)
        return path

    def test_rejects_generic_machine_zero_density_and_multiple_materials(self):
        for key, value, message in [('printer_model', 'Generic', 'X2D'),
                                    ('filament_density', ['0'], 'density'),
                                    ('filament_colour', ['#000000', '#FFFFFF'], 'single')]:
            with self.subTest(key=key), tempfile.TemporaryDirectory() as tmp:
                def change(data):
                    cfg = json.loads(data['Metadata/project_settings.config'])
                    cfg[key] = value
                    data['Metadata/project_settings.config'] = json.dumps(cfg)
                with self.assertRaisesRegex(ValueError, message):
                    s.inspect_3mf(self.mutated_archive(tmp, change))

    def test_rejects_archive_without_real_extrusion(self):
        with tempfile.TemporaryDirectory() as tmp:
            def change(data):
                data['Metadata/plate_1.gcode'] = '; CHANGE_LAYER\nG1 X2 Y2\n'
            with self.assertRaisesRegex(ValueError, 'extrusion'):
                s.inspect_3mf(self.mutated_archive(tmp, change))

    def test_gui_delta_patch_leaves_all_other_archive_bytes_identical(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.mutated_archive(tmp, lambda data: None)
            deltas = ['wall_loops;sparse_infill_pattern', 'filament_colour', '']
            with zipfile.ZipFile(path) as src:
                before = {name: src.read(name) for name in src.namelist()}
            s.patch_gui_deltas(path, deltas)
            with zipfile.ZipFile(path) as dst:
                for name, old in before.items():
                    if name != 'Metadata/project_settings.config':
                        self.assertEqual(dst.read(name), old)
                cfg = json.loads(dst.read('Metadata/project_settings.config'))
                self.assertEqual(cfg['different_settings_to_system'], deltas)

    def test_command_preserves_orientation_and_uses_private_datadir(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bundle = s.prepare_settings(root / 'settings', 'orange')
            cmd = s.build_slice_command([root / 'part.stl'], root / 'out.3mf', bundle,
                                        root / 'profile', Path('/Applications/BambuStudio.app/Contents/MacOS/BambuStudio'))
            self.assertEqual(cmd[cmd.index('--orient') + 1], '0')
            self.assertEqual(cmd[cmd.index('--arrange') + 1], '1')
            self.assertEqual(cmd[cmd.index('--load-filament-ids') + 1], '1')
            self.assertIn('--ensure-on-bed', cmd)
            self.assertNotIn('--allow-rotations', cmd)
            self.assertIn('--datadir', cmd)
            self.assertNotIn('--allow-multicolor-oneplate', cmd)
            self.assertEqual(cmd[-1], str(root / 'part.stl'))

    def test_run_slice_missing_input_does_not_launch_cli(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(s.subprocess, 'run') as launch:
            with self.assertRaises(FileNotFoundError):
                s.run_slice([Path(tmp) / 'missing.stl'], Path(tmp) / 'out.3mf', 'white')
            launch.assert_not_called()

    def test_run_slice_publishes_validated_fixture_and_keeps_offline_evidence(self):
        # Mocked CLI with modified genuine archive: validates orchestration, not a new slice.
        import trimesh
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            part = root / 'part.stl'
            mesh = trimesh.creation.box([10, 10, 10])
            mesh.apply_translation([0, 0, 5])
            mesh.export(part)
            def fake_cli(argv, **kwargs):
                settings_path = Path(argv[argv.index('--load-settings') + 1].split(';')[1])
                filament_path = Path(argv[argv.index('--load-filaments') + 1])
                process = json.loads(settings_path.read_text())
                filament = json.loads(filament_path.read_text())
                def change(data):
                    cfg = json.loads(data[s.SETTINGS_ENTRY])
                    for key, value in process.items():
                        if key not in {'name', 'inherits', 'from', 'type', 'setting_id'}:
                            cfg[key] = value
                    cfg['filament_colour'] = filament['filament_colour']
                    data[s.SETTINGS_ENTRY] = json.dumps(cfg)
                fixture = self.mutated_archive(root, change)
                fixture.rename(Path(argv[argv.index('--export-3mf') + 1]))
                kwargs['stdout'].write('[warning] synthetic fixture warning\n')
                return s.subprocess.CompletedProcess(argv, 0)
            with patch.object(s.subprocess, 'run', side_effect=fake_cli) as launch:
                report = s.run_slice([part], root / 'output.3mf', 'black')
                self.assertEqual(launch.call_count, 1)
            self.assertTrue((root / 'output.3mf').is_file())
            self.assertEqual(report['estimated_seconds'], 3406)
            self.assertTrue(Path(report['evidence_dir'], 'report.json').is_file())
            self.assertTrue(report['warnings'])
            self.assertEqual(report['physical_slot_binding'], 'NOT_SET')
            before = (root / 'output.3mf').read_bytes()
            with patch.object(s.subprocess, 'run') as launch:
                with self.assertRaises(FileExistsError):
                    s.run_slice([part], root / 'output.3mf', 'black')
                launch.assert_not_called()
            self.assertEqual((root / 'output.3mf').read_bytes(), before)

    def test_failed_cli_does_not_publish_requested_output(self):
        import trimesh
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            mesh = trimesh.creation.box([10, 10, 10])
            mesh.apply_translation([0, 0, 5])
            part = root / 'part.stl'
            mesh.export(part)
            with patch.object(s.subprocess, 'run', return_value=s.subprocess.CompletedProcess([], 1)):
                with self.assertRaisesRegex(RuntimeError, 'failed'):
                    s.run_slice([part], root / 'output.3mf', 'white')
            self.assertFalse((root / 'output.3mf').exists())
            self.assertEqual(len(list(root.glob('.*-slicing-*/bambu-cli.log'))), 1)

    def test_off_bed_geometry_is_rejected_before_cli(self):
        import trimesh
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            part = root / 'part.stl'
            trimesh.creation.box([10, 10, 10]).export(part)
            with patch.object(s.subprocess, 'run') as launch:
                with self.assertRaisesRegex(ValueError, 'z=0'):
                    s.run_slice([part], root / 'output.3mf', 'white')
                launch.assert_not_called()

    def test_warning_parser_keeps_unknown_warning_and_support_context(self):
        warnings = s.extract_warnings('normal\n[warning] Influence area cannot expand\nInvalid T65279\n[error] new problem\n')
        self.assertEqual(len(warnings), 3)
        self.assertIn('Influence area', warnings[0])
        self.assertIn('Invalid T65279', warnings[1])


if __name__ == '__main__':
    unittest.main()
