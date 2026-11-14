#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""回归与边界测试：四面体插值、保亮度色域收缩、S-Log3/矩阵及最终 21 个输出 LUT。"""

import glob
import os
import tempfile
import unittest

import colour
from colour.algebra import table_interpolation_tetrahedral
import numpy as np

import build_fuji_style
import lut_to_acr as m

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestTetrahedralAndCubeIO(unittest.TestCase):
    def test_grid_vertices_and_affine(self):
        n = 9
        idx = np.linspace(0.0, 1.0, n)
        B, G, R = np.meshgrid(idx, idx, idx, indexing="ij")
        coords = np.stack([R, G, B], axis=-1).reshape(-1, 3)

        # 仿射变换表（四面体插值必须精确重建任意仿射函数）
        mat = np.array([
            [0.6, 0.2, 0.1],
            [0.1, 0.7, 0.15],
            [0.05, 0.25, 0.65],
        ])
        bias = np.array([0.03, -0.02, 0.04])
        table = (coords @ mat.T + bias).reshape(n, n, n, 3)

        # 格点精确性
        out_grid = m.sample_table_tetra(table, coords)
        np.testing.assert_allclose(out_grid, table.reshape(-1, 3), atol=1e-15)

        # 任意随机点仿射重建
        rng = np.random.default_rng(123)
        q = rng.random((1000, 3))
        out_q = m.sample_table_tetra(table, q)
        expected_q = q @ mat.T + bias
        np.testing.assert_allclose(out_q, expected_q, atol=1e-14)

    def test_all_branches_boundaries_continuity_and_colour_parity(self):
        rng = np.random.default_rng(7)
        table = rng.random((17, 17, 17, 3))
        table_rgb = np.transpose(table, (2, 1, 0, 3)).copy()

        # 覆盖 6 个四面体内部、相等面/棱、0/1 边界与越界输入
        pts = np.vstack([
            rng.random((4000, 3)),
            np.array([
                [0.0, 0.0, 0.0], [1.0, 1.0, 1.0],
                [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0],
                [0.5, 0.5, 0.5], [0.25, 0.25, 0.25],
                [0.42, 0.42, 0.17], [0.42, 0.17, 0.42], [0.17, 0.42, 0.42],
                [0.17, 0.17, 0.83], [0.17, 0.83, 0.17], [0.83, 0.17, 0.17],
                [1.0, 0.37, 0.61], [0.37, 1.0, 0.61], [0.37, 0.61, 1.0],
                [-0.2, 0.5, 1.3],
            ]),
        ])
        got = m.sample_table_tetra(table, pts)
        ref = table_interpolation_tetrahedral(np.clip(pts, 0.0, 1.0), table_rgb)
        np.testing.assert_allclose(got, ref, atol=1e-15)

        # 跨越相等边界面 x == y 的 C0 连续性
        eps = 1e-10
        base = np.array([[0.33, 0.33, 0.19], [0.33, 0.33, 0.77], [0.33, 0.33, 0.33]])
        delta = np.array([[eps, 0.0, 0.0]])
        diff = np.abs(
            m.sample_table_tetra(table, base + delta)
            - m.sample_table_tetra(table, base - delta)
        )
        self.assertLess(diff.max(), 1e-8)

        # 轴置换对称性（RGB -> GBR）
        table_perm = np.transpose(table, (0, 2, 1, 3))  # [B, G, R] -> swap G,R in table axes
        # 完整置换 [B,G,R] -> [R,B,G] 等效输入 (r,g,b) -> (g,b,r)
        perm_idx = [1, 2, 0]
        # 原 table 索引为 [b, g, r]，新表要求在 (r', g', b') = (g, b, r) 处取原 (r, g, b)
        # 即 new_table[b', g', r'] = new_table[r, b, g] = table[b, g, r]
        new_table = np.transpose(table, (2, 0, 1, 3))
        q_perm = pts[:, perm_idx]
        np.testing.assert_allclose(
            m.sample_table_tetra(new_table, q_perm), got, atol=1e-15
        )

    def test_rejects_non_finite_coords(self):
        table = np.zeros((4, 4, 4, 3))
        with self.assertRaises(ValueError):
            m.sample_table_tetra(table, np.array([[0.5, np.nan, 0.5]]))
        with self.assertRaises(ValueError):
            m.sample_table(table, np.array([[0.5, np.inf, 0.5]]))

    def test_read_cube_rejects_zero_domain_span(self):
        with tempfile.NamedTemporaryFile("w", suffix=".cube", delete=False) as tf:
            tf.write("LUT_3D_SIZE 2\nDOMAIN_MIN 0.5 0.0 0.0\nDOMAIN_MAX 0.5 1.0 1.0\n")
            for _ in range(8):
                tf.write("0.0 0.0 0.0\n")
            path = tf.name
        try:
            with self.assertRaises(ValueError):
                m.read_cube(path)
        finally:
            os.remove(path)


class TestLuminancePreservationAndColorMath(unittest.TestCase):
    def test_preserve_luminance_in_gamut_and_projection(self):
        lin_in = np.array([
            [0.5, 0.5, 0.5],     # in-gamut neutral
            [0.8, 0.4, 0.2],     # in-gamut scaled
            [0.7, 0.7, 0.7],     # high-luminance input + saturated red look -> clips without fix
            [0.2, 0.8, 0.2],     # saturated green -> checks G upper bound
            [0.05, 0.02, 0.01],  # crushed black in look (y_look == 0)
            [1.0, 1.0, 1.0],     # pure white must stay (1, 1, 1)
            [0.0, 0.0, 0.0],     # pure black must stay (0, 0, 0)
        ])
        lin_look = np.array([
            [0.4, 0.4, 0.4],
            [0.45, 0.22, 0.11],
            [0.9, 0.05, 0.02],   # very saturated red at moderate Y_look
            [0.05, 0.9, 0.05],
            [0.0, 0.0, 0.0],     # crushed black
            [0.95, 0.9, 0.85],   # warm white look
            [0.02, 0.02, 0.02],  # lifted black look
        ])
        out = m.preserve_luminance(lin_in, lin_look)
        self.assertTrue(np.all((out >= 0.0) & (out <= 1.0)))

        y_in = lin_in @ m.REC709_LUM
        y_out = out @ m.REC709_LUM
        np.testing.assert_allclose(y_out, y_in, atol=1e-13)

        # 验证高饱和溢出色（索引 2）严格沿等亮度灰轴内缩，色相向量方向不变
        w2 = np.full(3, y_in[2])
        scaled2 = lin_look[2] * (y_in[2] / (lin_look[2] @ m.REC709_LUM))
        d_expected = scaled2 - w2
        d_actual = out[2] - w2
        ratio = d_actual / d_expected
        np.testing.assert_allclose(ratio, ratio[0], atol=1e-12)
        self.assertGreater(ratio[0], 0.0)
        self.assertLess(ratio[0], 1.0)

        # 验证被压黑的点（索引 4）回退为同亮度中性灰，不塌陷为 0
        np.testing.assert_allclose(out[4], np.full(3, y_in[4]), atol=1e-15)
        np.testing.assert_allclose(out[5], np.ones(3), atol=1e-15)
        np.testing.assert_allclose(out[6], np.zeros(3), atol=1e-15)

    def test_slog3_and_matrix_match_colour_science(self):
        lin = np.linspace(0.0, 2.0, 200)
        np.testing.assert_allclose(
            m.slog3_encode(lin),
            colour.models.log_encoding(lin, "S-Log3"),
            atol=1e-12,
        )
        np.testing.assert_allclose(
            m.slog3_decode(m.slog3_encode(lin)), lin, atol=1e-12
        )
        m_xyz_to_sgc = m.xyz_to_rgb(m.SGAMUT3CINE_PRIMARIES, m.D65_WHITE)
        np.testing.assert_allclose(
            m_xyz_to_sgc,
            colour.RGB_COLOURSPACES["S-Gamut3.Cine"].matrix_XYZ_to_RGB,
            atol=1e-9,
        )
        m_sgc, _ = m.conversion_matrices("srgb")
        ref_srgb = np.eye(3)
        ref_sgc = colour.RGB_to_RGB(ref_srgb, "sRGB", "S-Gamut3.Cine")
        # sRGB 矩阵在 colour 中使用标准四舍五入值，本实现由基色精确推导，差异 ~5.8e-5
        np.testing.assert_allclose(m_sgc, ref_sgc.T, atol=1e-4)

    def test_display_gamma_honored_in_preserve_mode(self):
        src = os.path.join(ROOT, "sources/sony_luts/Arri Neutral 65x.cube")
        if not os.path.exists(src):
            self.skipTest("missing source LUT")
        with tempfile.TemporaryDirectory() as td:
            p_srgb = os.path.join(td, "srgb.cube")
            p_24 = os.path.join(td, "g24.cube")
            m.convert(src, p_srgb, space="srgb", display_mode="srgb",
                      out_size=17, tone_mode="preserve")
            m.convert(src, p_24, space="srgb", display_mode="2.4",
                      out_size=17, tone_mode="preserve")
            _, t_srgb, _, _, _ = m.read_cube(p_srgb)
            _, t_24, _, _, _ = m.read_cube(p_24)
            self.assertGreater(np.abs(t_srgb - t_24).max(), 1e-3)


class TestGeneratedStyleOutputs(unittest.TestCase):
    def test_deployed_style_luts_valid_and_luminance_exact(self):
        outdir = os.path.join(ROOT, "output/acr_style")
        paths = sorted(glob.glob(os.path.join(outdir, "*.cube")))
        self.assertEqual(len(paths), 21)

        names = {os.path.basename(p) for p in paths}
        self.assertNotIn("Fuji FLog2-709 65 Style.cube", names)
        self.assertNotIn("Fuji WDR 65 Style.cube", names)
        self.assertEqual(len(build_fuji_style.MAPPING), 10)

        idx = np.linspace(0.0, 1.0, 64)
        B, G, R = np.meshgrid(idx, idx, idx, indexing="ij")
        inp = np.stack([R, G, B], axis=-1).reshape(-1, 3)
        y_in = m.decode_space(inp, "srgb") @ m.REC709_LUM

        for path in paths:
            size, tbl, dmin, dmax, title = m.read_cube(path)
            self.assertEqual(size, 64)
            self.assertEqual(title, os.path.splitext(os.path.basename(path))[0])
            np.testing.assert_allclose(dmin, 0.0, atol=1e-12)
            np.testing.assert_allclose(dmax, 1.0, atol=1e-12)
            self.assertGreaterEqual(tbl.min(), 0.0)
            self.assertLessEqual(tbl.max(), 1.0)

            y_out = m.decode_space(tbl.reshape(-1, 3), "srgb") @ m.REC709_LUM
            max_y_err = np.abs(y_out - y_in).max()
            self.assertLess(
                max_y_err, 1e-6,
                msg="%s luminance mismatch: %.8f" % (os.path.basename(path), max_y_err),
            )


if __name__ == "__main__":
    unittest.main()
