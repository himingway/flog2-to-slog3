#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""在 OKLab 感知色彩空间构造两支原创 ACR Style LUT（通透款 & 浓郁胶片款）。

两套风格在 OKLab 中分区调整色相、彩度和分离色调，并在输出格点匹配相对线性 Y。
分离色调会为近中性颜色着色。

1. ``Ultimate CrystalFilm Style``（通透 × 轻胶片）：
   中高调与高光接近中性、极暗部微冷墨黑分离；肤色洁净红润、黄转微琥珀、
   绿植呈翡翠清透感、晴空维持纯净正蓝。
2. ``Ultimate AnalogFilm Style``（浓郁胶片电影味）：
   经典光学印片分离色调（深暗部普鲁士冷青 ↔ 高光暖象牙奶油纸基）；暖黄转浓郁柯达琥珀金、
   青草收敛/深林呈 2383 松翠、蓝天压向电影青蓝氛围、肤色柔和奶油桃粉。

用法: .venv/bin/python build_ultimate_style.py
"""
import argparse
import os

import numpy as np

import lut_to_acr as m
from color_math import linear_srgb_to_oklab as _lin_to_oklab, oklab_to_linear_srgb as _oklab_to_lin

CRYSTAL_FILM_RECIPE = {
    "dh_lobes": (
        (+2.5,  25.0, 15.0),   # 红调微沉郁电影红
        (+0.4,  52.0, 13.0),   # 肤色锁定洁净红润粉桃感
        (-6.0,  92.0, 19.0),   # 黄调转暖琥珀金，消去柠檬黄感
        (+5.8, 138.0, 21.0),   # 绿植拉向富士/柯达高级翠绿
        (+2.0, 200.0, 22.0),   # 青绿清透化
        (-2.2, 260.0, 26.0),   # 蓝天与深蓝维持澄澈正蓝、拒绝发紫/脏青
        (+3.5, 332.0, 22.0),   # 洋红鲜花层次
    ),
    "sat_base": 1.14,
    "sat_hi_drop": 0.09,
    "sat_hi_L": 0.85,
    "sat_hi_w": 0.06,
    "sat_sh_boost": 0.04,
    "sat_sh_L": 0.36,
    "sat_sh_w": 0.08,
    "sat_sh_lo": 0.12,
    "sat_sh_wlo": 0.04,
    "hue_gain_lobes": (
        (+0.06,  26.0, 17.0),
        (-0.03,  53.0, 14.0),
        (-0.07,  94.0, 19.0),
        (-0.05, 122.0, 15.0),
        (+0.09, 144.0, 19.0),
        (+0.01, 204.0, 22.0),
        (+0.04, 258.0, 24.0),
    ),
    # 极暗部近中性颜色略带冷调。
    "shadow_split": (0.0040, 248.0, 0.08, 0.035, 0.24, 0.05, 0.040),
    "highlight_split": None,
}

ANALOG_FILM_RECIPE = {
    "dh_lobes": (
        (+8.5,  24.0, 19.0),   # 红调转复古胶片朱红/砖红
        (-2.2,  52.0, 15.0),   # 轻微向红桃收拢，抵消纸基暖意避免肤色发黄
        (-16.5, 92.0, 26.0),   # 黄色浓郁转柯达蜂蜜琥珀
        (+17.5, 146.0, 27.0),  # 绿叶大幅拉向 2383 / Classic Neg 深松翠
        (+12.0, 198.0, 28.0),  # 青水沉稳电影青蓝
        (-21.0, 250.0, 32.0),  # 晴空呈现经典 35mm 印片青蓝，消除数码电子蓝
        (-8.5, 278.0, 24.0),   # 深蓝稳重电影夜蓝
        (+13.0, 336.0, 24.0),  # 洋红复古玫瑰调
    ),
    "sat_base": 0.90,
    "sat_hi_drop": 0.14,
    "sat_hi_L": 0.80,
    "sat_hi_w": 0.08,
    "sat_sh_boost": 0.12,
    "sat_sh_L": 0.44,
    "sat_sh_w": 0.10,
    "sat_sh_lo": 0.12,
    "sat_sh_wlo": 0.04,
    "hue_gain_lobes": (
        (+0.18,  24.0, 19.0),  # 胶片红厚实饱和
        (+0.01,  52.0, 15.0),  # 肤色克制奶油润感，比 CrystalFilm 更柔和自然
        (-0.04,  92.0, 22.0),  # 琥珀沉稳
        (-0.12, 124.0, 20.0),  # 大幅收敛荧光草绿
        (+0.06, 148.0, 22.0),  # 保住深林松翠浓度，不显死灰
        (+0.08, 200.0, 26.0),  # 2383 青绿水色张力
        (-0.05, 250.0, 28.0),  # 天空高光轻敛更具银盐质感
        (+0.07, 278.0, 24.0),  # 深海夜蓝浓度
        (-0.14, 326.0, 24.0),  # 收敛紫调溢出
    ),
    # 经典 2383 / Portra 光学分离色调：冷青黑影 ↔ 暖奶油纸基高光（在纯白角前平滑收净）
    "shadow_split": (0.0290, 232.0, 0.08, 0.04, 0.32, 0.07, 0.032),
    "highlight_split": (0.0255, 82.0, 0.69, 0.08, 0.93, 0.03, 0.040),
}

RECIPES = {
    "Ultimate CrystalFilm Style.cube": CRYSTAL_FILM_RECIPE,
    "Ultimate AnalogFilm Style.cube": ANALOG_FILM_RECIPE,
}
OUTPUT_NAMES = tuple(RECIPES.keys())
OUTPUT_NAME = OUTPUT_NAMES[0]

def _gauss_lobe(h_deg, center_deg, width_deg):
    # Chord distance makes the response periodic and smoothly joins the hue circle.
    distance = 2.0 * np.sin(np.radians(h_deg - center_deg) * 0.5)
    return np.exp(-0.5 * (distance / np.radians(width_deg)) ** 2)


def _sigmoid(x):
    return 0.5 * (1.0 + np.tanh(0.5 * x))


def _gamut_headroom(lin, white_lum):
    """沿等亮度灰轴计算线性 RGB 抵达 [0, 1]^3 立方体边界的最大比例系数 t_max。"""
    d_vec = lin - white_lum
    eps = 1e-9
    pos = d_vec > eps
    neg = d_vec < -eps
    t_hi = np.where(pos, (1.0 - white_lum) / np.where(pos, d_vec, 1.0), 100.0)
    t_lo = np.where(neg, white_lum / np.where(neg, -d_vec, 1.0), 100.0)
    return np.minimum(np.min(t_hi, axis=-1), np.min(t_lo, axis=-1))


def _band_tint_oklab(L, C, wall_taper, spec):
    """在指定明度范围给近中性色加入分离色调。"""
    amp, hue_deg, l_lo, l_wlo, l_hi, l_whi, chroma_width = spec
    amt = (
        amp
        * _sigmoid((L - l_lo) / l_wlo)
        * _sigmoid((l_hi - L) / l_whi)
        * np.exp(-(C / chroma_width) ** 2)
        * wall_taper
    )
    rad = np.radians(hue_deg)
    return amt * np.cos(rad), amt * np.sin(rad)


def grade_linear_srgb(lin_in, recipe=CRYSTAL_FILM_RECIPE):
    """按指定 OKLab 配方调整线性 sRGB (N, 3)，并匹配输入的相对 CIE Y。"""
    lin_in = np.clip(np.asarray(lin_in, dtype=np.float64), 0.0, 1.0)
    y_in = lin_in @ m.REC709_LUM
    w = y_in[:, None]

    # 立方体边缘渐收因子：避免纯单色边界发生色域硬折角
    t_in_max = _gamut_headroom(lin_in, w)
    wall_taper = np.tanh(np.maximum(t_in_max - 1.0, 0.0) / 0.12)

    ok = _lin_to_oklab(lin_in)
    L, a, b = ok[..., 0], ok[..., 1], ok[..., 2]
    C = np.hypot(a, b)
    h = np.degrees(np.arctan2(b, a)) % 360.0

    # Fade hue-specific changes close to neutral, where hue is poorly defined.
    c_mask = (C * C) / (C * C + 0.020 ** 2)

    dh = sum(amp * _gauss_lobe(h, ctr, wid) for amp, ctr, wid in recipe["dh_lobes"])
    h_new = h + dh * c_mask

    lum_sat = (
        recipe["sat_base"]
        - recipe["sat_hi_drop"] * _sigmoid((L - recipe["sat_hi_L"]) / recipe["sat_hi_w"])
        + (recipe["sat_sh_boost"]
           * _sigmoid((recipe["sat_sh_L"] - L) / recipe["sat_sh_w"])
           * _sigmoid((L - recipe["sat_sh_lo"]) / recipe["sat_sh_wlo"]))
    )
    hue_gain = sum(amp * _gauss_lobe(h, ctr, wid) for amp, ctr, wid in recipe["hue_gain_lobes"])
    chroma = C * lum_sat * (1.0 + hue_gain * c_mask)
    rad = np.radians(h_new)
    a_out = chroma * np.cos(rad)
    b_out = chroma * np.sin(rad)

    # Taper the split tone with chroma and at the gamut boundary.
    for key in ("shadow_split", "highlight_split"):
        spec = recipe[key]
        if spec is not None:
            da_k, db_k = _band_tint_oklab(L, C, wall_taper, spec)
            a_out += da_k
            b_out += db_k

    ok_fin = np.stack([L, a_out, b_out], axis=-1)
    lin_look = _oklab_to_lin(ok_fin)
    return m.preserve_luminance(lin_in, lin_look, lum_coef=m.REC709_LUM)


def build(dst_path, recipe=CRYSTAL_FILM_RECIPE, out_size=64):
    """生成指定配方和精度的 ACR Style `.cube`。"""
    n = int(out_size)
    codes = m.uniform_grid(n)

    lin_in = m.decode_space(codes, "srgb")
    lin_out = grade_linear_srgb(lin_in, recipe=recipe)
    out_codes = m.encode_space(lin_out, "srgb").reshape(n, n, n, 3)

    title = os.path.splitext(os.path.basename(dst_path))[0]
    os.makedirs(os.path.dirname(os.path.abspath(dst_path)), exist_ok=True)
    m.write_cube(
        dst_path,
        out_codes,
        title,
        note="Original sRGB OKLab style, relative linear Y matched at nodes",
    )
    return dst_path


def main(argv=None):
    here = os.path.dirname(os.path.abspath(__file__))
    parser = argparse.ArgumentParser(
        description="生成两支原创 OKLab ACR Style LUT（CrystalFilm 通透款 & AnalogFilm 浓郁胶片款）",
    )
    parser.add_argument("-o", "--dst", default=os.path.join(here, "output", "acr_style"),
                        help="输出 ACR Style 目录（默认: ./output/acr_style）")
    parser.add_argument("-n", "--size", type=int, default=64,
                        help="输出 LUT 网格尺寸（默认: 64）")
    args = parser.parse_args(argv)

    for out_name, recipe in RECIPES.items():
        dst_path = os.path.join(args.dst, out_name)
        build(dst_path, recipe=recipe, out_size=args.size)
        print("OK ->", dst_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
