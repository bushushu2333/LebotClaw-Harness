#!/usr/bin/env python3
# 立绘抠图：纯黑底 → 透明 PNG（洪泛填充只去与边缘连通的黑色，保住角色内部深色）
# 用法: python3 matte_sprites.py
import numpy as np
from PIL import Image, ImageFilter
from pathlib import Path

RAW = Path(__file__).parent.parent / 'raw_生图原图'
OUT = Path(__file__).parent.parent / 'assets' / 'story'
THRESH = 42          # 低于此亮度视为"黑"
FEATHER = 1.2        # 边缘羽化

def matte(name):
    src = RAW / f'{name}.png'
    if not src.exists():
        print(f'⏭  {name} 不存在，跳过'); return
    im = Image.open(src).convert('RGBA')
    a = np.asarray(im).astype(np.uint8)
    # 自适应背景色：取四角中位数（模型有时无视"纯黑底"返回白底）
    corners = np.concatenate([a[:8, :8, :3].reshape(-1, 3), a[:8, -8:, :3].reshape(-1, 3),
                              a[-8:, :8, :3].reshape(-1, 3), a[-8:, -8:, :3].reshape(-1, 3)])
    bgc = np.median(corners, axis=0)
    dist = np.abs(a[..., :3].astype(int) - bgc).max(axis=2)
    dark = dist < THRESH
    print(f'   {name} 检测到背景色 RGB={bgc.astype(int).tolist()}')

    # 洪泛：从四边种子出发，在 dark 区域内传播
    seed = np.zeros_like(dark)
    seed[0, :] = dark[0, :]; seed[-1, :] = dark[-1, :]
    seed[:, 0] = dark[:, 0]; seed[:, -1] = dark[:, -1]
    bg = seed.copy()
    while True:
        grown = bg.copy()
        grown[1:, :] |= bg[:-1, :]; grown[:-1, :] |= bg[1:, :]
        grown[:, 1:] |= bg[:, :-1]; grown[:, :-1] |= bg[:, 1:]
        grown &= dark
        if (grown == bg).all(): break
        bg = grown

    alpha = np.where(bg, 0, 255).astype(np.uint8)
    # 边缘羽化：对 alpha 轻微高斯模糊，去掉黑边锯齿
    aimg = Image.fromarray(alpha).filter(ImageFilter.GaussianBlur(FEATHER))
    alpha = np.asarray(aimg)
    # 半透明像素里残存的黑色压暗一点，防黑边光晕
    out = a.copy()
    out[..., 3] = alpha
    res = Image.fromarray(out)

    # 按内容裁剪（留 2% 边距）
    ys, xs = np.where(alpha > 8)
    if len(xs):
        mx = int(res.width * 0.02); my = int(res.height * 0.02)
        box = (max(0, xs.min()-mx), max(0, ys.min()-my), min(res.width, xs.max()+mx), min(res.height, ys.max()+my))
        res = res.crop(box)
    res.save(OUT / f'{name}.png')
    print(f'✅ {name} → {OUT/name}.png  {res.size}')

if __name__ == '__main__':
    import sys
    names = sys.argv[1:] or ['sp_wave','sp_smile','sp_point','sp_think','sp_excited','sp_proud','sp_curious','sp_serious']
    for n in names: matte(n)
