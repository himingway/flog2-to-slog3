#!/usr/bin/env bash
# 把 output/acr_style/ 中的 Style LUT 部署到 Camera Raw 的 LUTs 目录。
# 会先清空目标目录里的 .cube（只放本项目的 LUT），并删除 ACR 索引缓存。
set -euo pipefail

resolve_acr_dir() {
  if [ -n "${1:-}" ]; then
    printf '%s\n' "$1"
    return
  fi
  if [ -n "${ACR_LUT_DIR:-}" ]; then
    printf '%s\n' "$ACR_LUT_DIR"
    return
  fi

  case "$(uname -s)" in
    Darwin)
      printf '%s\n' "$HOME/Library/Application Support/Adobe/CameraRaw/Settings/LUTs"
      return
      ;;
  esac

  if [ -n "${APPDATA:-}" ]; then
    local appdata_unix="$APPDATA"
    if command -v cygpath >/dev/null 2>&1; then
      appdata_unix="$(cygpath -u "$APPDATA")"
    fi
    printf '%s\n' "$appdata_unix/Adobe/CameraRaw/Settings/LUTs"
    return
  fi

  # WSL: 通过 Windows %APPDATA% 自动解析当前用户目录
  if command -v cmd.exe >/dev/null 2>&1 && command -v wslpath >/dev/null 2>&1; then
    local win_appdata
    win_appdata="$(cd /mnt/c 2>/dev/null || true; cmd.exe /c "echo %APPDATA%" 2>/dev/null | tr -d '\r\n')"
    if [ -n "$win_appdata" ] && [ "$win_appdata" != "%APPDATA%" ]; then
      printf '%s\n' "$(wslpath "$win_appdata")/Adobe/CameraRaw/Settings/LUTs"
      return
    fi
  fi

  return 1
}

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="$HERE/output/acr_style"

if ! DST="$(resolve_acr_dir "${1:-}")"; then
  echo "无法自动定位 Camera Raw LUTs 目录，请传入路径或设置 ACR_LUT_DIR：" >&2
  echo "  用法: $0 <CameraRaw_LUTs_DIR>" >&2
  exit 1
fi

[ -d "$SRC" ] || { echo "缺少源目录: $SRC" >&2; exit 1; }
[ -d "$DST" ] || { echo "缺少 Camera Raw LUTs 目录: $DST" >&2; exit 1; }

find "$DST" -maxdepth 1 -name '*.cube' -delete
cp -f "$SRC"/*.cube "$DST"/
find "$DST" -maxdepth 1 -name 'Index_*.dat' -delete

echo "已部署 $(find "$DST" -maxdepth 1 -name '*.cube' | wc -l) 个 LUT → $DST"
echo "请完全退出 Photoshop / Camera Raw 后重新打开。"
