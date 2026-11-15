#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""在 OKLab 感知色彩空间构造两支原创 ACR Style LUT（通透款 & 浓郁胶片款）。

两套风格共用同一个 C^∞ 连续可微 OKLab 分区色调/彩度引擎与无拐点色域边界缓收逻辑，
通过配方表参数化区分调色取向，同时严格保持输入线性亮度与 360° 色相单调性：

1. ``Ultimate CrystalFilm Style``（通透 × 轻胶片）：
   中高调与高光 100% 纯中性无色罩、极暗部微冷墨黑分离；肤色洁净红润、黄转微琥珀、
   绿植呈翡翠清透感、晴空维持纯净正蓝。
2. ``Ultimate AnalogFilm Style``（浓郁胶片电影味）：
   经典光学印片分离色调（深暗部普鲁士冷青 ↔ 高光暖象牙奶油纸基）；暖黄转浓郁柯达琥珀金、
   青草收敛/深林呈 2383 松翠、蓝天压向电影青蓝氛围、肤色柔和奶油桃粉、高光柔和滚降。

用法: .venv/bin/python build_ultimate_style.py
"""
import argparse
import os

import numpy as np

import lut_to_acr as m

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
    # 仅最深阴影微弱冷墨（sRGB 0.50+ 纯中性 0.00）
    "shadow_split": (0.0040, 248.0, 0.08, 0.035, 0.24, 0.05, 0.18, 0.04),
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
    "shadow_split": (0.0290, 232.0, 0.08, 0.04, 0.32, 0.07, 0.18, 0.05),
    "highlight_split": (0.0255, 82.0, 0.69, 0.08, 0.93, 0.03, 0.085, 0.045),
}

RECIPES = {
    "Ultimate CrystalFilm Style.cube": CRYSTAL_FILM_RECIPE,
    "Ultimate AnalogFilm Style.cube": ANALOG_FILM_RECIPE,
}
OUTPUT_NAMES = tuple(RECIPES.keys())
OUTPUT_NAME = OUTPUT_NAMES[0]

# Björn Ottosson OKLab <-> 线性 sRGB 标准变换矩阵
_M1_OK = np.array([
    [0.4122214708, 0.5363325363, 0.0514459929],
    [0.2119034982, 0.6806995451, 0.1073969566],
    [0.0883024619, 0.2817188376, 0.6299787005],
], dtype=np.float64)
_M2_OK = np.array([
    [0.2104542553,  0.7936177850, -0.0040720468],
    [1.9779984951, -2.4285922050,  0.4505937099],
    [0.0259040371,  0.7827717662, -0.8086757660],
], dtype=np.float64)
_INV_M2_OK = np.linalg.inv(_M2_OK)
_INV_M1_OK = np.linalg.inv(_M1_OK)


def _angle_diff_deg(h_deg, center_deg):
    return (h_deg - center_deg + 180.0) % 360.0 - 180.0


def _gauss_lobe(h_deg, center_deg, width_deg):
    d = _angle_diff_deg(h_deg, center_deg) / width_deg
    return np.exp(-0.5 * d * d)


def _sigmoid(x):
    return 0.5 * (1.0 + np.tanh(0.5 * x))


def _lin_to_oklab(rgb):
    lms = np.clip(rgb, 0.0, None) @ _M1_OK.T
    return np.cbrt(lms) @ _M2_OK.T


def _oklab_to_lin(lab):
    lms_c = np.maximum(lab @ _INV_M2_OK.T, 0.0)
    return (lms_c ** 3) @ _INV_M1_OK.T


def _gamut_headroom(lin, white_lum):
    """沿等亮度灰轴计算线性 RGB 抵达 [0, 1]^3 立方体边界的最大比例系数 t_max。"""
    d_vec = lin - white_lum
    eps = 1e-9
    pos = d_vec > eps
    neg = d_vec < -eps
    t_hi = np.where(pos, (1.0 - white_lum) / np.where(pos, d_vec, 1.0), 100.0)
    t_lo = np.where(neg, white_lum / np.where(neg, -d_vec, 1.0), 100.0)
    return np.minimum(np.min(t_hi, axis=-1), np.min(t_lo, axis=-1)), d_vec


def _band_tint_oklab(L, C, wall_taper, spec):
    """按统一 8 参数包络在指定亮度与低彩度区间注入平滑分离色调 (da, db)。"""
    amp, hue_deg, l_lo, l_wlo, l_hi, l_whi, c_max, c_w = spec
    amt = (
        amp
        * _sigmoid((L - l_lo) / l_wlo)
        * _sigmoid((l_hi - L) / l_whi)
        * _sigmoid((c_max - C) / c_w)
        * wall_taper
    )
    rad = np.radians(hue_deg)
    return amt * np.cos(rad), amt * np.sin(rad)


def grade_linear_srgb(lin_in, recipe=CRYSTAL_FILM_RECIPE):
    """按指定 OKLab 配方对线性 sRGB (N, 3) 执行色彩塑造并严格锁定线性亮度。"""
    lin_in = np.clip(np.asarray(lin_in, dtype=np.float64), 0.0, 1.0)
    y_in = lin_in @ m.REC709_LUM
    w = y_in[:, None]

    # 立方体边缘渐收因子：避免纯单色边界发生色域硬折角
    t_in_max, _ = _gamut_headroom(lin_in, w)
    wall_taper = np.tanh(np.maximum(t_in_max - 1.0, 0.0) / 0.12)

    ok = _lin_to_oklab(lin_in)
    L, a, b = ok[..., 0], ok[..., 1], ok[..., 2]
    C = np.hypot(a, b)
    h = np.degrees(np.arctan2(b, a)) % 360.0

    # C^∞ 零点平滑激活，消除中性轴色相奇点
    c_mask = (C * C) / (C * C + 0.020 ** 2)

    dh = sum(amp * _gauss_lobe(h, ctr, wid) for amp, ctr, wid in recipe["dh_lobes"])
    h_new = h + dh * c_mask * wall_taper

    lum_sat = (
        recipe["sat_base"]
        - recipe["sat_hi_drop"] * _sigmoid((L - recipe["sat_hi_L"]) / recipe["sat_hi_w"])
        + (recipe["sat_sh_boost"]
           * _sigmoid((recipe["sat_sh_L"] - L) / recipe["sat_sh_w"])
           * _sigmoid((L - recipe["sat_sh_lo"]) / recipe["sat_sh_wlo"]))
    )
    hue_gain = sum(amp * _gauss_lobe(h, ctr, wid) for amp, ctr, wid in recipe["hue_gain_lobes"])
    target_scale = lum_sat * (1.0 + hue_gain)

    # 无突变色域余量缓压缩（防止高饱和原色撞向 RGB 边界产生二阶折痕）
    rad = np.radians(h_new)
    lin_rot = _oklab_to_lin(np.stack([L, C * np.cos(rad), C * np.sin(rad)], axis=-1))
    y_rot = lin_rot @ m.REC709_LUM
    valid_y = y_rot > 1e-7
    lin_iso = np.broadcast_to(w, lin_rot.shape).copy()
    lin_iso[valid_y] = lin_rot[valid_y] * (y_in[valid_y, None] / y_rot[valid_y, None])

    t_max, d_vec = _gamut_headroom(lin_iso, w)
    margin = np.maximum(t_max - 1.0, 0.0)
    soft_margin = np.sqrt(margin * margin + 0.03 ** 2) - 0.03
    gain_req = target_scale - 1.0
    scale_eff = np.where(
        gain_req > 0.0,
        1.0 + np.where(
            soft_margin > 1e-6,
            soft_margin * np.tanh(gain_req / np.maximum(soft_margin, 1e-6)),
            0.0,
        ),
        target_scale,
    )
    lin_sat = w + np.minimum(scale_eff, np.maximum(t_max * 0.999, 1.0))[:, None] * d_vec

    # 分离色调注入（随高彩度渐隐、受边界缓收约束，保证色环纯正与白点平滑）
    ok_sat = _lin_to_oklab(np.clip(lin_sat, 0.0, 1.0))
    da_split = np.zeros_like(L)
    db_split = np.zeros_like(L)
    for key in ("shadow_split", "highlight_split"):
        spec = recipe[key]
        if spec is not None:
            da_k, db_k = _band_tint_oklab(L, C, wall_taper, spec)
            da_split = da_split + da_k
            db_split = db_split + db_k

    ok_fin = np.stack([ok_sat[..., 0], ok_sat[..., 1] + da_split, ok_sat[..., 2] + db_split], axis=-1)
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
        note="Original OKLab Signature Style LUT for Adobe Camera Raw (luminance-locked)",
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
