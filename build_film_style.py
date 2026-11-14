#!/usr/bin/env python3
"""将 Sony VENICE 官方 Look (S-Log3 / S-Gamut3.Cine) 转换为 Camera Raw Style LUT。

直接复用 `lut_to_acr.convert(..., tone_mode="preserve", display_mode="2.4")`。
"""

import argparse
import os
import sys

import lut_to_acr as m

VENICE_MAPPING = {
    "Slog3-S-Gamut3.Cine_To_s709_V200.cube": "Sony VENICE s709 65 Style.cube",
    "sv2_look_7525_r709_g24.cube":           "Sony VENICE2 Look 7525 65 Style.cube",
    "sv2_look_1_r709_g24.cube":              "Sony VENICE2 Look 1 65 Style.cube",
}


def main(argv=None):
    here = os.path.dirname(os.path.abspath(__file__))
    parser = argparse.ArgumentParser(
        description="批量构建 Sony VENICE Style LUT",
    )
    parser.add_argument("--venice-src", default=os.path.join(here, "sources", "sony_venice_official"),
                        help="Sony VENICE S-Log3 LUT 目录（默认: ./sources/sony_venice_official）")
    parser.add_argument("-o", "--dst", default=os.path.join(here, "output", "acr_style"),
                        help="输出 ACR Style 目录（默认: ./output/acr_style）")
    parser.add_argument("-n", "--size", type=int, default=64,
                        help="输出 LUT 网格尺寸（默认: 64）")
    parser.add_argument("--display-gamma", choices=m.DISPLAY_MODES, default="2.4",
                        help="源 LUT 输出的 Rec.709 解码伽马（VENICE 默认: 2.4）")
    args = parser.parse_args(argv)

    built = 0
    for src_fn, out_fn in VENICE_MAPPING.items():
        src_path = os.path.join(args.venice_src, src_fn)
        if not os.path.isfile(src_path):
            continue
        dst_path = os.path.join(args.dst, out_fn)
        m.convert(src_path, dst_path, space="srgb", display_mode=args.display_gamma,
                  out_size=args.size, tone_mode="preserve")
        built += 1
        print("OK ->", out_fn)

    if built == 0:
        sys.stderr.write("未找到可用的 Sony VENICE 源 LUT。\n")
        return 1
    print(f"VENICE Style 转换完成，共输出 {built} 个。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
