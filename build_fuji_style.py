#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从富士官方 GFX LUT 包（F-Log2 / F-Gamut）构建 ACR 用 "Style" LUT。

链路（每个输出格点）:
    ACR sRGB 码 -> 解码线性 -> 转为 F-Gamut 线性（Bradford）
    -> F-Log2 编码 -> 采样官方 F-Log2 LUT
    -> 输出按显示伽马解码 -> 亮度替换为输入照片亮度（越界高饱和沿等亮度灰轴收缩）
    -> 编码写出

注：官方包中 FLog2_to_FLog2-709（F-Log2 -> F-Log2 技术色域转换）与
FLog2_to_WDR（Wide Dynamic Range 曲线）均非 Rec.709 显示级胶片模拟，不纳入 Style 构建。

需要：colour-science（.venv 中已装）
用法: .venv/bin/python build_fuji_style.py
"""
import argparse
import os
import sys
import numpy as np
import colour

import lut_to_acr as m

PACK = "sources/fuji_official/65Grid/F-Log2"
OUTDIR = "output/acr_style"

# 官方胶片模拟 LUT 文件 -> ACR 菜单名（排除 FLog2-709 / WDR 技术曲线）
MAPPING = {
    "FLog2_to_ACROS_65grid_V.1.00.cube": "Fuji ACROS 65 Style",
    "FLog2_to_ASTIA_65grid_V.1.00.cube": "Fuji ASTIA 65 Style",
    "FLog2_to_CLASSIC-CHROME_65grid_V.1.00.cube": "Fuji Classic Chrome 65 Style",
    "FLog2_to_CLASSIC-Neg._65grid_V.1.00.cube": "Fuji Classic Neg 65 Style",
    "FLog2_to_ETERNA-BB_65grid_V.1.00.cube": "Fuji Eterna BB 65 Style",
    "FLog2_to_ETERNA_65grid_V.1.00.cube": "Fuji Eterna 65 Style",
    "FLog2_to_PRO-Neg.Std_65grid_V.1.00.cube": "Fuji Pro Neg Std 65 Style",
    "FLog2_to_PROVIA_65grid_V.1.00.cube": "Fuji Provia 65 Style",
    "FLog2_to_REALA-ACE_65grid_V.1.00.cube": "Fuji Reala Ace 65 Style",
    "FLog2_to_Velvia_65grid_V.1.00.cube": "Fuji Velvia 65 Style",
}


def build(src, dst, n=64, display_mode="srgb"):
    _, table, dmin, dmax, _ = m.read_cube(src)
    idx = np.linspace(0.0, 1.0, n)
    B, G, R = np.meshgrid(idx, idx, idx, indexing="ij")
    codes = np.stack([R, G, B], axis=-1).reshape(-1, 3)

    lin_srgb = m.decode_space(codes, "srgb")
    lin_fgamut = colour.RGB_to_RGB(
        lin_srgb, "sRGB", "F-Gamut", chromatic_adaptation_transform="Bradford")
    flog2 = colour.models.log_encoding(lin_fgamut, "F-Log2")
    pos = (flog2 - dmin) / (dmax - dmin)
    look = np.clip(m.sample_table_tetra(table, pos), 0.0, 1.0)

    # 只保留颜色风格：亮度替换为输入照片亮度（越界高饱和沿灰轴保亮度收缩）
    lin_look = m.decode_display(look, display_mode)
    out_lin = m.preserve_luminance(lin_srgb, lin_look)
    out_codes = m.encode_space(out_lin, "srgb").reshape(n, n, n, 3)

    title = os.path.splitext(os.path.basename(dst))[0]
    m.write_cube(
        dst, out_codes, title,
        source_title=os.path.basename(src),
        note="Re-baked for Adobe Camera Raw (F-Log2/F-Gamut source LUT)",
    )
    print("built", dst)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="从富士官方 F-Log2 LUT 包构建 ACR Style LUT")
    ap.add_argument("--display-gamma", choices=m.DISPLAY_MODES, default="srgb",
                    help="源 LUT 输出（Rec.709）的显示解码方式（默认 srgb）")
    args = ap.parse_args(argv)

    os.makedirs(OUTDIR, exist_ok=True)
    for src_name, dst_name in MAPPING.items():
        src = os.path.join(PACK, src_name)
        if not os.path.exists(src):
            raise SystemExit("missing: " + src)
        build(src, os.path.join(OUTDIR, dst_name + ".cube"),
              display_mode=args.display_gamma)


if __name__ == "__main__":
    sys.exit(main())
