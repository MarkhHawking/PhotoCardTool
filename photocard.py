# -*- coding: utf-8 -*-
r"""photo_card 生成器（02.dds 同款木框卡片）

输出（文件名取输入文件主名）：
  <name>.dds          1024x1024 BC7_UNORM 线性 DX10，木框+深灰卡片，卡片内左半=正面、右半=侧面
  <name>_front.png    正面（1024x1024，深灰卡片底）
  <name>_side.png     侧面（1024x1024，深灰卡片底）

用法：python photocard.py "路径\头发.nif" [--out 目录]
      python photocard.py "路径\已拼好.png"     # 图片模式：左右拆开 + 转 BC7
"""
import argparse, os, re, shutil, struct, subprocess, sys
import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render_blend as RB

TEXCONV = r'D:\Modding\SSEEdit 4.1.5f-164-4-1-5f-1714283656\SSEEdit 4.1.5f\Edit Scripts\Texconv.exe'
TMP = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'work', 'tmp')
os.makedirs(TMP, exist_ok=True)
BG = (46, 46, 46)
BASE_CARD = r'D:\DSH_SKY_CTD\work\02.png'   # 02.dds 的 1024 预览图（木框+卡片），存在则用它当底板
CARD_RECT = (12, 238, 1012, 788)                     # 卡片区域


def _u32(b, o): return struct.unpack_from('<I', b, o)[0]
def _i32(b, o): return struct.unpack_from('<i', b, o)[0]


def read_texset(b, h, shader):
    import nif as N
    if shader < 0 or N.tname(h, shader) != 'BSLightingShaderProperty':
        return []
    so = h['offsets'][shader]
    t = _i32(b, so + 40)
    if not (0 <= t < h['nb']) or N.tname(h, t) != 'BSShaderTextureSet':
        return []
    o = h['offsets'][t]; cnt = _u32(b, o); p = o + 4; out = []
    for _ in range(cnt):
        ln = _u32(b, p); p += 4
        out.append(b[p:p+ln].rstrip(b'\x00')); p += ln
    return out


def load_geometry(path):
    import nif as N
    b = open(path, 'rb').read(); h = N.read_header(b)
    geo = []
    for i in range(h['nb']):
        if N.tname(h, i) != 'BSTriShape':
            continue
        sh = N.parse_tri_shape(b, h['offsets'][i])
        nm = h['strings'][sh['name']] if 0 <= sh['name'] < len(h['strings']) else ''
        if any(k in nm.lower() for k in ('virtual', 'femalehead', 'unp', 'hairline')):
            continue
        pos, uvs, tris = [], [], []
        if sh['num_verts'] > 0:
            for p_, uv_, _n in N.read_vertices(b, sh):
                pos.append(p_); uvs.append(uv_ if uv_ else (0.0, 0.0))
            tris = N.read_triangles(b, sh)
        elif sh['skin'] >= 0:
            o = h['offsets'][sh['skin']]; part = -1
            for k in range(min(10, h['sizes'][sh['skin']] // 4)):
                r = _u32(b, o + 4 * k)
                if 0 <= r < h['nb'] and N.tname(h, r) == 'NiSkinPartition':
                    part = r; break
            if part >= 0:
                ps = N.parse_skin_partition(b, h['offsets'][part], h['userver'])
                pos, uvs, tris = N.partition_geometry(b, ps)
        if not pos:
            continue
        flat = []
        for tri in tris:
            if isinstance(tri, tuple):
                flat.extend(tri)
            else:
                flat.append(tri)
        geo.append((nm, pos, uvs, flat, read_texset(b, h, sh['shader'])))
    pos, uvs, tris, tex = [], [], [], []
    seen = set()
    for nm, p, u, t, tx in geo:
        sig = (len(p), tuple(round(c, 1) for c in p[0]), tuple(round(c, 1) for c in p[len(p)//2]))
        if sig in seen:
            continue
        seen.add(sig)
        base = len(pos); pos.extend(p); uvs.extend(u); tris.extend([base + x for x in t])
        for q in tx:
            if q and q not in tex:
                tex.append(q)
    return pos, uvs, tris, tex


def find_root(p):
    d = os.path.dirname(p)
    while d:
        if os.path.isdir(os.path.join(d, 'textures')):
            return d
        nd = os.path.dirname(d)
        if nd == d:
            return os.path.dirname(p)
        d = nd
    return os.path.dirname(p)


def load_texture(paths, root):
    for raw in paths:
        rel = (raw.decode('latin1') if isinstance(raw, bytes) else str(raw)).replace('/', '\\')
        cand = os.path.join(root, rel)
        if not os.path.exists(cand):
            low = os.path.basename(rel).lower()
            for dp, dn, fn in os.walk(os.path.join(root, 'textures')):
                hit = [f for f in fn if f.lower() == low]
                if hit:
                    cand = os.path.join(dp, hit[0]); break
        if not os.path.exists(cand):
            continue
        try:
            im = Image.open(cand).convert('RGBA')
        except Exception:
            try:
                td = os.path.join(TMP, 'tex_%d' % __import__('time').time_ns()); os.makedirs(td, exist_ok=True)
                subprocess.run([TEXCONV, '-ft', 'png', '-m', '1', '-y', '-o', td, cand],
                               check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                im = Image.open(os.path.join(td, os.path.splitext(os.path.basename(cand))[0] + '.png')).convert('RGBA')
                shutil.rmtree(td, ignore_errors=True)
            except Exception:
                continue
        return np.asarray(im).astype(np.float32) / 255.0
    return None


def render_view(pos, uvs, tris, tex, mode, size, prm=None):
    P = np.asarray(pos, float)
    P[:, 1] *= -1.0          # 从正面看（否则看到头发内侧，像兜帽/人脸）
    if mode == 'side':
        th = np.deg2rad(65.0)
        X = P[:, 0] * np.cos(th) - P[:, 1] * np.sin(th)
        Y = P[:, 0] * np.sin(th) + P[:, 1] * np.cos(th)
        P = np.stack([X, Y, P[:, 2]], axis=1)
    # 保留贴图 alpha（半透明发丝），配合 bilinear + 超采样还原 NifSkope 那种细节
    return RB.render_blend(P, uvs, tris, tex, size=size * 2, prm=prm)


def panel(img, w, h):
    try:
        from scipy import ndimage
    except Exception:
        ndimage = None
    im = Image.fromarray(img, 'RGBA')
    arr = np.asarray(im).copy()
    if ndimage is None:
        return _panel_finish(im, w, h)
    mask = arr[..., 3] > 40
    lab, n = ndimage.label(mask)
    if n > 1:
        sizes = ndimage.sum(mask, lab, range(1, n + 1))
        keep = np.isin(lab, [i + 1 for i, s_ in enumerate(sizes) if s_ >= sizes.max() * 0.004])
        arr[..., 3] = np.where(keep, arr[..., 3], 0)
        im = Image.fromarray(arr, 'RGBA')
    A = np.asarray(im)[..., 3]
    rows = np.where((A > 8).sum(1) > A.shape[1] * 0.01)[0]
    cols = np.where((A > 8).sum(0) > A.shape[0] * 0.01)[0]
    if len(rows) and len(cols):
        im = im.crop((cols[0], rows[0], cols[-1] + 1, rows[-1] + 1))
    r = min(w * 0.92 / max(im.width, 1), h * 0.94 / max(im.height, 1))
    im = im.resize((max(1, int(im.width * r)), max(1, int(im.height * r))), Image.LANCZOS)
    card = Image.new('RGBA', (w, h), BG + (255,))
    card.alpha_composite(im, ((w - im.width) // 2, (h - im.height) // 2))
    return card


def _panel_finish(im, w, h):
    A = np.asarray(im)[..., 3]
    rows = np.where((A > 8).sum(1) > A.shape[1] * 0.01)[0]
    cols = np.where((A > 8).sum(0) > A.shape[0] * 0.01)[0]
    if len(rows) and len(cols):
        im = im.crop((cols[0], rows[0], cols[-1] + 1, rows[-1] + 1))
    r = min(w * 0.92 / max(im.width, 1), h * 0.94 / max(im.height, 1))
    im = im.resize((max(1, int(im.width * r)), max(1, int(im.height * r))), Image.LANCZOS)
    card = Image.new('RGBA', (w, h), BG + (255,))
    card.alpha_composite(im, ((w - im.width) // 2, (h - im.height) // 2))
    return card


def to_bc7(rgb, out_dds):
    td = os.path.join(TMP, 'bc7_%d' % __import__('time').time_ns()); os.makedirs(td, exist_ok=True)
    src = os.path.join(td, 'in.png'); rgb.save(src)
    subprocess.run([TEXCONV, '-f', 'BC7_UNORM', '-dx10', '-m', '1', '-y', '-o', td, src],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    shutil.move(os.path.join(td, 'in.DDS'), out_dds)
    shutil.rmtree(td, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('input', nargs='?', default='')
    ap.add_argument('--front', default=''); ap.add_argument('--side', default='')
    ap.add_argument('--name', default='')
    ap.add_argument('--out', default=''); ap.add_argument('--size', type=int, default=1024)
    a = ap.parse_args()
    if a.front and a.side:
        stem = a.name or os.path.splitext(os.path.basename(a.front))[0]
        if stem.endswith('_front'):
            stem = stem[:-6]
        safe = re.sub(r'[\\/:*?"<>|]', '_', stem)
        outdir = a.out or os.path.join(os.path.dirname(os.path.abspath(a.front)), 'photo_card')
        os.makedirs(outdir, exist_ok=True)
        f = Image.open(a.front).convert('RGBA'); s_ = Image.open(a.side).convert('RGBA')
        f.convert('RGB').resize((a.size, a.size), Image.LANCZOS).save(os.path.join(outdir, safe + '_front.png'))
        s_.convert('RGB').resize((a.size, a.size), Image.LANCZOS).save(os.path.join(outdir, safe + '_side.png'))
        _make_card(f.convert('RGB'), s_.convert('RGB'), a.size, safe, outdir)
        print('OK', os.path.join(outdir, safe + '.dds'))
        return
    src = os.path.abspath(a.input); stem = os.path.splitext(os.path.basename(src))[0]
    safe = re.sub(r'[\\/:*?"<>|]', '_', stem)
    outdir = a.out or os.path.join(os.path.dirname(src), 'photo_card'); os.makedirs(outdir, exist_ok=True)

    if src.lower().endswith(('.png', '.dds', '.jpg', '.jpeg', '.tga')):
        im = Image.open(src).convert('RGB'); w, h = im.size
        front, side = im.crop((0, 0, w//2, h)), im.crop((w//2, 0, w, h))
        front.save(os.path.join(outdir, safe + '_front.png')); side.save(os.path.join(outdir, safe + '_side.png'))
        im.save(os.path.join(outdir, 'photo_card.png'))
        to_bc7(im, os.path.join(outdir, safe + '.dds')); print('OK(direct)', safe); return

    pos, uvs, tris, tex = load_geometry(src)
    root = find_root(src); t = load_texture(tex, root)
    f = render_view(pos, uvs, tris, t, 'front', a.size)
    s = render_view(pos, uvs, tris, t, 'side', a.size)
    S = a.size
    pf = panel(f, S, S); pf.save(os.path.join(outdir, safe + '_front.png'))
    ps = panel(s, S, S); ps.save(os.path.join(outdir, safe + '_side.png'))

    _make_card(pf, ps, S, safe, outdir)


def _make_card(pf, ps, S, safe, outdir):
    # 02 风格底板
    if os.path.exists(BASE_CARD):
        base = Image.open(BASE_CARD).convert('RGB').resize((S, S), Image.LANCZOS)
    else:
        base = Image.new('RGB', (S, S), (30, 26, 22))
    x0, y0, x1, y1 = CARD_RECT
    from PIL import ImageDraw
    ImageDraw.Draw(base).rectangle((x0, y0, x1, y1), fill=BG)
    cw, ch = x1 - x0, y1 - y0
    half = cw // 2
    base.paste(pf.resize((half-8, ch-8), Image.LANCZOS), (x0+4, y0+4))
    base.paste(ps.resize((cw-half-8, ch-8), Image.LANCZOS), (x0+half+4, y0+4))
    base.save(os.path.join(outdir, 'photo_card.png'))
    to_bc7(base, os.path.join(outdir, safe + '.dds'))


if __name__ == '__main__':
    main()
