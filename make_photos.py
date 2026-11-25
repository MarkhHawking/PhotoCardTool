# -*- coding: utf-8 -*-
# -*- coding: utf-8 -*-
import os, sys, math, struct, argparse
import numpy as np
from PIL import Image
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gndtool as G
import esp as E

ROOT = r'D:\DSH_SKY_CTD\work\yundao'

def tex_map():
    m = {}
    for dp, dn, fn in os.walk(os.path.join(ROOT, 'textures')):
        for f in fn:
            rel = os.path.relpath(os.path.join(dp, f), ROOT).replace('\\', '\\')
            m[rel.lower()] = os.path.join(dp, f)
    return m
TM = None

def load_tex(paths):
    global TM
    if TM is None: TM = tex_map()
    for p in paths:
        if not p: continue
        if isinstance(p, bytes): p = p.decode('latin1')
        k = p.replace('/', '\\').lower()
        fp = TM.get(k)
        if not fp:
            base = os.path.basename(k)
            for kk, vv in TM.items():
                if kk.endswith('\\' + base): fp = vv; break
        if fp:
            try:
                im = Image.open(fp).convert('RGBA')
                return np.asarray(im, dtype=np.float32) / 255.0
            except Exception:
                pass
    return None

def render(pos, uvs, tris, tex, size=1536, ss=1):
    P = np.asarray(pos, dtype=np.float64); U = np.asarray(uvs, dtype=np.float64); T = np.asarray(tris, dtype=np.int64).reshape(-1, 3)
    x, y, z = P[:, 0], P[:, 1], P[:, 2]
    cx, cz = (x.min() + x.max()) / 2.0, (z.min() + z.max()) / 2.0
    w, hh = max(x.max() - x.min(), 1e-6), max(z.max() - z.min(), 1e-6)
    scale = 0.86 * size / max(w, hh)
    sx = (x - cx) * scale + size / 2.0
    sy = size / 2.0 - (z - cz) * scale
    zbuf = np.full((size, size), -1e9, dtype=np.float64)
    col = np.zeros((size, size, 3), dtype=np.float32)
    alpha = np.zeros((size, size), dtype=np.float32)
    v0 = np.stack([sx[T[:, 0]], sy[T[:, 0]], y[T[:, 0]]], 1)
    v1 = np.stack([sx[T[:, 1]], sy[T[:, 1]], y[T[:, 1]]], 1)
    v2 = np.stack([sx[T[:, 2]], sy[T[:, 2]], y[T[:, 2]]], 1)
    uv0, uv1, uv2 = U[T[:, 0]], U[T[:, 1]], U[T[:, 2]]
    area = (v1[:, 0] - v0[:, 0]) * (v2[:, 1] - v0[:, 1]) - (v2[:, 0] - v0[:, 0]) * (v1[:, 1] - v0[:, 1])
    L = np.array([0.35, 0.30, 0.62]); L /= np.linalg.norm(L)
    # face normal (world)
    n = np.cross(P[T[:, 1]] - P[T[:, 0]], P[T[:, 2]] - P[T[:, 0]])
    ln = np.linalg.norm(n, axis=1); ln[ln == 0] = 1
    n = n / ln[:, None]
    lam = np.abs(n @ np.array([0.25, -0.92, 0.30]))  # light from camera side
    shade = 0.42 + 0.62 * lam
    for i in range(len(T)):
        a = area[i]
        if abs(a) < 1e-9: continue
        minx = int(max(0, math.floor(min(v0[i,0], v1[i,0], v2[i,0]))))
        maxx = int(min(size-1, math.ceil(max(v0[i,0], v1[i,0], v2[i,0]))))
        miny = int(max(0, math.floor(min(v0[i,1], v1[i,1], v2[i,1]))))
        maxy = int(min(size-1, math.ceil(max(v0[i,1], v1[i,1], v2[i,1]))))
        if minx > maxx or miny > maxy: continue
        xs = np.arange(minx, maxx+1) + 0.5
        ys = np.arange(miny, maxy+1) + 0.5
        X, Y = np.meshgrid(xs, ys)
        w0 = ((v1[i,0]-X)*(v2[i,1]-Y) - (v2[i,0]-X)*(v1[i,1]-Y)) / a
        w1 = ((v2[i,0]-X)*(v0[i,1]-Y) - (v0[i,0]-X)*(v2[i,1]-Y)) / a
        w2 = 1.0 - w0 - w1
        m = (w0 >= -1e-4) & (w1 >= -1e-4) & (w2 >= -1e-4)
        if not m.any(): continue
        Z = w0*v0[i,2] + w1*v1[i,2] + w2*v2[i,2]
        sub = zbuf[miny:maxy+1, minx:maxx+1]
        mm = m & (Z > sub)
        if not mm.any(): continue
        uu = w0*uv0[i,0] + w1*uv1[i,0] + w2*uv2[i,0]
        vv = w0*uv0[i,1] + w1*uv1[i,1] + w2*uv2[i,1]
        if tex is None:
            rgb = np.array([0.82, 0.78, 0.7], dtype=np.float32)
            aa = np.ones_like(uu)
        else:
            th, tw = tex.shape[:2]
            px = np.clip((uu * tw).astype(np.int64) % tw, 0, tw-1)
            py = np.clip((vv * th).astype(np.int64) % th, 0, th-1)
            s = tex[py, px]
            rgb = s[..., :3]; aa = s[..., 3]
        ok = mm & (aa > 0.30)
        sub[mm] = Z[mm]
        csub = col[miny:maxy+1, minx:maxx+1]
        asub = alpha[miny:maxy+1, minx:maxx+1]
        csub[ok] = rgb[ok] * shade[i]
        asub[ok] = 1.0
    img = (np.clip(col, 0, 1) ** (1/1.9) * 255).astype(np.uint8)
    a = (alpha * 255).astype(np.uint8)
    out = np.dstack([img, a])
    if ss > 1:
        im = Image.fromarray(out, 'RGBA').resize((size//ss, size//ss), Image.LANCZOS)
        out = np.asarray(im)
    return out


def hair_geom2(path):
    import numpy as _np
    shapes = G.source_shapes(path)
    good = []
    for name, pos, uvs, tris, tex in shapes:
        nm = name.decode('latin1') if isinstance(name, bytes) else str(name)
        if nm.lower() in ('unp', 'head'):
            continue
        p = _np.asarray(pos, dtype=float)
        if len(p) == 0: continue
        zmin, zmax = p[:, 2].min(), p[:, 2].max()
        xw = p[:, 0].max() - p[:, 0].min()
        if zmin < 40 or xw > 75:  # body/ref shapes
            continue
        good.append((nm, pos, uvs, tris, tex))
    if not good:
        return G.hair_geometry(path)
    pos, uvs, tris, tex = [], [], [], []
    seen = set()
    for name, p, u, t, tx in good:
        sig = (len(p), tuple(round(c, 1) for c in p[0]), tuple(round(c, 1) for c in p[len(p)//2]))
        if sig in seen: continue
        seen.add(sig)
        base = len(pos); pos.extend(p); uvs.extend(u); tris.extend([base + x for x in t])
        for q in tx:
            if q and q not in tex: tex.append(q)
    return pos, uvs, tris, tex

def save_dds_dxt5(arr, path):
    h, w = arr.shape[:2]
    bh, bw = h//4, w//4
    img = arr[:bh*4, :bw*4].astype(np.int32)
    blocks = img.reshape(bh, 4, bw, 4, 4).transpose(0, 2, 1, 3, 4)
    px = blocks.reshape(bh*bw, 16, 4)
    r, g, b, a = px[:, :, 0], px[:, :, 1], px[:, :, 2], px[:, :, 3]
    c0 = ((r.max(1) >> 3) << 11) | ((g.max(1) >> 2) << 5) | (b.max(1) >> 3)
    c1 = ((r.min(1) >> 3) << 11) | ((g.min(1) >> 2) << 5) | (b.min(1) >> 3)
    swap = c0 < c1
    c0s = np.where(swap, c1, c0).astype(np.uint32); c1s = np.where(swap, c0, c1).astype(np.uint32)
    def unpack(c):
        return np.stack([((c >> 11) & 31) * 255 // 31, ((c >> 5) & 63) * 255 // 63, (c & 31) * 255 // 31], -1).astype(np.float32)
    p0, p1 = unpack(c0s), unpack(c1s)
    pal = np.stack([p0, p1, (2*p0+p1)/3, (p0+2*p1)/3], 1)
    cols = np.stack([r, g, b], -1).astype(np.float32)
    idx = (((cols[:, :, None, :] - pal[:, None, :, :]) ** 2).sum(-1)).argmin(-1).astype(np.uint32)
    color = (c0s << 16) | c1s
    for k in range(16):
        color |= idx[:, k] << (2 * k)
    a0 = a.max(1).astype(np.int32); a1 = a.min(1).astype(np.int32)
    apal = np.stack([a0, a1, (6*a0+a1)//7, (5*a0+2*a1)//7, (4*a0+3*a1)//7, (3*a0+4*a1)//7, (2*a0+5*a1)//7, (a0+6*a1)//7], 1)
    ad = np.abs(a[:, :, None] - apal[:, None, :])
    aidx = ad.argmin(-1).astype(np.uint32)
    alpha = (a0.astype(np.uint32) | (a1.astype(np.uint32) << 8))
    for k in range(16):
        alpha |= aidx[:, k] << (16 + 3 * k)
    out = np.empty((bh*bw, 16), dtype=np.uint8)
    for j in range(8):
        out[:, j] = ((alpha >> (8*j)) & 0xFF).astype(np.uint8)
        out[:, 8+j] = ((color >> (8*j)) & 0xFF).astype(np.uint8)
    data = out.tobytes()
    hdr = b'DDS ' + struct.pack('<7I', 124, 0x00081007, bh*4, bw*4, len(data), 0, 1)
    hdr += b'\x00' * 44
    hdr += struct.pack('<2I4s5I', 32, 4, b'DXT5', 0, 0, 0, 0, 0)
    hdr += struct.pack('<4I', 0x1000, 0, 0, 0)
    hdr += b'\x00' * 4
    open(path, 'wb').write(hdr + data)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--styles', default='')
    ap.add_argument('--all', action='store_true')
    ap.add_argument('--out', default=r'D:\DSH_SKY_CTD\work\out\photos')
    ap.add_argument('--size', type=int, default=1024)
    ap.add_argument('--limit', type=int, default=0)
    ap.add_argument('--bg', default='#2e2e2e')
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    entries = G.source_entries()[1]
    by = {e['style']: e for e in entries}
    styles = [s for s in a.styles.split(',') if s] if a.styles else list(by)
    if a.limit: styles = styles[:a.limit]
    for st in styles:
        e = by.get(st)
        if not e: print('skip', st); continue
        nif_path = os.path.join(G.ROOT if hasattr(G,'ROOT') else ROOT, 'meshes', e['mod4'].replace('\\', os.sep))
        try:
            pos, uvs, tris, tex = hair_geom2(nif_path)
        except Exception as ex:
            print('geom fail', st, ex); continue
        img = render(pos, uvs, tris, load_tex(tex), size=a.size)
        png = os.path.join(a.out, st + '.png')
        Image.fromarray(img, 'RGBA').save(png)
        bg = tuple(int(a.bg.lstrip('#')[i:i+2], 16) for i in (0, 2, 4))
        al = img[..., 3:4].astype(np.float32) / 255.0
        comp = (img[..., :3].astype(np.float32) * al + np.array(bg, dtype=np.float32) * (1 - al)).astype(np.uint8)
        flat = np.dstack([comp, np.full((img.shape[0], img.shape[1]), 255, np.uint8)])
        dds = os.path.join(a.out, st + '.dds')
        save_dds_dxt5(flat, dds)
        print('ok', st, len(tris), 'tris ->', png, os.path.getsize(dds))

if __name__ == '__main__':
    main()
