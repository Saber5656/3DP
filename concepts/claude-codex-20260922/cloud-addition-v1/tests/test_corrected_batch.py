"""Synthetic file fixtures test batching only; no CLI or real slicing is invoked."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('prepare_corrected_batch', ROOT / 'prepare_corrected_batch.py')
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)


def make_fixture(root):
    """Manifests resemble real exports; fake STL bytes are never sliced."""
    root = Path(root)
    new = root / 'cloud-addition-v1'
    old = root / 'production-v1'
    manifests = []
    for folder, counts in [(new, {'A1': 4, 'A2': 4, 'A3': 4, 'A4': 4}),
                           (old, {'D1': 2, 'D2': 3, 'D3': 5, 'D4': 6, 'B4': 7})]:
        (folder / 'output/stl').mkdir(parents=True)
        parts = []
        for design, count in counts.items():
            colors = ['orange', 'white', 'black', 'black'] if design.startswith('A') else (
                ['orange', 'white', 'black', 'black', 'black'] if design == 'D3' else (
                    ['orange', 'black', 'black', 'translucent_blue', 'white', 'white', 'black'] if design == 'B4' else ['gray'] * count))
            for index in range(count):
                ident = f'{design}_part_{index + 1}'
                path = folder / 'output/stl' / f'{ident}.stl'
                # Intentional same hashes for distinct files prove we keep two identical eyes.
                path.write_bytes(b'clearly synthetic STL fixture; no actual mesh')
                parts.append({'id': ident, 'design': design, 'part': f'part_{index + 1}',
                              'count': 1, 'color': colors[index], 'support_recommended': index == 0 or (design.startswith('A') and index == 1),
                              'stl': str(path.relative_to(folder)),
                              'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
        data = {'unit': 'mm', 'target_height_mm': 48, 'selected_ids': list(counts),
                'models': [{'id': key, 'parts': value, 'quantity': 1, 'height_mm': 48} for key, value in counts.items()],
                'parts': parts}
        path = folder / 'output/manifest.json'
        path.write_text(json.dumps(data))
        manifests.append(path)
    archive = root / 'claude-codex-48mm.zip'
    archive.write_bytes(b'old ZIP fixture; not an actual archive')
    preserved = {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
                 for path in old.rglob('*') if path.is_file()}
    preserved[archive.name] = hashlib.sha256(archive.read_bytes()).hexdigest()
    (new / 'preserved-files.json').write_text(json.dumps(preserved))
    return *manifests, archive


def change_manifest(path, mutate):
    data = json.loads(path.read_text())
    mutate(data)
    path.write_text(json.dumps(data))


class CorrectedBatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.new, self.old, self.archive = make_fixture(self.tmp.name)

    def test_exact_six_designs_28_parts_and_four_colors(self):
        plan = b.build_batch_plan(self.new, self.old)
        self.assertEqual(plan['design_ids'], ['A1', 'A2', 'A3', 'A4', 'B4', 'D3'])
        self.assertEqual(plan['part_count'], 28)
        self.assertEqual([plate['part_count'] for plate in plan['plates']], [7, 6, 14, 1])
        self.assertEqual([plate['support'] for plate in plan['plates']], [True, True, False, False])
        self.assertEqual([p['color_key'] for p in plan['plates']], ['white', 'orange', 'black', 'translucent_blue'])
        parts = [part for plate in plan['plates'] for part in plate['parts']]
        self.assertEqual(len({part['id'] for part in parts}), 28)
        self.assertFalse({'D1', 'D2', 'D4'} & {part['design'] for part in parts})
        self.assertEqual({part['sha256'] for part in parts}, {hashlib.sha256(b'clearly synthetic STL fixture; no actual mesh').hexdigest()})
        self.assertEqual(plan['physical_slot_binding'], 'NOT_SET')
        for plate in plan['plates']:
            self.assertEqual(plate['support'], any(part['support_recommended'] for part in plate['parts']))

    def test_rejects_tampered_stl(self):
        path = self.new.parent / 'stl/A1_part_1.stl'
        path.write_bytes(b'tampered')
        with self.assertRaisesRegex(ValueError, 'SHA256'):
            b.build_batch_plan(self.new, self.old)

    def test_rejects_missing_part_even_if_declared_count_altered(self):
        def mutate(data):
            data['parts'] = [p for p in data['parts'] if p['id'] != 'A2_part_4']
            next(m for m in data['models'] if m['id'] == 'A2')['parts'] = 3
        change_manifest(self.new, mutate)
        with self.assertRaisesRegex(ValueError, 'part count'):
            b.build_batch_plan(self.new, self.old)

    def test_rejects_duplicate_ids_and_duplicate_paths(self):
        for duplicate in ['id', 'stl']:
            with self.subTest(duplicate=duplicate):
                original = self.new.read_text()
                change_manifest(self.new, lambda data: data['parts'][1].update({duplicate: data['parts'][0][duplicate]}))
                with self.assertRaisesRegex(ValueError, 'Duplicate'):
                    b.build_batch_plan(self.new, self.old)
                self.new.write_text(original)

    def test_rejects_missing_design_and_extraneous_new_design(self):
        for name in ['A5', 'D1']:
            with self.subTest(name=name):
                original = self.new.read_text()
                change_manifest(self.new, lambda data: data['models'][0].update(id=name))
                with self.assertRaises(ValueError):
                    b.build_batch_plan(self.new, self.old)
                self.new.write_text(original)

    def test_rejects_stl_path_escape_and_bad_support_flag(self):
        original = self.new.read_text()
        change_manifest(self.new, lambda data: data['parts'][0].update(stl='../../production-v1/output/stl/D1_part_1.stl'))
        with self.assertRaisesRegex(ValueError, 'within'):
            b.build_batch_plan(self.new, self.old)
        self.new.write_text(original)
        change_manifest(self.new, lambda data: data['parts'][0].update(support_recommended='false'))
        with self.assertRaisesRegex(ValueError, 'boolean'):
            b.build_batch_plan(self.new, self.old)

    def test_rejects_wrong_quantity_color_or_height(self):
        mutations = [lambda d: d['parts'][0].update(count=2),
                     lambda d: d['parts'][0].update(color='gray'),
                     lambda d: d['parts'][0].update(color='white'),
                     lambda d: d.update(target_height_mm=60),
                     lambda d: d['models'][0].update(height_mm=47)]
        for mutate in mutations:
            original = self.new.read_text()
            change_manifest(self.new, mutate)
            with self.assertRaises(ValueError):
                b.build_batch_plan(self.new, self.old)
            self.new.write_text(original)

    def test_old_tree_and_zip_snapshot_detect_changed_added_removed(self):
        root = self.old.parent.parent
        before = b.snapshot_paths([root, self.archive])
        result = b.verify_preserved(before)
        self.assertEqual(result['status'], 'UNCHANGED')
        self.assertGreater(result['files_checked'], 23)
        target = root / 'output/stl/D1_part_1.stl'
        content = target.read_bytes()
        target.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'changed'):
            b.verify_preserved(before)
        target.write_bytes(content)
        added = root / 'extra.txt'
        added.write_text('unexpected')
        with self.assertRaisesRegex(ValueError, 'added'):
            b.verify_preserved(before)
        added.unlink()
        target.unlink()
        with self.assertRaisesRegex(ValueError, 'removed'):
            b.verify_preserved(before)
        target.write_bytes(content)
        self.archive.write_bytes(b'changed old zip')
        with self.assertRaisesRegex(ValueError, 'changed'):
            b.verify_preserved(before)

    def test_rejects_legacy_manifest_from_a_different_project(self):
        other_new, other_old, other_zip = make_fixture(Path(self.tmp.name) / 'other')
        with self.assertRaisesRegex(ValueError, 'sibling'):
            b.prepare_batch(self.new, other_old)

    def test_historical_baseline_is_checked_before_first_batch(self):
        self.archive.write_bytes(b'changed before the batch starts')
        with self.assertRaisesRegex(ValueError, 'changed'):
            b.prepare_batch(self.new, self.old)
        self.assertFalse((self.new.parent.parent / 'slice-work/corrected/preservation-before.json').exists())

    def test_parent_baseline_checks_artifacts_and_excludes_only_declared_transients(self):
        preserved = self.new.parent.parent / 'preserved-files.json'
        cache = self.old.parent.parent / '__pycache__'
        cache.mkdir()
        (cache / 'synthetic.pyc').write_bytes(b'transient')
        self.assertEqual(b.verify_preserved_files(preserved)['status'], 'UNCHANGED')
        added = self.old.parent.parent / 'new-artifact.txt'
        added.write_text('unexpected')
        with self.assertRaisesRegex(ValueError, 'added'):
            b.verify_preserved_files(preserved)

    def test_plan_only_never_loads_or_calls_slicer(self):
        with patch.object(b, '_load_slice_runner') as load:
            report = b.prepare_batch(self.new, self.old)
            load.assert_not_called()
        self.assertEqual(report['status'], 'PLANNED')
        work = self.new.parent.parent / 'slice-work/corrected'
        self.assertTrue((work / 'batch-plan.json').is_file())
        self.assertTrue((work / 'preservation-before.json').is_file())
        self.assertEqual((work / 'batch-plan.json').stat().st_mode & 0o777, 0o600)
        self.assertEqual(list(work.glob('*.3mf')), [])
        self.assertEqual(b.verify_preserved(json.loads((work / 'preservation-before.json').read_text()))['status'], 'UNCHANGED')

    def test_slice_is_explicit_groups_by_color_and_preserves_old_data(self):
        calls = []
        def fake_slice(paths, output, color, support=False):
            calls.append((paths, output, color, support))
            output.write_bytes(b'mocked sliced package')
            return {'estimated_seconds': 1, 'estimated_filament_g': 1, 'physical_print': 'NOT_RUN'}
        report = b.prepare_batch(self.new, self.old, execute=True, slice_runner=fake_slice)
        self.assertEqual(report['status'], 'OFFLINE_SLICED')
        self.assertEqual(len(calls), 4)
        self.assertEqual(sum(len(call[0]) for call in calls), 28)
        self.assertEqual({call[2] for call in calls}, {'white', 'orange', 'black', 'translucent_blue'})
        self.assertTrue(all('slice-work/corrected' in str(call[1]) for call in calls))
        self.assertEqual(report['preservation']['status'], 'UNCHANGED')
        runner = Mock()
        with self.assertRaises(FileExistsError):
            b.prepare_batch(self.new, self.old, execute=True, slice_runner=runner)
        runner.assert_not_called()

    def test_source_change_between_color_plates_stops_batch(self):
        calls = []
        def changing_runner(paths, output, color, support=False):
            calls.append(color)
            paths[0].write_bytes(b'new shape appeared after first color')
            return {'estimated_seconds': 1, 'estimated_filament_g': 1}
        with self.assertRaisesRegex(ValueError, 'SHA256 changed'):
            b.prepare_batch(self.new, self.old, execute=True, slice_runner=changing_runner)
        self.assertEqual(calls, ['white'])
        status = json.loads((self.new.parent.parent / 'slice-work/corrected/batch-status.json').read_text())
        self.assertEqual(status['status'], 'FAILED')
        self.assertEqual(status['preservation']['status'], 'UNCHANGED')

    def test_rerun_does_not_replace_old_baseline_after_modification(self):
        b.prepare_batch(self.new, self.old)
        work = self.new.parent.parent / 'slice-work/corrected'
        before = (work / 'preservation-before.json').read_bytes()
        self.archive.write_bytes(b'altered')
        with self.assertRaisesRegex(ValueError, 'changed'):
            b.prepare_batch(self.new, self.old)
        self.assertEqual((work / 'preservation-before.json').read_bytes(), before)

    def test_failures_retain_status_and_detect_old_data_mutation(self):
        def bad_runner(paths, output, color, support=False):
            self.archive.write_bytes(b'altered by fake runner')
            raise RuntimeError('synthetic slice failure')
        with self.assertRaisesRegex(ValueError, 'changed'):
            b.prepare_batch(self.new, self.old, execute=True, slice_runner=bad_runner)
        status = json.loads((self.new.parent.parent / 'slice-work/corrected/batch-status.json').read_text())
        self.assertEqual(status['status'], 'FAILED')
        self.assertIn('synthetic slice failure', status['error'])
        self.assertIn('changed', status['preservation_error'])


if __name__ == '__main__':
    unittest.main()
