#!/usr/bin/env python3
"""将 ARRI 官方 LogC3 / LogC4 -> Rec.709 LUT 转换为 Adobe Camera Raw Style LUT。

流水线复用 `lut_to_acr` 统一几何色域与亮度保持架构：
  1. sRGB 代码 -> linear sRGB
  2. Bradford CAT 转换至 ARRI Wide Gamut 3 或 ARRI Wide Gamut 4
  3. 编码为 ARRI LogC3 (SUP 3.x EI=800) 或 ARRI LogC4
  4. 可选串联 ARRI Look Library (log-to-log 3D LUT)
  5. 四面体插值采样 ARRI 官方 Rec.709 Gamma 2.4 DRT
  6. 按 Gamma 2.4 (ARRI 官方标注输出曲线) 解码为线性光
  7. `preserve_luminance` 匹配输入的相对线性 Y，并在固定 OKLab 色相下收缩越界颜色
  8. 编码回 sRGB 并写出 64^3 .cube
"""

import argparse
import os
import sys

import colour
import numpy as np

import lut_to_acr as m

# (输出文件名, ARRI 色彩空间, ARRI 对数编码, DRT 文件相对路径, 可选 Look 文件相对路径)
ARRI_PRESETS = [
    ("ARRI Alexa35 REVEAL 65 Style.cube",
     "ARRI Wide Gamut 4", "ARRI LogC4",
     "ARRI_LogC4-to-Gamma24_Rec709-D65_v1_65.cube", None),
    ("ARRI Alexa Classic 65 Style.cube",
     "ARRI Wide Gamut 3", "ARRI LogC3",
     "ARRI_LogC3-to-Gamma24_Rec709_D65-Classic_33.cube", None),
    ("ARRI Alexa ALF2 65 Style.cube",
     "ARRI Wide Gamut 3", "ARRI LogC3",
     "ARRI_LogC3-to-Gamma24_Rec709_D65-v1_33.cube", None),
    ("ARRI Look 3110 Film A 65 Style.cube",
     "ARRI Wide Gamut 4", "ARRI LogC4",
     "ARRI_LogC4-to-Gamma24_Rec709-D65_v1_65.cube",
     "look_library_logc4/3110 Film A.cube"),
    ("ARRI Look 3114 Film E 65 Style.cube",
     "ARRI Wide Gamut 4", "ARRI LogC4",
     "ARRI_LogC4-to-Gamma24_Rec709-D65_v1_65.cube",
     "look_library_logc4/3114 Film E.cube"),
    ("ARRI Look 3150 Bleach Bypass 65 Style.cube",
     "ARRI Wide Gamut 4", "ARRI LogC4",
     "ARRI_LogC4-to-Gamma24_Rec709-D65_v1_65.cube",
     "look_library_logc4/3150 Film Process - Bleach bypass.cube"),
    ("ARRI Look 3211 Vintage 65 Style.cube",
     "ARRI Wide Gamut 4", "ARRI LogC4",
     "ARRI_LogC4-to-Gamma24_Rec709-D65_v1_65.cube",
     "look_library_logc4/3211 Vintage.cube"),
    ("ARRI Look 3411 TealOrange 65 Style.cube",
     "ARRI Wide Gamut 4", "ARRI LogC4",
     "ARRI_LogC4-to-Gamma24_Rec709-D65_v1_65.cube",
     "look_library_logc4/3411 Film - Teal and orange.cube"),
    ("ARRI Look 5110 Nature 65 Style.cube",
     "ARRI Wide Gamut 4", "ARRI LogC4",
     "ARRI_LogC4-to-Gamma24_Rec709-D65_v1_65.cube",
     "look_library_logc4/5110 Nature.cube"),
    ("ARRI Look 6311 Pastel 65 Style.cube",
     "ARRI Wide Gamut 4", "ARRI LogC4",
     "ARRI_LogC4-to-Gamma24_Rec709-D65_v1_65.cube",
     "look_library_logc4/6311 Pastel.cube"),
]


def build(drt_path, dst_path, gamut="ARRI Wide Gamut 4", log_name="ARRI LogC4",
          look_path=None, n=64, display_mode="2.4"):
    """将单个 ARRI DRT (与可选 log-to-log Look LUT) 烘焙为 ACR sRGB Style LUT。"""
    _, drt_table, drt_min, drt_max, _ = m.read_cube(drt_path)

    codes = m.uniform_grid(n)

    lin_srgb = m.decode_space(codes, "srgb")
    lin_awg = np.clip(
        colour.RGB_to_RGB(lin_srgb, "sRGB", gamut, chromatic_adaptation_transform="Bradford"),
        0.0, None,
    )
    log_codes = colour.models.log_encoding(lin_awg, log_name)

    if look_path is not None:
        _, look_table, look_min, look_max, _ = m.read_cube(look_path)
        look_pos = (log_codes - look_min) / (look_max - look_min)
        log_codes = m.sample_table_tetra(look_table, look_pos)

    drt_pos = (log_codes - drt_min) / (drt_max - drt_min)
    rec709 = np.clip(m.sample_table_tetra(drt_table, drt_pos), 0.0, 1.0)

    lin_look = m.decode_display(rec709, display_mode)
    out_lin = m.preserve_luminance(lin_srgb, lin_look)
    out_codes = m.encode_space(out_lin, "srgb").reshape(n, n, n, 3)

    title = os.path.splitext(os.path.basename(dst_path))[0]
    source_parts = [os.path.basename(look_path), os.path.basename(drt_path)] if look_path else [os.path.basename(drt_path)]
    os.makedirs(os.path.dirname(os.path.abspath(dst_path)), exist_ok=True)
    m.write_cube(
        dst_path, out_codes, title,
        source_title=" -> ".join(source_parts),
        note=f"Re-baked for Adobe Camera Raw ({log_name}/{gamut} official ARRI LUT)",
    )
    return dst_path


def main(argv=None):
    here = os.path.dirname(os.path.abspath(__file__))
    parser = argparse.ArgumentParser(
        description="批量将 ARRI 官方 LogC3/LogC4 Rec.709 LUT 转换为 Camera Raw Style LUT",
    )
    parser.add_argument("-i", "--src", default=os.path.join(here, "sources", "arri_official"),
                        help="ARRI 官方源 LUT 目录（默认: ./sources/arri_official）")
    parser.add_argument("-o", "--dst", default=os.path.join(here, "output", "acr_style"),
                        help="输出 ACR Style 目录（默认: ./output/acr_style）")
    parser.add_argument("-n", "--size", type=int, default=64,
                        help="输出 LUT 网格尺寸（默认: 64）")
    parser.add_argument("--display-gamma", choices=m.DISPLAY_MODES, default="2.4",
                        help="源 LUT 输出的 Rec.709 解码伽马（ARRI Gamma24 默认: 2.4）")
    args = parser.parse_args(argv)

    built = 0
    for out_name, gamut, log_name, drt_rel, look_rel in ARRI_PRESETS:
        drt_path = os.path.join(args.src, drt_rel)
        look_path = os.path.join(args.src, look_rel) if look_rel else None
        if not os.path.isfile(drt_path):
            continue
        if look_path is not None and not os.path.isfile(look_path):
            continue
        dst_path = os.path.join(args.dst, out_name)
        build(drt_path, dst_path, gamut=gamut, log_name=log_name,
              look_path=look_path, n=args.size, display_mode=args.display_gamma)
        built += 1
        print("OK ->", out_name)

    if built == 0:
        sys.stderr.write(f"未在 {args.src} 中找到可用的 ARRI 官方 .cube 源文件。\n")
        return 1
    print(f"ARRI Style 转换完成，共输出 {built} 个。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
