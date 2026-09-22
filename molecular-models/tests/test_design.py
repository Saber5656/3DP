import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from design import load_sdf, mirror, load_infinitene, build_mof, scaled_positions, methane, analyze_guest, clearance


class StructureTests(unittest.TestCase):
    def test_helicene_has_six_rings_and_a_nonplanar_mirror(self):
        m = load_sdf(ROOT / "sources/helicene.sdf")
        self.assertEqual(m["formula"], "C26H16")
        self.assertEqual(len(m["elements"]), 26)
        self.assertEqual(len(m["bonds"]), 31)
        p = np.array(m["positions"])
        q = np.array(mirror(m)["positions"])
        self.assertGreater(np.linalg.svd(p-p.mean(0))[1][-1], 1)
        np.testing.assert_allclose(np.linalg.norm(p[:,None]-p[None,:],axis=2),
                                   np.linalg.norm(q[:,None]-q[None,:],axis=2))
        # A reflection cannot be reproduced by a proper rotation (same atom correspondence).
        u, _, vt = np.linalg.svd((p-p.mean(0)).T @ (q-q.mean(0)))
        self.assertLess(np.linalg.det(u @ vt), 0)

    def test_caffeine_preserves_heteroatoms(self):
        m = load_sdf(ROOT / "sources/caffeine.sdf")
        self.assertEqual(m["formula"], "C8H10N4O2")
        self.assertEqual(m["elements"].count("N"), 4)
        self.assertEqual(m["elements"].count("O"), 2)
        self.assertEqual(len(m["bonds"]), 15)

    def test_infinitene_is_one_correct_carbon_network(self):
        m = load_infinitene(ROOT / "sources")
        self.assertEqual(m["formula"], "C48H24")
        self.assertEqual(len(m["elements"]), 48)
        self.assertEqual(len(m["bonds"]), 60)
        degrees = np.bincount(np.array(m["bonds"]).flatten(), minlength=48)
        self.assertEqual(sorted(degrees.tolist()), [2]*24+[3]*24)
        # The graph must form one component; stacked aromatic faces are not bonded.
        found={0}
        for _ in range(48):
            for a,b in m["bonds"]:
                if a in found or b in found: found.update((a,b))
        self.assertEqual(len(found), 48)

    def test_mof_has_real_clusters_and_linkers(self):
        m = build_mof(ROOT / "sources/IRMOF-1.cif", cells=2)
        self.assertEqual(m["cluster_count"], 27)
        self.assertEqual(m["linker_count"], 54)
        self.assertEqual(m["elements"].count("Zn"), 108)
        self.assertEqual(m["elements"].count("C"), 432)
        self.assertEqual(m["elements"].count("O"), 243)
        self.assertEqual(m["unit_cell_counts"], {"C":192,"O":104,"H":96,"Zn":32})

    def test_scaling_and_guest_containment(self):
        m = build_mof(ROOT / "sources/IRMOF-1.cif", cells=2)
        p, factor = scaled_positions(m, 150, atom_radius=2.7)
        self.assertAlmostEqual(float(np.ptp(p,axis=0).max()+5.4),150,places=5)
        result = analyze_guest(m, p, factor)
        self.assertGreater(result["central_clearance_mm"], 1)
        self.assertGreater(result["retention_margin_mm"], 1)
        self.assertEqual(len(methane()["elements"]), 5)
        centers=(np.array(m["cluster_centers"])-np.array(m["positions"]).mean(0))*factor
        guest_center=np.array(result["center_mm"])
        # It is a pore centre equidistant from eight adjacent nodes, not a node.
        distances=np.linalg.norm(centers-guest_center,axis=1)
        self.assertEqual(np.count_nonzero(np.isclose(distances,distances.min())),8)
        # Independent finer, off-grid samples must remain below the stated bound.
        rng=np.random.default_rng(20260921)
        lo,hi=centers.min(0),centers.max(0)
        for axis in range(3):
            for boundary in [lo[axis],hi[axis]]:
                points=rng.uniform(lo,hi,size=(300,3));points[:,axis]=boundary
                measured=clearance(points,p,m["elements"],m["bonds"])
                self.assertLessEqual(measured.max(),result["aperture_radius_upper_bound_mm"])

    def test_clearance_analytic_ball_and_capsule(self):
        # A single C ball has radius 2.2 mm.
        np.testing.assert_allclose(clearance([[0,0,5],[0,0,1]],[[0,0,0]],["C"],[]),[2.8,-1.2])
        # Midpoint of long bond: distance to the bond capsule is the nearest surface.
        result=clearance([[0,4,0]],np.array([[-10,0,0],[10,0,0]]),["C","C"],[[0,1]],bond_radius=1.65)
        self.assertAlmostEqual(result[0],2.35)


if __name__ == "__main__":
    unittest.main()
