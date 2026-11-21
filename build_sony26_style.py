#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从精选索尼终极调色包（S-Log3 / S-Gamut3.Cine）构建 ACR / LrC 用 Style LUT。

所有输出统一添加 ``Sony26 `` 前缀，方便在 Lightroom Classic / Adobe Camera Raw
LUT 下拉菜单中分组检索，并在输出格点匹配输入相对线性 Y。

用法: .venv/bin/python build_sony26_style.py
"""
import argparse
import os
import sys

import lut_to_acr as m

HERE = os.path.dirname(os.path.abspath(__file__))
PACK = os.path.join(HERE, "sources", "sony_pack_20260928")
OUTDIR = os.path.join(HERE, "output", "acr_style")
PREFIX = "Sony26 "
SOURCE_DISPLAY_GAMMA = {"Quirky_33x.cube": "2.4"}  # Filmbox LUT header

# (源文件名, LrC/ACR 显示基础名, 输入 EV 偏移)
CURATED_SPECS = [
    ("2383_55.cube", "Kodak 2383 D55 Style", 0.0),
    ("2383_65.cube", "Kodak 2383 D65 Style", 0.0),
    ("BP-02.cube", "BP-02 Cool Steel Style", 0.0),
    ("BP-04.cube", "BP-04 Commercial Warm Style", 0.0),
    ("BP-08.cube", "BP-08 Chrome Mute Style", 0.0),
    ("Kodax_Slog3.cube", "Kodax Film Style", 0.0),
    ("True_Tone_Filmic.cube", "True Tone Filmic Style", 0.0),
    ("Arri_Cinema_Green.cube", "Cinema Green Style", 0.0),
    ("Portra_400.cube", "Portra 400 Style", 0.0),
    ("Eterna_160T.cube", "Eterna 160T Style", 0.0),
    ("Vision3_500T.cube", "Vision3 500T Style", 0.0),
    ("Vintage_Classic_Film.cube", "Vintage Classic Style", 0.0),
    ("FilmGreens_SLG3.cube", "Film Greens Style", 0.0),
    ("JN3_Teal.cube", "JN3 Teal Style", 0.0),
    ("JN5_Gold.cube", "JN5 Gold Style", 0.0),
    ("JN6_Cine.cube", "JN6 Cine Style", 0.0),
    ("Chicago_Slog3.cube", "Chicago Street Style", 0.0),
    ("Leica_Eternal.cube", "Leica Eternal Style", 0.0),
    ("Lucy_True_Tone.cube", "Lucy True Tone Style", 0.0),
    ("Neutral_Slog3.cube", "Neutral Clear Style", 0.0),
    ("Neutro_SLG3.cube", "Neutro Clean Style", 0.0),
    ("SLOG3_Portrait.cube", "Portrait Style", 0.0),
    # +0.5 EV is the selected creative offset for this Filmbox look.
    ("Quirky_33x.cube", "Quirky Pro400H Style", 0.5),
]


def output_filename(label, prefix=PREFIX):
    """生成带统一前缀的 ACR/LrC 目标 `.cube` 文件名。"""
    return f"{prefix}{label}.cube"


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="从精选索尼调色包构建带统一前缀的 ACR / LrC Style LUT")
    ap.add_argument("-i", "--src", default=PACK,
                    help="精选源 LUT 目录（默认 sources/sony_pack_20260928）")
    ap.add_argument("-o", "--dst", "--outdir", dest="dst", default=OUTDIR,
                    help="输出目录（默认 output/acr_style）")
    ap.add_argument("-n", "--size", type=int, default=64,
                    help="输出 LUT 格点数（默认 64）")
    ap.add_argument("--prefix", default=PREFIX,
                    help="ACR/LrC 菜单名前缀（默认 'Sony26 '）")
    ap.add_argument("--display-gamma", choices=m.DISPLAY_MODES, default=None,
                    help="覆盖整包的源显示解码方式（默认 Quirky 2.4，其余按 sRGB 假定）")
    args = ap.parse_args(argv)

    jobs = []
    for src_name, label, ev_offset in CURATED_SPECS:
        src = os.path.join(args.src, src_name)
        if not os.path.isfile(src):
            print(f"error: 缺少源 LUT 文件: {src}", file=sys.stderr)
            return 1
        display_mode = args.display_gamma or SOURCE_DISPLAY_GAMMA.get(src_name, "srgb")
        jobs.append((src, os.path.join(args.dst, output_filename(label, args.prefix)), ev_offset, display_mode))

    os.makedirs(args.dst, exist_ok=True)
    for src, dst, ev_offset, display_mode in jobs:
        m.convert(
            src,
            dst,
            space="srgb",
            display_mode=display_mode,
            out_size=args.size,
            tone_mode="preserve",
            ev_offset=ev_offset,
        )
        print("built", dst)
    return 0


if __name__ == "__main__":
    sys.exit(main())
