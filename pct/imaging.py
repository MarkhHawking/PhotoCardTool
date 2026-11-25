# -*- coding: utf-8 -*-
"""面板裁切、BC7 编码、卡片合成、run_card 入口。"""
import os
import shutil
import subprocess

from PIL import Image, ImageDraw

from .paths import BASE_CARD, CACHE_DIR, TEXCONV
from .scene import load_scene, render_view


CARD_RECT = (12, 238, 1012, 788)
BG = (46, 46, 46)

def panel(img):
    import numpy as np
    from PIL import Image
    im = Image.fromarray(img, 'RGBA')
    try:
        from scipy import ndimage
        arr = np.asarray(im).copy()
        mask = arr[..., 3] > 40
        lab, n = ndimage.label(mask)
        if n > 1:
            sizes = ndimage.sum(mask, lab, range(1, n + 1))
            keep = np.isin(lab, [i + 1 for i, s in enumerate(sizes) if s >= sizes.max() * 0.004])
            arr[..., 3] = np.where(keep, arr[..., 3], 0)
            im = Image.fromarray(arr, 'RGBA')
    except Exception:
        pass
    A = np.asarray(im)[..., 3]
    rows = np.where((A > 8).sum(1) > A.shape[1] * 0.01)[0]
    cols = np.where((A > 8).sum(0) > A.shape[0] * 0.01)[0]
    if len(rows) and len(cols):
        im = im.crop((cols[0], rows[0], cols[-1] + 1, rows[-1] + 1))
    return im.convert('RGBA')


def to_bc7(img, out_dds):
    if not os.path.exists(TEXCONV):
        raise RuntimeError('找不到 Texconv.exe（应放在 materials 目录）：' + TEXCONV)
    base = CACHE_DIR.get('dir') or os.path.dirname(os.path.abspath(out_dds))
    tmp = os.path.join(base, '_bc7_tmp')
    try:
        os.makedirs(tmp, exist_ok=True)
    except Exception:
        tmp = os.path.join(os.path.dirname(os.path.abspath(out_dds)), '_bc7_tmp')
        os.makedirs(tmp, exist_ok=True)
    png = os.path.join(tmp, 'card_in.png')
    img.convert('RGB').save(png)
    p = subprocess.run([TEXCONV, '-f', 'BC7_UNORM', '-dx10', '-m', '1', '-y', '-o', tmp, png],
                       capture_output=True)
    made = os.path.join(tmp, 'card_in.dds')
    if p.returncode != 0 or not os.path.exists(made):
        raise RuntimeError('BC7 编码失败')
    shutil.move(made, out_dds)
    shutil.rmtree(tmp, ignore_errors=True)


def compose_card(front_img, side_img, size, fill=92.0, hscale=100.0):
    """把正/侧两张图按卡片版式合成（含 画面占比 / 横向比例），返回 PIL RGB。"""
    from PIL import Image, ImageDraw
    base = Image.open(BASE_CARD).convert('RGB')
    if base.size != (size, size):
        base = base.resize((size, size), Image.LANCZOS)
    d = ImageDraw.Draw(base)
    sx = size / 1024.0
    x0, y0, x1, y1 = [int(v * sx) for v in CARD_RECT]
    d.rectangle([x0, y0, x1, y1], fill=BG)
    half = (x1 - x0) // 2
    ph = y1 - y0 - 8

    def put(im, px):
        im = im.convert('RGBA')
        target = ph * (fill / 100.0)
        r = min(target / max(im.height, 1), (half - 12) / max(im.width, 1))
        t = im.resize((max(1, int(im.width * r * hscale / 100.0)), max(1, int(im.height * r))), Image.LANCZOS)
        base.paste(t, (px + (half - 4 - t.width) // 2, y0 + 4 + (ph - t.height) // 2), t)

    put(front_img, x0 + 4)
    put(side_img, x0 + half + 4)
    return base


def build_card(front_img, side_img, size, outdir, name, fill=92, hscale=100.0):
    from PIL import Image
    img = compose_card(front_img, side_img, size, fill, hscale)
    os.makedirs(outdir, exist_ok=True)
    png = os.path.join(outdir, 'photo_card.png')
    img.save(png)
    for im, sfx in ((front_img, '_front'), (side_img, '_side')):
        c = Image.new('RGB', (size, size), BG)
        r = min(0.9 * size / max(im.width, 1), 0.9 * size / max(im.height, 1))
        t = im.convert('RGBA').resize((max(1, int(im.width * r)), max(1, int(im.height * r))), Image.LANCZOS)
        c.paste(t, ((size - t.width) // 2, (size - t.height) // 2), t)
        c.save(os.path.join(outdir, name + sfx + '.png'))
    dds = os.path.join(outdir, name + '.dds')
    to_bc7(img, dds)
    return png, dds


def run_card(nif_path, outdir, size, name, log=print, fill=92, hscale=100.0,
             yaw_f=0.0, pitch_f=0.0, yaw_s=65.0, pitch_s=0.0, prm=None):
    scene = load_scene(nif_path)
    log('几何: %d 顶点 / %d 三角形' % (len(scene['pos']), len(scene['tris']) // 3))
    front = panel(render_view(scene, size, yaw_f, pitch_f, prm))
    side = panel(render_view(scene, size, yaw_s, pitch_s, prm))
    return build_card(front, side, size, outdir, name, fill, hscale)



# ==================== 供图拼卡 ====================
def square_crop(img, size=1024):
    """居中取最大正方形并缩放到 size×size。"""
    from PIL import Image
    im = img.convert('RGB')
    s = min(im.width, im.height)
    x = (im.width - s) // 2
    y = (im.height - s) // 2
    return im.crop((x, y, x + s, y + s)).resize((size, size), Image.LANCZOS)


def dds_size(path):
    try:
        b = open(path, 'rb').read(32)
        if b[:4] != b'DDS ':
            return None
        return struct.unpack_from('<I', b, 16)[0], struct.unpack_from('<I', b, 12)[0]
    except Exception:
        return None


