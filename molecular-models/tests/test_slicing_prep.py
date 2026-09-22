import json
import sys
import tempfile
import unittest
from pathlib import Path
import numpy as np
import trimesh
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from slicing_prep import resolve_preset, flatback, validate_presets


class SlicingPrepTests(unittest.TestCase):
    def test_inheritance_and_templates_are_resolved(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)
            for name,obj in {'base':{'density':1.24,'temp':200},'template':{'start':'G28','temp':210},'leaf':{'name':'leaf','inherits':'base','include':['template'],'temp':220}}.items():
                (p/(name+'.json')).write_text(json.dumps(obj))
            x=resolve_preset(p,'leaf')
            self.assertEqual(x['density'],1.24);self.assertEqual(x['start'],'G28');self.assertEqual(x['temp'],220)
            self.assertNotIn('include',x);self.assertNotIn('inherits',x)

    def test_flatback_preserves_top_and_gives_a_closed_contact_face(self):
        sphere=trimesh.creation.icosphere(subdivisions=2,radius=3.5)
        m=flatback(sphere)
        self.assertTrue(m.is_watertight);self.assertEqual(m.body_count,1)
        np.testing.assert_allclose(m.bounds, [[-3.5,-3.5,0],[3.5,3.5,3.5]],atol=1e-5)
        self.assertAlmostEqual(m.volume,sphere.volume/2,delta=.01)

    def test_incomplete_machine_defaults_are_rejected(self):
        with self.assertRaises(ValueError):
            validate_presets({'printer_model':'Bambu Lab X2D','machine_start_gcode':'G28'}, {'filament_density':['0']})


if __name__=='__main__':unittest.main()
