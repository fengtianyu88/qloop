#!/usr/bin/env python3
"""获取 qloop 的 stargazers 数据并生成 SVG 趋势图

用法:
    GITHUB_TOKEN=ghp_xxx python3 scripts/gen_star_trend.py

Token 只从环境变量读取,不硬编码。
需要 public_repo 或 repo scope(读取 stargazers)。
"""
import json
import os
import urllib.request
from datetime import datetime, timezone

TOKEN = os.environ.get("GITHUB_TOKEN", "")
REPO = "fengtianyu88/qloop"

if not TOKEN:
    print("ERROR: 请设置 GITHUB_TOKEN 环境变量")
    print("  export GITHUB_TOKEN=ghp_xxx  # 或在命令前加")
    print("  GITHUB_TOKEN=ghp_xxx python3 scripts/gen_star_trend.py")
    exit(1)

# 1. 获取 stargazers(带 starred_at 时间戳)
headers = {
    "Authorization": f"token {TOKEN}",
    "Accept": "application/vnd.github.star+json",  # 这个 accept header 返回 starred_at
    "User-Agent": "qloop-star-trend",
}

stars = []
page = 1
while True:
    url = f"https://api.github.com/repos/{REPO}/stargazers?per_page=100&page={page}"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"Error fetching page {page}: {e}")
        break
    if not data:
        break
    for s in data:
        starred_at = s.get("starred_at")
        if starred_at:
            stars.append(starred_at)
    print(f"Page {page}: {len(data)} stars (total so far: {len(stars)})")
    if len(data) < 100:
        break
    page += 1
    if page > 10:  # 安全上限
        break

print(f"\nTotal stars fetched: {len(stars)}")

if not stars:
    stars = ["2026-07-22T00:00:00Z"]  # 至少有一个点(今天),避免空图

# 2. 生成 SVG 趋势图
stars_sorted = sorted(stars)
# 累积 star 数:每个时间点的 star 总数
cumulative = []
for i, ts in enumerate(stars_sorted, 1):
    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    cumulative.append((dt, i))

# SVG 参数
W, H = 720, 260
PAD_L, PAD_R, PAD_T, PAD_B = 60, 30, 30, 50
plot_w = W - PAD_L - PAD_R
plot_h = H - PAD_T - PAD_B

# 时间范围
t_min = cumulative[0][0]
t_max = cumulative[-1][0]
# 确保 t_max 至少是今天
now = datetime.now(timezone.utc)
if t_max < now:
    t_max = now
# 如果只有1个点,扩展范围到前后7天
if len(cumulative) == 1:
    from datetime import timedelta
    t_min = t_min - timedelta(days=1)
    t_max = t_max + timedelta(days=1)

def t_to_x(t):
    if t_max == t_min:
        return PAD_L + plot_w / 2
    return PAD_L + (t - t_min).total_seconds() / (t_max - t_min).total_seconds() * plot_w

def n_to_y(n):
    max_n = max(cumulative[-1][1], 1)
    return PAD_T + plot_h - (n / max_n) * plot_h

# 生成折线 path
path_points = []
for dt, n in cumulative:
    x = t_to_x(dt)
    y = n_to_y(n)
    path_points.append((x, y))

# 折线 path
line_path = "M " + " L ".join(f"{x:.1f} {y:.1f}" for x, y in path_points)
# 填充区域 path(折线 + 到底边)
fill_path = line_path + f" L {path_points[-1][0]:.1f} {PAD_T + plot_h:.1f} L {path_points[0][0]:.1f} {PAD_T + plot_h:.1f} Z"

# Y 轴刻度
max_n = max(cumulative[-1][1], 1)
y_ticks = list(range(0, max_n + 1, max(1, max_n // 5)))

# X 轴刻度(日期)
from datetime import timedelta
x_ticks_count = min(6, max(2, len(cumulative)))
x_tick_dates = []
for i in range(x_ticks_count):
    frac = i / (x_ticks_count - 1)
    t = t_min + (t_max - t_min) * frac
    x_tick_dates.append(t)

svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif">
  <defs>
    <linearGradient id="starGrad" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#ffcb2d" stop-opacity="0.5"/>
      <stop offset="100%" stop-color="#ffcb2d" stop-opacity="0.05"/>
    </linearGradient>
  </defs>
  <rect width="{W}" height="{H}" fill="#ffffff" rx="8"/>

  <!-- 标题 -->
  <text x="{PAD_L}" y="20" font-size="14" font-weight="600" fill="#24292f">Star Trend</text>
  <text x="{W - PAD_R}" y="20" font-size="12" fill="#8b949e" text-anchor="end">{REPO}</text>

  <!-- 网格线 + Y 轴标签 -->
'''

for yt in y_ticks:
    y = n_to_y(yt)
    svg += f'  <line x1="{PAD_L}" y1="{y:.1f}" x2="{W - PAD_R}" y2="{y:.1f}" stroke="#eaecef" stroke-width="1"/>\n'
    svg += f'  <text x="{PAD_L - 8}" y="{y + 4:.1f}" font-size="11" fill="#6e7681" text-anchor="end">{yt}</text>\n'

svg += f'''
  <!-- 填充区域 -->
  <path d="{fill_path}" fill="url(#starGrad)"/>

  <!-- 折线 -->
  <path d="{line_path}" fill="none" stroke="#ffcb2d" stroke-width="2" stroke-linejoin="round"/>

  <!-- 数据点 -->
'''
for x, y in path_points:
    svg += f'  <circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="#ffcb2d" stroke="#ffffff" stroke-width="1.5"/>\n'

svg += f'''
  <!-- X 轴 -->
  <line x1="{PAD_L}" y1="{PAD_T + plot_h}" x2="{W - PAD_R}" y2="{PAD_T + plot_h}" stroke="#d0d7de" stroke-width="1"/>

  <!-- X 轴标签 -->
'''
for t in x_tick_dates:
    x = t_to_x(t)
    label = t.strftime("%m/%d")
    svg += f'  <text x="{x:.1f}" y="{H - PAD_B + 18}" font-size="11" fill="#6e7681" text-anchor="middle">{label}</text>\n'

svg += f'''
  <!-- 右下角总数 -->
  <text x="{W - PAD_R}" y="{H - 8}" font-size="11" fill="#8b949e" text-anchor="end">Total: {max_n} stars</text>
</svg>
'''

# 3. 写入文件
output_path = "/home/tiany/qloop/docs/star-trend.svg"
with open(output_path, "w", encoding="utf-8") as f:
    f.write(svg)

print(f"\nSVG generated: {output_path}")
print(f"  Stars: {len(stars)}")
print(f"  Date range: {t_min.strftime('%Y-%m-%d')} → {t_max.strftime('%Y-%m-%d')}")
