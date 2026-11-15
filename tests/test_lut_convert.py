#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""回归与边界测试：四面体插值、保亮度色域收缩、S-Log3/LogC/F-Log2 转换及输出 LUT。"""

import glob
import os
import tempfile
import unittest

import colour
from colour.algebra import table_interpolation_tetrahedral
import numpy as np

import build_arri_style
import build_film_style
import build_fuji_style
import build_sony26_style
import build_ultimate_style
import fuji_to_sony_lut
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

    def test_read_cube_parses_lut_3d_input_range(self):
        with tempfile.NamedTemporaryFile("w", suffix=".cube", delete=False) as tf:
            tf.write("LUT_3D_SIZE 2\nLUT_3D_INPUT_RANGE 0.064 0.94\n")
            for _ in range(8):
                tf.write("0.0 0.0 0.0\n")
            path = tf.name
        try:
            _, _, dmin, dmax, _ = m.read_cube(path)
            np.testing.assert_allclose(dmin, 0.064, atol=1e-12)
            np.testing.assert_allclose(dmax, 0.94, atol=1e-12)
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

    def test_flog2_to_slog3_mapping_neutral_and_gamut(self):
        slog18 = m.slog3_encode(0.18)
        flog18 = float(colour.models.log_encoding(0.18, "F-Log2"))
        domain = np.array([[0.0, 0.0, 0.0], [1.0, 1.0, 1.0]])
        mapped = fuji_to_sony_lut.map_slog3_samples_to_flog2(
            np.array([[slog18, slog18, slog18]]),
            "S-Gamut3.Cine",
            domain,
        )
        np.testing.assert_allclose(mapped[0], flog18, atol=1e-6)


class TestArriStyle(unittest.TestCase):
    def _make_achromatic_drt(self, path):
        # 恒等测试表（输入输出同轴，使线性输入灰轴在 Gamma 2.4 解码后保持中性）
        idx = np.linspace(0.0, 1.0, 9)
        B, G, R = np.meshgrid(idx, idx, idx, indexing="ij")
        tbl = np.stack([R, G, B], axis=-1)
        m.write_cube(path, tbl, "MockDRT")

    def test_logc4_look_chaining_and_luminance_preserve(self):
        with tempfile.TemporaryDirectory() as tmp:
            drt = os.path.join(tmp, "drt.cube")
            look = os.path.join(tmp, "look.cube")
            out = os.path.join(tmp, "ARRI Mock Style.cube")
            self._make_achromatic_drt(drt)

            # Look 表给红色通道略微增暖、蓝色略微抑制
            idx = np.linspace(0.0, 1.0, 9)
            B, G, R = np.meshgrid(idx, idx, idx, indexing="ij")
            ltbl = np.stack([np.clip(R * 1.05, 0.0, 1.0), G, B * 0.92], axis=-1)
            m.write_cube(look, ltbl, "WarmLook")

            build_arri_style.build(
                drt, out, gamut="ARRI Wide Gamut 4", log_name="ARRI LogC4",
                look_path=look, n=9, display_mode="2.4",
            )
            sz, tbl, dmin, dmax, title = m.read_cube(out)
            self.assertEqual(sz, 9)
            self.assertEqual(title, "ARRI Mock Style")
            np.testing.assert_allclose(dmin, 0.0, atol=1e-12)
            np.testing.assert_allclose(dmax, 1.0, atol=1e-12)

            b, g, r = np.meshgrid(idx, idx, idx, indexing="ij")
            inp = np.stack([r, g, b], axis=-1).reshape(-1, 3)
            y_in = m.decode_space(inp, "srgb") @ m.REC709_LUM
            y_out = m.decode_space(tbl.reshape(-1, 3), "srgb") @ m.REC709_LUM
            np.testing.assert_allclose(y_out, y_in, atol=1e-6)

            # 中灰格点应当呈现暖调（R > B）
            mid = tbl[4, 4, 4]
            self.assertGreater(mid[0], mid[2])

    def test_logc3_runs_without_nan(self):
        with tempfile.TemporaryDirectory() as tmp:
            drt = os.path.join(tmp, "drt3.cube")
            out = os.path.join(tmp, "ARRI LogC3 Mock Style.cube")
            self._make_achromatic_drt(drt)
            build_arri_style.build(
                drt, out, gamut="ARRI Wide Gamut 3", log_name="ARRI LogC3",
                n=9, display_mode="2.4",
            )
            _, tbl, _, _, _ = m.read_cube(out)
            self.assertTrue(np.all(np.isfinite(tbl)))
            self.assertGreaterEqual(tbl.min(), 0.0)
            self.assertLessEqual(tbl.max(), 1.0)

    def test_missing_source_returns_nonzero(self):
        with tempfile.TemporaryDirectory() as tmp:
            rc = build_arri_style.main(["-i", tmp, "-o", tmp])
            self.assertNotEqual(rc, 0)


class TestFilmAndVeniceStyle(unittest.TestCase):
    def test_venice_main_converts_and_preserves_luminance(self):
        with tempfile.TemporaryDirectory() as tmp:
            src_dir = os.path.join(tmp, "src")
            dst_dir = os.path.join(tmp, "dst")
            os.makedirs(src_dir)
            src = os.path.join(src_dir, "Slog3-S-Gamut3.Cine_To_s709_V200.cube")
            idx = np.linspace(0.0, 1.0, 9)
            B, G, R = np.meshgrid(idx, idx, idx, indexing="ij")
            tbl = np.stack([np.clip(R * 1.04, 0.0, 1.0), G, B * 0.94], axis=-1)
            m.write_cube(src, tbl, "MockVENICE")

            rc = build_film_style.main(["--venice-src", src_dir, "-o", dst_dir, "-n", "9"])
            self.assertEqual(rc, 0)
            out_path = os.path.join(dst_dir, "Sony VENICE s709 65 Style.cube")
            self.assertTrue(os.path.isfile(out_path))

            sz, res, _, _, title = m.read_cube(out_path)
            self.assertEqual(sz, 9)
            self.assertEqual(title, "Sony VENICE s709 65 Style")
            b, g, r = np.meshgrid(idx, idx, idx, indexing="ij")
            inp = np.stack([r, g, b], axis=-1).reshape(-1, 3)
            y_in = m.decode_space(inp, "srgb") @ m.REC709_LUM
            y_out = m.decode_space(res.reshape(-1, 3), "srgb") @ m.REC709_LUM
            np.testing.assert_allclose(y_out, y_in, atol=1e-6)

    def test_missing_sources_return_nonzero(self):
        with tempfile.TemporaryDirectory() as tmp:
            rc = build_film_style.main(["--venice-src", tmp, "-o", tmp])
            self.assertNotEqual(rc, 0)


class TestSony26PackStyle(unittest.TestCase):
    def test_curated_build_adds_prefix_preserves_luminance_and_supports_ev_offset(self):
        with tempfile.TemporaryDirectory() as tmp:
            src_dir = os.path.join(tmp, "src")
            dst_dir = os.path.join(tmp, "dst")
            os.makedirs(src_dir)
            idx = np.linspace(0.0, 1.0, 9)
            B, G, R = np.meshgrid(idx, idx, idx, indexing="ij")
            # 高暗区分色差异确保 ev_offset 会改变色相而亮度依然严格锁定
            tbl = np.stack([
                np.clip(R * (0.95 + 0.15 * B), 0.0, 1.0),
                G,
                np.clip(B * (0.9 + 0.1 * (1.0 - R)), 0.0, 1.0),
            ], axis=-1)
            for src_name, _, _ in build_sony26_style.CURATED_SPECS:
                m.write_cube(os.path.join(src_dir, src_name), tbl, "MockSony26")

            rc = build_sony26_style.main(["-i", src_dir, "-o", dst_dir, "-n", "9"])
            self.assertEqual(rc, 0)

            inp = np.stack([R, G, B], axis=-1).reshape(-1, 3)
            y_in = m.decode_space(inp, "srgb") @ m.REC709_LUM

            for _, label, _ in build_sony26_style.CURATED_SPECS:
                expected_name = build_sony26_style.output_filename(label)
                self.assertTrue(expected_name.startswith(build_sony26_style.PREFIX))
                out_path = os.path.join(dst_dir, expected_name)
                self.assertTrue(os.path.isfile(out_path))
                sz, res, _, _, title = m.read_cube(out_path)
                self.assertEqual(sz, 9)
                self.assertEqual(title, os.path.splitext(expected_name)[0])
                y_out = m.decode_space(res.reshape(-1, 3), "srgb") @ m.REC709_LUM
                np.testing.assert_allclose(y_out, y_in, atol=1e-6)

            # Quirky 使用 ev_offset=0.5，与 ev_offset=0.0 的同名源表应产生可测差异但同保亮度
            ev0_out = os.path.join(tmp, "ev0.cube")
            ev5_out = os.path.join(dst_dir, build_sony26_style.output_filename("Quirky Pro400H Style"))
            m.convert(os.path.join(src_dir, "Quirky_33x.cube"), ev0_out,
                      space="srgb", tone_mode="preserve", display_mode="srgb", out_size=9, ev_offset=0.0)
            _, tbl0, *_ = m.read_cube(ev0_out)
            _, tbl5, *_ = m.read_cube(ev5_out)
            self.assertGreater(np.abs(tbl5 - tbl0).max(), 1e-3)

    def test_missing_sources_return_nonzero(self):
        with tempfile.TemporaryDirectory() as tmp:
            rc = build_sony26_style.main(["-i", tmp, "-o", tmp])
            self.assertNotEqual(rc, 0)


class TestUltimateStyle(unittest.TestCase):
    def test_build_luminance_neutrality_and_monotonic_hues(self):
        with tempfile.TemporaryDirectory() as tmp:
            rc = build_ultimate_style.main(["-o", tmp, "-n", "17"])
            self.assertEqual(rc, 0)

            inp = m.uniform_grid(17)
            y_in = m.decode_space(inp, "srgb") @ m.REC709_LUM

            hues = np.linspace(0.0, 2.0 * np.pi, 72, endpoint=False)
            ring_lin = np.clip(0.22 + 0.14 * np.stack([
                np.cos(hues),
                np.cos(hues - 2.0 * np.pi / 3.0),
                np.cos(hues + 2.0 * np.pi / 3.0),
            ], axis=-1), 0.01, 0.98)
            ring_in = m.encode_space(ring_lin, "srgb")

            tables = {}
            for out_name in build_ultimate_style.OUTPUT_NAMES:
                out_path = os.path.join(tmp, out_name)
                self.assertTrue(os.path.isfile(out_path))

                sz, tbl, dmin, dmax, title = m.read_cube(out_path)
                self.assertEqual(sz, 17)
                self.assertEqual(title, os.path.splitext(out_name)[0])
                np.testing.assert_allclose(dmin, 0.0, atol=1e-12)
                np.testing.assert_allclose(dmax, 1.0, atol=1e-12)

                y_out = m.decode_space(tbl.reshape(-1, 3), "srgb") @ m.REC709_LUM
                np.testing.assert_allclose(y_out, y_in, atol=1e-6)

                # 360° 色环无色相反转
                ring_out = m.decode_space(m.sample_table_tetra(tbl, ring_in), "srgb")
                ok_ring = build_ultimate_style._lin_to_oklab(ring_out)
                ang = np.degrees(np.arctan2(ok_ring[:, 2], ok_ring[:, 1])) % 360.0
                diffs = (np.roll(ang, -1) - ang + 180.0) % 360.0 - 180.0
                self.assertTrue(np.all(diffs > 0.0))

                if out_name == build_ultimate_style.OUTPUT_NAME:
                    # CrystalFilm 中灰与高光灰必须保持纯中性无色罩
                    neutrals = m.sample_table_tetra(tbl, np.array([[0.50, 0.50, 0.50], [0.85, 0.85, 0.85]]))
                    self.assertLess(float(np.max(neutrals.max(axis=1) - neutrals.min(axis=1))), 1e-3)
                else:
                    # AnalogFilm 必须呈冷青暗部与暖象牙高光分离调性
                    shadow_gray = m.sample_table_tetra(tbl, np.array([[0.10, 0.10, 0.10]]))[0]
                    high_gray = m.sample_table_tetra(tbl, np.array([[0.85, 0.85, 0.85]]))[0]
                    self.assertGreater(float(shadow_gray[2] - shadow_gray[0]), 0.008)
                    self.assertGreater(float(high_gray[0] - high_gray[2]), 0.008)

                tables[out_name] = tbl

            self.assertGreater(
                float(np.max(np.abs(tables[build_ultimate_style.OUTPUT_NAMES[1]] - tables[build_ultimate_style.OUTPUT_NAMES[0]]))),
                0.02,
            )


class TestGeneratedStyleOutputs(unittest.TestCase):
    def test_deployed_style_luts_valid_and_luminance_exact(self):
        outdir = os.path.join(ROOT, "output/acr_style")
        paths = sorted(glob.glob(os.path.join(outdir, "*.cube")))

        sony_dir = os.path.join(ROOT, "sources/sony_luts")
        has_sony = os.path.isdir(sony_dir)
        has_arri = os.path.isdir(os.path.join(ROOT, "sources/arri_official"))
        has_venice = os.path.isdir(os.path.join(ROOT, "sources/sony_venice_official"))
        has_sony26 = os.path.isdir(os.path.join(ROOT, "sources/sony_pack_20260928"))

        expected_names = set(build_ultimate_style.OUTPUT_NAMES)
        expected_names.update(f"{dst_name}.cube" for dst_name in build_fuji_style.MAPPING.values())
        if has_sony:
            for p in glob.glob(os.path.join(sony_dir, "*.cube")):
                stem = os.path.splitext(os.path.basename(p))[0]
                if not stem.startswith(("Fuji ", "Sony ")):
                    expected_names.add(f"{stem} Style.cube")
        if has_arri:
            expected_names.update(out_name for out_name, *_ in build_arri_style.ARRI_PRESETS)
        if has_venice:
            expected_names.update(build_film_style.VENICE_MAPPING.values())
        if has_sony26:
            expected_names.update(
                build_sony26_style.output_filename(label)
                for _, label, _ in build_sony26_style.CURATED_SPECS
            )

        names = {os.path.basename(p) for p in paths}
        self.assertEqual(len(paths), len(expected_names))
        self.assertEqual(names, expected_names)

        # 确认富士技术转换表（FLog2-709 / WDR）未被错误纳入 Style 输出
        self.assertNotIn("Fuji FLog2-709 65 Style.cube", names)
        self.assertNotIn("Fuji WDR 65 Style.cube", names)

        inp = m.uniform_grid(64)
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
