"""Linear-light RGB helpers shared by the LUT builders."""

import numpy as np


# Björn Ottosson's matrices for linear sRGB and a D65 white point.
_RGB_TO_LMS = np.array([
    [0.4122214708, 0.5363325363, 0.0514459929],
    [0.2119034982, 0.6806995451, 0.1073969566],
    [0.0883024619, 0.2817188376, 0.6299787005],
])
_LMS_TO_OKLAB = np.array([
    [0.2104542553, 0.7936177850, -0.0040720468],
    [1.9779984951, -2.4285922050, 0.4505937099],
    [0.0259040371, 0.7827717662, -0.8086757660],
])
_OKLAB_TO_LMS = np.linalg.inv(_LMS_TO_OKLAB)
_LMS_TO_RGB = np.linalg.inv(_RGB_TO_LMS)


def linear_srgb_to_oklab(rgb):
    return np.cbrt(rgb @ _RGB_TO_LMS.T) @ _LMS_TO_OKLAB.T


def oklab_to_linear_srgb(lab):
    return (lab @ _OKLAB_TO_LMS.T) ** 3 @ _LMS_TO_RGB.T


def compress_rgb_to_domain(rgb, lum_coef, lower, upper, knee=0.90):
    """Compress along lines of constant linear Y toward the in-domain neutral."""
    rgb = np.asarray(rgb, dtype=np.float64)
    lower = np.broadcast_to(lower, (3,))
    upper = np.broadcast_to(upper, (3,))
    neutral_min = lower.max()
    neutral_max = upper.min()
    if neutral_min > neutral_max:
        # Custom channel ranges with no common gray have no neutral target.
        return np.clip(rgb, lower, upper)

    rgb_out = rgb.copy()
    span = upper - lower
    margin = (1.0 - knee) * span
    y_all = rgb @ lum_coef
    near_edge = np.any((rgb < lower + margin) | (rgb > upper - margin), axis=-1)
    near_edge |= (y_all < neutral_min) | (y_all > neutral_max)
    points = rgb[near_edge]
    y = y_all[near_edge]
    neutral = np.clip(y, neutral_min, neutral_max)[:, None]
    delta = points - y[:, None]

    room = np.where(delta >= 0.0, upper - neutral, neutral - lower)
    pressure = np.zeros_like(delta)
    np.divide(np.abs(delta), room, out=pressure, where=room > 0.0)
    pressure[(room == 0.0) & (delta != 0.0)] = np.inf
    ratio = np.max(pressure, axis=-1, keepdims=True)
    scale = np.ones_like(ratio)
    active = ratio > knee
    width = 1.0 - knee
    shoulder = 1.0 - width * width / (ratio[active] - knee + width)
    scale[active] = shoulder / ratio[active]
    rgb_out[near_edge] = neutral + scale * delta
    return np.clip(rgb_out, lower, upper)
