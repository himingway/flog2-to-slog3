#!/usr/bin/env bash
# 从 sources/ 重新生成全部 Style LUT（64³、四面体插值、8 位小数）。
#   Arri/Film（S-Log3 路径）→ output/acr_style/
#   Sony 技术转换 LUT       → output/not_deployed/sony/
#   Fuji（官方 F-Log2 包）  → output/acr_style/（由 build_fuji_style.py 处理）
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"
mkdir -p output/acr_style output/not_deployed/sony
find output/acr_style output/not_deployed/sony -maxdepth 1 -name '*.cube' -delete

for f in sources/sony_luts/*.cube; do
  name="$(basename "$f" .cube)"
  case "$name" in
    "Fuji "*) continue ;;                       # 由 build_fuji_style.py 用官方包重建
    "Sony "*) out="output/not_deployed/sony" ;;
    *)        out="output/acr_style" ;;
  esac
  python3 lut_to_acr.py --space srgb --tone preserve --size 64 "$f" "$out/${name} Style.cube"
done

.venv/bin/python build_fuji_style.py

echo
echo "完成。output/acr_style: $(find output/acr_style -name '*.cube' | wc -l) 个，" \
     "output/not_deployed/sony: $(find output/not_deployed/sony -name '*.cube' | wc -l) 个。"
echo "部署到 Camera Raw: ./redeploy_to_acr.sh"
