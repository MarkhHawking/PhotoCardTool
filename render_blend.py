import math, numpy as np
from PIL import Image

def render_blend(pos, uvs, tris, tex, size=2048, prm=None):
    d = dict(amb=0.50, diff=0.55, rim=0.18, spec=0.24, specpow=24.0,
             alpha=1.8, depth=0, gamma=1.8, bright=1.0, contrast=1.0, tint=(1.0, 1.0, 1.0),
             autobright=1)
    if prm: d.update({k: v for k, v in prm.items() if k in d})
    P = np.asarray(pos, float); U = np.asarray(uvs, float); T = np.asarray(tris, np.int64).reshape(-1, 3)
    x, y, z = P[:, 0], P[:, 1], P[:, 2]
    cx, cz = (x.min()+x.max())/2, (z.min()+z.max())/2
    w, hh = max(x.max()-x.min(), 1e-6), max(z.max()-z.min(), 1e-6)
    s = 0.9*size/max(w, hh)
    sx = (x-cx)*s + size/2; sy = size/2 - (z-cz)*s
    zb = np.full((size, size), -1e9); col = np.zeros((size, size, 3)); al = np.zeros((size, size))
    th, tw = tex.shape[:2]
    fn = np.cross(P[T[:, 1]]-P[T[:, 0]], P[T[:, 2]]-P[T[:, 0]])
    ln = np.linalg.norm(fn, axis=1); ln[ln == 0] = 1; fn = fn/ln[:, None]
    # 顶点法线（面积加权平滑）：NifSkope 的观感来自平滑法线，逐三角形平光会变成“笔刷条纹”
    vn = np.zeros_like(P)
    for k in range(3):
        np.add.at(vn, T[:, k], fn * ln[:, None])
    vl = np.linalg.norm(vn, axis=1); vl[vl == 0] = 1; vn = vn / vl[:, None]
    L = np.array([0.25, -0.92, 0.30], np.float32); L = L / np.linalg.norm(L)
    V = np.array([0.0, -1.0, 0.0], np.float32)
    UV_OFF = [float(U[:, 1].max()) > 1.001]
    v = [np.stack([sx[T[:, i]], sy[T[:, i]], y[T[:, i]]], 1) for i in range(3)]
    for i in range(len(T)):
        x0, y0 = v[0][i, 0], v[0][i, 1]; x1, y1 = v[1][i, 0], v[1][i, 1]; x2, y2 = v[2][i, 0], v[2][i, 1]
        ar = (x1-x0)*(y2-y0)-(x2-x0)*(y1-y0)
        if abs(ar) < 1e-9: continue
        minx = int(max(0, math.floor(min(x0, x1, x2)))); maxx = int(min(size-1, math.ceil(max(x0, x1, x2))))
        miny = int(max(0, math.floor(min(y0, y1, y2)))); maxy = int(min(size-1, math.ceil(max(y0, y1, y2))))
        if minx > maxx or miny > maxy: continue
        X, Y = np.meshgrid(np.arange(minx, maxx+1)+0.5, np.arange(miny, maxy+1)+0.5)
        w0 = ((x1-X)*(y2-Y)-(x2-X)*(y1-Y))/ar
        w1 = ((x2-X)*(y0-Y)-(x0-X)*(y2-Y))/ar
        w2 = 1-w0-w1
        m = (w0 >= -1e-4) & (w1 >= -1e-4) & (w2 >= -1e-4)
        if not m.any(): continue
        Z = w0*v[0][i, 2]+w1*v[1][i, 2]+w2*v[2][i, 2]
        sub = zb[miny:maxy+1, minx:maxx+1]
        use_depth = bool(d['depth']) or UV_OFF[0]   # extra part 双面壳：强制深度，避免正反两层叠成斑块
        mm = (m & (Z > sub)) if use_depth else m
        if not mm.any(): continue
        uu = w0*U[T[i, 0], 0]+w1*U[T[i, 1], 0]+w2*U[T[i, 2], 0]
        vv = w0*U[T[i, 0], 1]+w1*U[T[i, 1], 1]+w2*U[T[i, 2], 1]
        # extra part 的 UV 常整体 +1（贴图平铺）：按 mod 取回 0..1，方向保持原样
        # （早先写成 1-mod 会把整张图上下镜像：v 只要略微超过 1 就会把整个网格翻掉，
        #  表现为发丝错位、白缝、明暗相反）
        uu = np.mod(uu, 1.0)
        if UV_OFF[0]:
            vv = np.mod(vv, 1.0)
        else:
            vv = np.clip(vv, 0.0, 0.999999)
        fx = np.clip(uu*tw - 0.5, 0, tw-1.001); fy = np.clip(vv*th - 0.5, 0, th-1.001)
        x0i = fx.astype(np.int64); y0i = fy.astype(np.int64)
        tx = (fx - x0i)[..., None]; ty = (fy - y0i)[..., None]
        x1i = np.minimum(x0i+1, tw-1); y1i = np.minimum(y0i+1, th-1)
        c00 = tex[y0i, x0i]; c10 = tex[y0i, x1i]; c01 = tex[y1i, x0i]; c11 = tex[y1i, x1i]
        top = c00*(1-tx) + c10*tx; bot = c01*(1-tx) + c11*tx
        samp = top*(1-ty) + bot*ty
        rgb = samp[..., :3]; a = samp[..., 3]
        sub[mm] = Z[mm]
        c = col[miny:maxy+1, minx:maxx+1]; aa_ = al[miny:maxy+1, minx:maxx+1]
        # 逐像素法线插值 → 平滑明暗（NifSkope 观感的关键）
        n = (w0[..., None]*vn[T[i, 0]] + w1[..., None]*vn[T[i, 1]] + w2[..., None]*vn[T[i, 2]])
        nl = np.linalg.norm(n, axis=-1); nl[nl == 0] = 1; n = n/nl[..., None]
        lam = np.abs(n @ L)
        rim = np.clip(1.0 - np.abs(n @ V), 0, 1) ** 2
        spec = np.clip(n @ np.array([0.3, -0.9, 0.35]), 0, 1) ** d['specpow']
        shade = d['amb'] + d['diff']*lam + d['rim']*rim + d['spec']*spec
        if UV_OFF[0]:
            shade = np.minimum(shade, 0.95)   # extra part 双面壳：压掉高光白块
        aa = np.clip(a * d['alpha'], 0, 1)
        # 双面壳仍然强制深度（见 use_depth），所以这里可以直接用软 alpha，边缘不会出斑块
        take = mm & (aa > 0.02)
        strand = rgb * shade[..., None] * np.asarray(d['tint'], np.float32)[None, None, :]
        c[take] = c[take]*(1-aa[take, None]) + strand[take]*aa[take, None]
        aa_[take] = np.minimum(1.0, aa_[take] + aa[take]*0.9)
    c2 = np.clip(col, 0, 1) * d['bright']
    c2 = (c2 - 0.5) * d['contrast'] + 0.5
    c3 = np.clip(c2, 0, 1) ** (1.0 / d['gamma'])
    # 按贴图平均亮度自适应：贴图本身偏暗时，sRGB 空间的光照 + 1/gamma 会把它整体抬成灰白，
    # 这里按「贴图不透明像素的平均亮度」反推一个增益，把结果拉回贴图该有的明暗（NifSkope 观感）。
    if d.get('autobright', 1) and tex is not None and getattr(tex, 'ndim', 0) == 3:
        ta = tex[..., 3] > 0.5
        vis = al > 0.12
        if ta.any() and vis.any():
            LU = np.array([0.2126, 0.7152, 0.0722], np.float32)
            tgt = float((tex[..., :3][ta] * LU).sum(axis=1).mean()) * 0.85
            cur = float((c3[vis] * LU).sum(axis=1).mean())
            if cur > 1e-3:
                g = float(min(1.12, max(0.55, (tgt / cur) ** 0.85)))
                if abs(g - 1.0) > 0.01:
                    c3 = np.clip(c3 * g, 0.0, 1.0)
    img = (c3 * 255).astype(np.uint8)
    out = np.dstack([img, (al*255).astype(np.uint8)])
    im = Image.fromarray(out, 'RGBA').resize((size//2, size//2), Image.LANCZOS)
    return np.asarray(im)


def render_soft(pos, uvs, tris, tex, size=900, ss=1):
    """画家算法 + 贴图 alpha 混合（不写深度）：模拟 NifSkope 的半透明叠加，保留发丝细节。
    投影约定与 render_blend 一致：X=x, Y=-z, 深度=y。"""
    P = np.asarray(pos, float).copy()
    U = np.asarray(uvs, float).copy()
    T = np.asarray(tris, np.int32).reshape(-1, 3)
    W = int(size * ss)
    x, y, z = P[:, 0], P[:, 1], P[:, 2]
    cx, cz = (x.min() + x.max()) / 2, (z.min() + z.max()) / 2
    span = max(x.max() - x.min(), z.max() - z.min(), 1e-6)
    sc = 0.94 * W / span
    X = (x - cx) * sc + W / 2.0
    Y = (cz - z) * sc + W / 2.0
    img = np.zeros((W, W, 3), np.float32)
    alpha = np.zeros((W, W), np.float32)
    n = np.cross(P[T[:, 1]] - P[T[:, 0]], P[T[:, 2]] - P[T[:, 0]])
    ln = np.linalg.norm(n, axis=1); ln[ln == 0] = 1.0; n = n / ln[:, None]
    lam = np.abs(n @ np.array([0.25, -0.92, 0.30]))
    shade = (0.35 + 0.75 * lam).astype(np.float32)
    order = np.argsort(y[T].mean(axis=1))          # y 大=更靠前，先画远的（y 小）
    if tex is None:
        tex = np.ones((4, 4, 4), np.float32)
    TH, TW = tex.shape[:2]
    for ti in order:
        i0, i1, i2 = T[ti]
        x0, x1, x2 = X[i0], X[i1], X[i2]
        y0, y1, y2 = Y[i0], Y[i1], Y[i2]
        minx = int(max(0, np.floor(min(x0, x1, x2)))); maxx = int(min(W - 1, np.ceil(max(x0, x1, x2))))
        miny = int(max(0, np.floor(min(y0, y1, y2)))); maxy = int(min(W - 1, np.ceil(max(y0, y1, y2))))
        if minx > maxx or miny > maxy:
            continue
        ys = np.arange(miny, maxy + 1, dtype=np.float32)[:, None] + 0.5
        xs = np.arange(minx, maxx + 1, dtype=np.float32)[None, :] + 0.5
        d = (x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0)
        if abs(d) < 1e-9:
            continue
        w0 = ((x1 - xs) * (y2 - ys) - (x2 - xs) * (y1 - ys)) / d
        w1 = ((x2 - xs) * (y0 - ys) - (x0 - xs) * (y2 - ys)) / d
        w2 = 1.0 - w0 - w1
        m = (w0 >= -1e-4) & (w1 >= -1e-4) & (w2 >= -1e-4)
        if not m.any():
            continue
        uu = w0 * U[i0, 0] + w1 * U[i1, 0] + w2 * U[i2, 0]
        vv = w0 * U[i0, 1] + w1 * U[i1, 1] + w2 * U[i2, 1]
        px = np.clip((uu * TW).astype(np.int32), 0, TW - 1)
        py = np.clip((vv * TH).astype(np.int32), 0, TH - 1)
        col = tex[py, px, :3].astype(np.float32)
        a = tex[py, px, 3].astype(np.float32) * m
        a = np.clip(a, 0.0, 1.0)
        sub = img[miny:maxy + 1, minx:maxx + 1]
        sa = alpha[miny:maxy + 1, minx:maxx + 1]
        a3 = a[..., None]
        sub *= (1.0 - a3)
        sub += (col * shade[ti]) * a3
        sa[:] = np.minimum(1.0, sa + a * (1.0 - sa))
    out = np.dstack([(np.clip(img, 0, 1) ** (1 / 1.8) * 255).astype(np.uint8),
                     np.clip(alpha * 255, 0, 255).astype(np.uint8)])
    im = Image.fromarray(out, 'RGBA')
    if ss > 1:
        im = im.resize((int(size), int(size)), Image.LANCZOS)
    return np.asarray(im)
