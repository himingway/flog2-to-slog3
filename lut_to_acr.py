#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
lut_to_acr.py — 把 S-Gamut3.Cine / S-Log3 的 .cube LUT 重制为
Adobe Camera Raw 可直接使用的 LUT。

默认以 sRGB 为目标接口（--space srgb）。这是对宿主接口的假设，
与源 LUT 的显示传递函数独立。

色彩模型（每个输出格点）:
    ACR 输入 code
      -> 按目标空间解码为线性 RGB（默认 sRGB；可切 --space adobergb）
      -> 3x3 矩阵转换线性 RGB 到 S-Gamut3.Cine
      -> S-Log3 编码（Sony 官方曲线）
      -> 四面体 / 三线性插值采样原始 LUT（默认四面体）
      -> 输出端（--output-mode / --tone preserve）:
           as-is       (默认) 原 LUT 输出值直接作为目标空间编码值写出  -> sRGB -> sRGB
           display-709        原 LUT 输出按 Rec.709 显示解码，再转换/编码为目标空间

用法:
    python3 lut_to_acr.py input.cube output.cube            # 默认 sRGB/Rec.709 -> 同空间直通
    python3 lut_to_acr.py --space adobergb in.cube out.cube # 按 Adobe RGB (1998) 接口
    python3 lut_to_acr.py --size 64 --report in.cube out.cube
    python3 lut_to_acr.py --output-mode display-709 in.cube out.cube

参考:
    Sony "S-Gamut3.Cine/S-Gamut3/S-Log3 Technical Summary V1.0"
    Adobe RGB (1998) 规范: gamma 563/256, D65
"""

import argparse
import os
import sys

import numpy as np

from color_math import linear_srgb_to_oklab, oklab_to_linear_srgb

# ---------------------------------------------------------------------------
# 色彩空间定义
# ---------------------------------------------------------------------------

D65_WHITE = (0.3127, 0.3290)  # CIE 1931 2° D65
D50_WHITE = (0.3457, 0.3585)  # ProPhoto RGB (ROMM) 白点

# ProPhoto RGB (ROMM RGB) 基色，线性
PROPHOTO_PRIMARIES = ((0.7347, 0.2653), (0.1596, 0.8404), (0.0366, 0.0001))

# Bradford 色适应 D65 -> D50（用于 ProPhoto D50 与 S-Gamut3.Cine D65 之间）
BRADFORD_D65_TO_D50 = np.array([
    [1.0478112, 0.0228866, -0.0501270],
    [0.0295424, 0.9904844, -0.0170491],
    [-0.0092345, 0.0150436, 0.7521316],
])

# Adobe RGB (1998)
ADOBE_RGB_GAMMA = 563.0 / 256.0  # 2.19921875
ADOBE_RGB_PRIMARIES = ((0.6400, 0.3300), (0.2100, 0.7100), (0.1500, 0.0600))
ROMM_LIN_BREAK = 1.0 / 512.0

# sRGB / Rec.709 基色
SRGB_PRIMARIES = ((0.6400, 0.3300), (0.3000, 0.6000), (0.1500, 0.0600))

# Sony S-Gamut3.Cine（D65）
SGAMUT3CINE_PRIMARIES = ((0.766, 0.275), (0.225, 0.800), (0.089, -0.087))

# Sony S-Log3（官方 Technical Summary）
SLOG3_LIN_BREAK = 0.01125        # 线性段/对数段分界（场景线性）
SLOG3_LOG_BREAK_CV = 171.2102946929  # 分界处 10bit 码值
SLOG3_BLACK_CV = 95.0            # 0% 反射对应码值
SLOG3_MID_CV = 420.0             # 18% 灰对应码值（1023 满量程）
SLOG3_SLOPE = 261.5
SLOG3_CV_MAX = 1023.0
SLOG3_OFFSET = 0.01
SLOG3_MID_REF = 0.19             # 0.18 + 0.01

DISPLAY_MODES = ("srgb", "2.4", "2.2", "bt709-oetf", "linear")
REC709_LUM = np.array([0.2126, 0.7152, 0.0722], dtype=np.float64)


# ---------------------------------------------------------------------------
# 矩阵推导（基色 + 白点 -> RGB<->XYZ）
# ---------------------------------------------------------------------------

def _xy_to_xyz(xy):
    x, y = xy
    return np.array([x / y, 1.0, (1.0 - x - y) / y], dtype=np.float64)


def rgb_to_xyz(primaries, white=D65_WHITE):
    """由基色 xy 和白点 xy 推导 RGB -> XYZ 矩阵（Y 归一化）。"""
    p = np.column_stack([_xy_to_xyz(c) for c in primaries])
    s = np.linalg.solve(p, _xy_to_xyz(white))
    return p * s


def xyz_to_rgb(primaries, white=D65_WHITE):
    return np.linalg.inv(rgb_to_xyz(primaries, white))


def conversion_matrices(space):
    """返回 (目标空间线性 -> S-Gamut3.Cine 线性, Rec.709 线性 -> 目标空间线性)。"""
    m_709_to_xyz = rgb_to_xyz(SRGB_PRIMARIES, D65_WHITE)
    if space.startswith("prophoto"):
        pp_to_xyz = rgb_to_xyz(PROPHOTO_PRIMARIES, D50_WHITE)
        xyz_to_pp = xyz_to_rgb(PROPHOTO_PRIMARIES, D50_WHITE)
        d50_to_d65 = np.linalg.inv(BRADFORD_D65_TO_D50)
        m_target_to_sgc = xyz_to_rgb(SGAMUT3CINE_PRIMARIES, D65_WHITE) @ d50_to_d65 @ pp_to_xyz
        m_709_to_target = xyz_to_pp @ BRADFORD_D65_TO_D50 @ m_709_to_xyz
        return m_target_to_sgc, m_709_to_target

    target_prim = SRGB_PRIMARIES if space.startswith("srgb") else ADOBE_RGB_PRIMARIES
    m_target_to_sgc = xyz_to_rgb(SGAMUT3CINE_PRIMARIES) @ rgb_to_xyz(target_prim)
    m_709_to_target = xyz_to_rgb(target_prim) @ m_709_to_xyz
    return m_target_to_sgc, m_709_to_target


# ---------------------------------------------------------------------------
# 传递函数
# ---------------------------------------------------------------------------

def slog3_encode(linear):
    """场景线性 -> S-Log3 code (0..1)，Sony 官方分段公式。"""
    x = np.asarray(linear, dtype=np.float64)
    out = np.empty_like(x)
    hi = x >= SLOG3_LIN_BREAK
    out[hi] = (SLOG3_MID_CV
               + SLOG3_SLOPE * np.log10((x[hi] + SLOG3_OFFSET) / SLOG3_MID_REF)) / SLOG3_CV_MAX
    out[~hi] = (x[~hi] * (SLOG3_LOG_BREAK_CV - SLOG3_BLACK_CV) / SLOG3_LIN_BREAK
                + SLOG3_BLACK_CV) / SLOG3_CV_MAX
    return out


def slog3_decode(code):
    """S-Log3 code (0..1) -> 场景线性。"""
    y = np.asarray(code, dtype=np.float64) * SLOG3_CV_MAX
    out = np.empty_like(y)
    hi = y >= SLOG3_LOG_BREAK_CV
    out[hi] = 10.0 ** ((y[hi] - SLOG3_MID_CV) / SLOG3_SLOPE) * SLOG3_MID_REF - SLOG3_OFFSET
    out[~hi] = (y[~hi] - SLOG3_BLACK_CV) * SLOG3_LIN_BREAK / (SLOG3_LOG_BREAK_CV - SLOG3_BLACK_CV)
    return out


def decode_space(code, space):
    """目标空间编码值 -> 线性。"""
    v = np.clip(np.asarray(code, dtype=np.float64), 0.0, 1.0)
    if space.endswith("-linear"):
        return v
    if space == "adobergb":
        return v ** ADOBE_RGB_GAMMA
    if space == "prophoto":
        return np.where(v < 16.0 * ROMM_LIN_BREAK, v / 16.0, v ** 1.8)
    # sRGB (IEC 61966-2-1)
    return np.where(v <= 0.04045, v / 12.92, ((v + 0.055) / 1.055) ** 2.4)


def encode_space(linear, space):
    """线性 -> 目标空间编码值。"""
    v = np.clip(np.asarray(linear, dtype=np.float64), 0.0, 1.0)
    if space.endswith("-linear"):
        return v
    if space == "adobergb":
        return v ** (1.0 / ADOBE_RGB_GAMMA)
    if space == "prophoto":
        return np.where(v < ROMM_LIN_BREAK, v * 16.0, v ** (1.0 / 1.8))
    return np.where(v <= 0.0031308,
                    v * 12.92,
                    1.055 * v ** (1.0 / 2.4) - 0.055)


def space_lum_coef(space):
    """返回目标空间线性 RGB -> CIE Y 的亮度权重向量（总和为 1）。"""
    if space.startswith("srgb"):
        return REC709_LUM
    if space.startswith("prophoto"):
        return rgb_to_xyz(PROPHOTO_PRIMARIES, D50_WHITE)[1]
    return rgb_to_xyz(ADOBE_RGB_PRIMARIES, D65_WHITE)[1]


def decode_display(code, mode):
    """原始 LUT 的输出（Rec.709 显示编码值）-> 线性光。"""
    c = np.clip(np.asarray(code, dtype=np.float64), 0.0, 1.0)
    if mode == "srgb":
        return decode_space(c, "srgb")
    if mode == "2.4":
        return c ** 2.4
    if mode == "2.2":
        return c ** 2.2
    if mode == "bt709-oetf":
        return np.where(c < 0.081, c / 4.5, ((c + 0.099) / 1.099) ** (1.0 / 0.45))
    if mode == "linear":
        return c
    raise ValueError("未知 display 模式: %r" % (mode,))


# ---------------------------------------------------------------------------
# .cube 读写与三线性插值
# ---------------------------------------------------------------------------

def read_cube(path):
    """读取 3D .cube。返回 (size, table[size,size,size,3], domain_min, domain_max, title)。

    table 索引为 table[blue, green, red]，即文件里红色变化最快（.cube 规范）。
    """
    size = None
    domain_min = np.zeros(3, dtype=np.float64)
    domain_max = np.ones(3, dtype=np.float64)
    title = os.path.basename(path)
    rows = []

    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            key = line.split(None, 1)[0].upper()
            if key == "LUT_3D_SIZE":
                size = int(line.split()[1])
            elif key == "LUT_1D_SIZE":
                raise ValueError("只支持 3D LUT: %s" % path)
            elif key == "DOMAIN_MIN":
                domain_min = np.array([float(v) for v in line.split()[1:4]])
            elif key == "DOMAIN_MAX":
                domain_max = np.array([float(v) for v in line.split()[1:4]])
            elif key == "LUT_3D_INPUT_RANGE":
                vals = line.split()[1:3]
                if len(vals) == 2:
                    domain_min = np.full(3, float(vals[0]))
                    domain_max = np.full(3, float(vals[1]))
            elif key == "TITLE":
                rest = line[len("TITLE"):].strip().strip('"')
                if rest:
                    title = rest
            else:
                parts = line.split()
                try:
                    rows.append((float(parts[0]), float(parts[1]), float(parts[2])))
                except (ValueError, IndexError):
                    continue

    if size is None:
        raise ValueError("缺少 LUT_3D_SIZE: %s" % path)
    if not np.all(domain_max > domain_min):
        raise ValueError("%s: 无效 DOMAIN 范围 min=%s max=%s" % (path, domain_min, domain_max))
    data = np.asarray(rows, dtype=np.float64)
    if data.shape != (size ** 3, 3):
        raise ValueError("%s: 期望 %d 行数据, 实际 %d" % (path, size ** 3, data.shape[0]))
    return size, data.reshape(size, size, size, 3), domain_min, domain_max, title


def sample_table(table, coords):
    """三线性插值。coords 为 (N,3) 的 (r,g,b)；table 索引 [blue,green,red]。"""
    coords = np.asarray(coords, dtype=np.float64)
    if not np.all(np.isfinite(coords)):
        raise ValueError("sample_table 收到非有限坐标（NaN/Inf）")
    n = table.shape[0]
    v = np.clip(coords, 0.0, 1.0) * (n - 1)
    i0 = np.floor(v).astype(np.int64)
    i1 = np.minimum(i0 + 1, n - 1)
    f = v - i0

    r0, g0, b0 = i0[:, 0], i0[:, 1], i0[:, 2]
    r1, g1, b1 = i1[:, 0], i1[:, 1], i1[:, 2]
    fr = f[:, 0:1]
    fg = f[:, 1:2]
    fb = f[:, 2:3]

    def corner(r, g, b):
        return table[b, g, r]

    return (corner(r0, g0, b0) * ((1 - fr) * (1 - fg) * (1 - fb))
            + corner(r1, g0, b0) * (fr * (1 - fg) * (1 - fb))
            + corner(r0, g1, b0) * ((1 - fr) * fg * (1 - fb))
            + corner(r1, g1, b0) * (fr * fg * (1 - fb))
            + corner(r0, g0, b1) * ((1 - fr) * (1 - fg) * fb)
            + corner(r1, g0, b1) * (fr * (1 - fg) * fb)
            + corner(r0, g1, b1) * ((1 - fr) * fg * fb)
            + corner(r1, g1, b1) * (fr * fg * fb))


def sample_table_tetra(table, coords):
    """四面体插值（3D LUT 工业标准，比三线性更准确）。coords 为 (N,3) 的 (r,g,b)。"""
    coords = np.asarray(coords, dtype=np.float64)
    if not np.all(np.isfinite(coords)):
        raise ValueError("sample_table_tetra 收到非有限坐标（NaN/Inf）")
    n = table.shape[0]
    v = np.clip(coords, 0.0, 1.0) * (n - 1)
    i0 = np.floor(v).astype(np.int64)
    i1 = np.minimum(i0 + 1, n - 1)
    f = v - i0
    r0, g0, b0 = i0[:, 0], i0[:, 1], i0[:, 2]
    r1, g1, b1 = i1[:, 0], i1[:, 1], i1[:, 2]
    x = f[:, 0:1]
    y = f[:, 1:2]
    z = f[:, 2:3]

    def corner(r, g, b):
        return table[b, g, r]

    c000 = corner(r0, g0, b0)
    c100 = corner(r1, g0, b0)
    c010 = corner(r0, g1, b0)
    c001 = corner(r0, g0, b1)
    c110 = corner(r1, g1, b0)
    c101 = corner(r1, g0, b1)
    c011 = corner(r0, g1, b1)
    c111 = corner(r1, g1, b1)

    xf, yf, zf = f[:, 0], f[:, 1], f[:, 2]
    m1 = (xf > yf) & (yf > zf)
    m2 = (xf > yf) & (yf <= zf) & (xf > zf)
    m3 = (xf > yf) & (yf <= zf) & (xf <= zf)
    m4 = (xf <= yf) & (xf > zf)
    m5 = (xf <= yf) & (xf <= zf) & (yf > zf)
    m6 = (xf <= yf) & (xf <= zf) & (yf <= zf)

    out = np.empty_like(c000)
    out[m1] = (c000[m1] * (1 - x[m1]) + c100[m1] * (x[m1] - y[m1])
               + c110[m1] * (y[m1] - z[m1]) + c111[m1] * z[m1])
    out[m2] = (c000[m2] * (1 - x[m2]) + c100[m2] * (x[m2] - z[m2])
               + c101[m2] * (z[m2] - y[m2]) + c111[m2] * y[m2])
    out[m3] = (c000[m3] * (1 - z[m3]) + c001[m3] * (z[m3] - x[m3])
               + c101[m3] * (x[m3] - y[m3]) + c111[m3] * y[m3])
    out[m4] = (c000[m4] * (1 - y[m4]) + c010[m4] * (y[m4] - x[m4])
               + c110[m4] * (x[m4] - z[m4]) + c111[m4] * z[m4])
    out[m5] = (c000[m5] * (1 - y[m5]) + c010[m5] * (y[m5] - z[m5])
               + c011[m5] * (z[m5] - x[m5]) + c111[m5] * x[m5])
    out[m6] = (c000[m6] * (1 - z[m6]) + c001[m6] * (z[m6] - y[m6])
               + c011[m6] * (y[m6] - x[m6]) + c111[m6] * x[m6])
    return out


def preserve_luminance(lin_in, lin_look, lum_coef=REC709_LUM, *, space="srgb"):
    """Restore linear Y and reduce out-of-gamut chroma at constant OKLab hue."""
    lin_in = np.asarray(lin_in, dtype=np.float64)
    lin_look = np.asarray(lin_look, dtype=np.float64)
    lum_coef = np.asarray(lum_coef, dtype=np.float64)

    y_in = np.clip(lin_in @ lum_coef, 0.0, 1.0)
    y_look = lin_look @ lum_coef
    neutral = y_in[:, None]
    # Fade toward neutral as source luminance approaches zero, where chromaticity
    # becomes ill-conditioned. This also handles source LUTs that crush to black.
    t = np.clip(y_look / 1e-5, 0.0, 1.0)
    strength = t * t * (3.0 - 2.0 * t)
    scale = np.divide(y_in * strength, y_look, out=np.zeros_like(y_in), where=y_look > 0.0)
    out = lin_look * scale[:, None] + neutral * (1.0 - strength[:, None])
    interior = (y_in > 0.0) & (y_in < 1.0)
    oob = interior & np.any((out < -1e-12) | (out > 1.0 + 1e-12), axis=1)
    if np.any(oob):
        out[oob] = _fit_oklab_chroma(out[oob], y_in[oob], lum_coef, space)
    out[~interior] = neutral[~interior]
    return np.clip(out, 0.0, 1.0)


def _fit_oklab_chroma(rgb, y, lum_coef, space):
    if space.startswith("srgb"):
        to_srgb = from_srgb = np.eye(3)
    else:
        _, from_srgb = conversion_matrices(space)
        to_srgb = np.linalg.inv(from_srgb)
    lab = linear_srgb_to_oklab(rgb @ to_srgb.T)

    # OKLab scales uniformly with the cube root of exposure. At each trial
    # chroma we can restore Y by scaling RGB without changing OKLab hue.
    low = np.zeros_like(y)
    high = np.ones_like(y)
    result = np.repeat(y[:, None], 3, axis=1)
    trial = lab.copy()
    for _ in range(20):
        amount = (low + high) * 0.5
        trial[:, 1:] = lab[:, 1:] * amount[:, None]
        rgb_trial = oklab_to_linear_srgb(trial) @ from_srgb.T
        trial_y = rgb_trial @ lum_coef
        positive = trial_y > 0.0
        scale = np.divide(y, trial_y, out=np.zeros_like(y), where=positive)
        rgb_trial *= scale[:, None]
        fits = positive & np.all((rgb_trial >= 0.0) & (rgb_trial <= 1.0), axis=1)
        result[fits] = rgb_trial[fits]
        low = np.where(fits, amount, low)
        high = np.where(fits, high, amount)
    return result


def write_cube(path, table, title, source_title=None,
               note="Re-baked for Adobe Camera Raw (S-Log3/S-Gamut3.Cine source LUT)"):
    n = table.shape[0]
    header = [
        "# %s" % note,
    ]
    if source_title and source_title != title:
        header.append("# source title: %s"
                      % source_title.replace('"', "'").replace("\n", " "))
    header += [
        'TITLE "%s"' % title.replace('"', "'"),
        "LUT_3D_SIZE %d" % n,
        "DOMAIN_MIN 0.0 0.0 0.0",
        "DOMAIN_MAX 1.0 1.0 1.0",
    ]
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(header) + "\n")
        np.savetxt(fh, table.reshape(-1, 3), fmt="%.8f")


# ---------------------------------------------------------------------------
# 转换
# ---------------------------------------------------------------------------

def uniform_grid(out_size):
    """生成 (out_size^3, 3) 的 [R, G, B] 均匀采样网格（按 .cube B/G/R 外到内序）。"""
    n = int(out_size)
    idx = np.linspace(0.0, 1.0, n)
    blue_axis, green_axis, red_axis = np.meshgrid(idx, idx, idx, indexing="ij")
    return np.stack((red_axis, green_axis, blue_axis), axis=-1).reshape(-1, 3)


def highlight_expand(v, anchor=0.18, white_scene=4.0):
    """显示线性值的高光展开（锚定 18% 灰，显示白 -> white_scene 倍场景反射）。

    仅对显示参考的空间使用；线性场景空间不需要。
    """
    v = np.asarray(v, dtype=np.float64)
    out = v.copy()
    m = v > anchor
    x = np.clip(v[m], anchor, 1.0)
    t = (x - anchor) / (1.0 - anchor)
    H = (white_scene - anchor) / (1.0 - anchor)
    h = t + (H - 1.0) * (3.0 * t * t - 2.0 * t * t * t)
    out[m] = anchor + (1.0 - anchor) * h
    return out


def convert(src_path, dst_path, space="srgb", output_mode="as-is", display_mode=None,
            out_size=64, report=False, he_white=0.0, he_anchor=0.18, tone_mode="lut",
            interp="tetrahedral", ev_offset=0.0):
    if display_mode is None:
        display_mode = "srgb" if tone_mode == "preserve" else "2.4"

    src_size, table, domain_min, domain_max, title = read_cube(src_path)
    m_target_to_sgc, m_709_to_target = conversion_matrices(space)

    n = int(out_size)
    codes = uniform_grid(n)

    lin_src = decode_space(codes, space)
    lin_in = lin_src
    if he_white and he_white > he_anchor and not space.endswith("-linear"):
        y = lin_in @ space_lum_coef(space)
        expanded = highlight_expand(y, anchor=he_anchor, white_scene=he_white)
        scale = np.divide(expanded, y, out=np.ones_like(y), where=y > 0.0)
        lin_in = lin_in * scale[:, None]
    if ev_offset:
        lin_in = lin_in * (2.0 ** float(ev_offset))
    lin_sgc = lin_in @ m_target_to_sgc.T
    slog = slog3_encode(lin_sgc)

    pos = (slog - domain_min) / (domain_max - domain_min)
    sampler = sample_table_tetra if interp == "tetrahedral" else sample_table
    look = np.clip(sampler(table, pos), 0.0, 1.0)

    if tone_mode == "preserve":
        lin_look_709 = decode_display(look, display_mode)
        lin_look = lin_look_709 if space.startswith("srgb") else (lin_look_709 @ m_709_to_target.T)
        out_lin = preserve_luminance(lin_src, lin_look, space_lum_coef(space), space=space)
        out_codes = encode_space(out_lin, space)
    elif output_mode == "display-709":
        lin_709 = decode_display(look, display_mode)
        lin_out = np.clip(lin_709 @ m_709_to_target.T, 0.0, 1.0)
        out_codes = encode_space(lin_out, space)
    else:  # as-is: 原 LUT 输出值直接作为目标空间编码值（Adobe RGB -> Adobe RGB）
        out_codes = look
    out_table = out_codes.reshape(n, n, n, 3)

    # Camera Raw 菜单显示的是 TITLE 字段，因此让 TITLE 与输出文件名一致
    display_title = os.path.splitext(os.path.basename(dst_path))[0]
    os.makedirs(os.path.dirname(os.path.abspath(dst_path)), exist_ok=True)
    decode_source = tone_mode == "preserve" or output_mode == "display-709"
    encoding = f"source display gamma {display_mode}" if decode_source else "source output codes used directly"
    constraint = ", relative linear Y matched at nodes" if tone_mode == "preserve" else ""
    write_cube(dst_path, out_table, display_title, source_title=title,
               note=f"S-Log3/S-Gamut3.Cine source, target {space}, {encoding}{constraint}")

    if report:
        _print_report(table, domain_min, domain_max, m_target_to_sgc, m_709_to_target,
                      space, output_mode, display_mode, src_size, n)
        if tone_mode == "preserve":
            points = np.random.default_rng(20261121).random((20_000, 3))
            lum = space_lum_coef(space)
            expected = decode_space(points, space) @ lum
            for name, sample in (("tetrahedral", sample_table_tetra), ("trilinear", sample_table)):
                actual = decode_space(sample(out_table, points), space) @ lum
                err = np.abs(actual - expected)
                print(f"格点间相对 Y 误差 ({name}, 20000 点): P95 {np.quantile(err, 0.95):.6g}, "
                      f"max {err.max():.6g}")
    return dst_path


def _print_report(table, domain_min, domain_max, m_target_to_sgc, m_709_to_target,
                  space, output_mode, display_mode, src_size, out_size):
    np.set_printoptions(precision=7, suppress=True)
    gamma_name = {"adobergb": "2.19921875", "adobergb-linear": "1.0 (linear)",
                  "srgb": "sRGB", "srgb-linear": "1.0 (linear)",
                  "prophoto": "1.8 (ROMM RGB / ProPhoto D50)",
                  "prophoto-linear": "1.0 (linear, ProPhoto/D50)",
                  "prophoto-gamma": "sRGB 曲线 (ProPhoto/D50)"}[space]
    print("目标空间: %s (gamma %s), 输出模式: %s, 显示解码: %s" % (
        space, gamma_name, output_mode, display_mode))
    print("输入源 LUT: %d^3 -> 输出: %d^3" % (src_size, out_size))
    print("目标线性 -> S-Gamut3.Cine 线性 矩阵:")
    print(m_target_to_sgc)
    print("Rec.709 线性 -> 目标线性 矩阵:")
    print(m_709_to_target)

    # 探测: 18% 中性灰线性亮度 0.18 -> 目标空间 code
    code18 = encode_space(np.array([[0.18, 0.18, 0.18]]), space)[0]
    print("18%% 线性灰 -> %s code: %s" % (space, np.round(code18, 5)))
    slog18 = slog3_encode(np.array([0.18]))
    print("18%% 线性灰 -> S-Log3 code: %.5f (应为 420/1023=0.4106)" % slog18[0])
    print("S-Log3 code 0.41 对应的场景线性: %.5f" % slog3_decode(np.array([0.41]))[0])


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="把 S-Log3/S-Gamut3.Cine 的 .cube LUT 重制为 Camera Raw 可用的 LUT")
    ap.add_argument("input", help="输入 .cube")
    ap.add_argument("output", help="输出 .cube")
    ap.add_argument("--space", choices=("srgb", "srgb-linear", "adobergb", "adobergb-linear",
                                        "prophoto", "prophoto-gamma", "prophoto-linear"),
                    default="srgb",
                    help="生成 LUT 时假定的输入与输出空间（默认 srgb）")
    ap.add_argument("--output-mode", choices=("as-is", "display-709"), default="as-is",
                    help="as-is: 原 LUT 输出值直接作为目标空间值（目标空间 -> 目标空间，默认）；"
                         "display-709: 原 LUT 输出按 Rec.709 显示解码后再换算")
    ap.add_argument("--display-gamma", choices=DISPLAY_MODES, default=None,
                    help="原始 LUT 输出（Rec.709）的显示解码方式："
                         "preserve 模式默认 srgb，display-709 模式默认纯 Gamma 2.4")
    ap.add_argument("--size", type=int, default=64,
                    help="输出 LUT 格点数（默认 64 = Camera Raw 上限）")
    ap.add_argument("--interp", choices=("tetrahedral", "trilinear"), default="tetrahedral",
                    help="采样源 LUT 的插值方式（默认 tetrahedral，精度更高）")
    ap.add_argument("--he-white", type=float, default=0.0,
                    help="高光展开：显示白(线性1.0)对应的场景反射倍数，如 4；0=关闭")
    ap.add_argument("--he-anchor", type=float, default=0.18,
                    help="高光展开锚点（默认 0.18，即 18%% 灰保持不变）")
    ap.add_argument("--tone", choices=("lut", "preserve"), default="lut",
                    help="lut: 沿用源 LUT 影调（默认）；preserve: 在输出格点匹配输入的相对线性 Y")
    ap.add_argument("--ev-offset", type=float, default=0.0,
                    help="输入 S-Log3 查表前的曝光补偿 EV（如 ETTR LUT 的 +0.5）")
    ap.add_argument("--report", action="store_true", help="打印矩阵与探针值")
    args = ap.parse_args(argv)

    if not (2 <= args.size <= 64):
        ap.error("--size 需在 2..64 之间（Camera Raw 上限 64）")

    convert(args.input, args.output, space=args.space, output_mode=args.output_mode,
            display_mode=args.display_gamma, out_size=args.size,
            report=args.report, he_white=args.he_white, he_anchor=args.he_anchor,
            tone_mode=args.tone, interp=args.interp, ev_offset=args.ev_offset)
    print("OK: %s -> %s" % (args.input, args.output))


if __name__ == "__main__":
    sys.exit(main())
