# -*- coding: utf-8 -*-
"""全屏半透明遮罩、拖动框选、自动方形裁切。"""
import time
import tkinter as tk

from PIL import Image, ImageEnhance, ImageGrab, ImageTk


def _virtual_metrics(root):
    try:
        import ctypes
        u = ctypes.windll.user32
        vx, vy, vw, vh = [u.GetSystemMetrics(i) for i in (76, 77, 78, 79)]
        if vw > 0 and vh > 0:
            return vx, vy, vw, vh
    except Exception:
        pass
    return 0, 0, root.winfo_screenwidth(), root.winfo_screenheight()


def shoot_screen(root, on_done, countdown=2.6):
    """全屏框选截图：倒数 → 抓屏 → 半透明遮罩里拖矩形（自动正方形）→ on_done(PIL.Image)。"""
    import time as _t
    import tkinter as tk
    from tkinter import messagebox, filedialog
    from PIL import Image, ImageEnhance, ImageGrab, ImageTk

    toast = tk.Toplevel(root)
    toast.overrideredirect(True)
    toast.attributes('-topmost', True)
    lab = tk.Label(toast, bg='#111', fg='#eee', font=('Microsoft YaHei', 12),
                   padx=20, pady=12, justify='center')
    lab.pack()
    state = dict(cancelled=False)

    def cancel_count(event=None):
        state['cancelled'] = True

    toast.bind('<Escape>', cancel_count)
    toast.bind('<Button-1>', cancel_count)
    t0 = _t.time()
    while True:
        left = countdown - (_t.time() - t0)
        if state['cancelled'] or left <= 0:
            break
        lab.configure(text='%.1f 秒后截屏 · 现在切到要截取的画面\n（Esc 或点这里取消）' % left)
        toast.update_idletasks()
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        toast.geometry('+%d+%d' % (max(0, (sw - toast.winfo_width()) // 2), 90))
        toast.update()
        _t.sleep(0.05)
    try:
        toast.destroy()
    except Exception:
        pass
    root.update()
    if state['cancelled']:
        return
    _t.sleep(0.12)
    try:
        try:
            shot = ImageGrab.grab(all_screens=True)
        except TypeError:
            shot = ImageGrab.grab()
    except Exception as e:
        messagebox.showerror('截图失败', str(e))
        return

    vx, vy, vw, vh = _virtual_metrics(root)
    disp = shot if shot.size == (vw, vh) else shot.resize((vw, vh), Image.LANCZOS)
    dim = ImageEnhance.Brightness(disp).enhance(0.42)
    top = tk.Toplevel(root)
    top.overrideredirect(True)
    top.attributes('-topmost', True)
    top.geometry('%dx%d+%d+%d' % (vw, vh, vx, vy))
    cv = tk.Canvas(top, highlightthickness=0, bd=0, cursor='crosshair', bg='#000')
    cv.pack(fill='both', expand=True)
    bg_pi = ImageTk.PhotoImage(dim)
    cv.create_image(0, 0, anchor='nw', image=bg_pi)
    cv.bg_pi = bg_pi      # 保住 Python 引用，否则 shoot_screen 返回后图像会被回收 → 遮罩变全黑
    cv.create_text(vw // 2, 28, fill='#ffd75e', font=('Microsoft YaHei', 12, 'bold'), tags='ui',
                   text='拖动框选要用的画面（自动正方形）· 松开即填入槽位 · Esc / 右键 取消')
    st = dict(drag=False, x0=0, y0=0, side=0, rect=None, spot=None, spot_pi=None,
              size_t=None, last=0.0)

    def square(x0, y0, x1, y1):
        side = min(max(abs(x1 - x0), abs(y1 - y0), 16), min(vw, vh))
        cx = max(side / 2.0, min(vw - side / 2.0, (x0 + x1) / 2.0))
        cy = max(side / 2.0, min(vh - side / 2.0, (y0 + y1) / 2.0))
        return cx, cy, side

    def draw_spot(cx, cy, side, force=False):
        if not force and _t.time() - st['last'] < 0.03:
            return
        st['last'] = _t.time()
        x0, y0 = int(cx - side / 2), int(cy - side / 2)
        x1, y1 = x0 + int(side), y0 + int(side)
        pi = ImageTk.PhotoImage(disp.crop((x0, y0, x1, y1)))
        st['spot_pi'] = pi
        cv.spot_pi = pi
        if st['spot'] is None:
            st['spot'] = cv.create_image(x0, y0, anchor='nw', image=pi)
        else:
            cv.itemconfigure(st['spot'], image=pi)
            cv.coords(st['spot'], x0, y0)
        if st['rect'] is None:
            st['rect'] = cv.create_rectangle(x0, y0, x1, y1, outline='#ffd75e', width=2)
        else:
            cv.coords(st['rect'], x0, y0, x1, y1)
        txt = '%d × %d' % (x1 - x0, y1 - y0)
        if st['size_t'] is None:
            st['size_t'] = cv.create_text(x0, max(10, y0 - 10), text=txt, anchor='sw',
                                           fill='#ffd75e', font=('Microsoft YaHei', 10, 'bold'), tags='ui')
        else:
            cv.itemconfigure(st['size_t'], text=txt)
            cv.coords(st['size_t'], x0, max(10, y0 - 10))
        cv.tag_raise('ui')

    def close(event=None):
        try:
            top.grab_release()
        except Exception:
            pass
        try:
            top.destroy()
        except Exception:
            pass

    def finish(im):
        close()
        try:
            on_done(im)
        except Exception:
            traceback.print_exc()

    def on_press(e):
        st.update(drag=True, x0=e.x, y0=e.y, last=0.0)
        for k in ('spot', 'rect', 'size_t'):
            if st.get(k):
                cv.delete(st[k])
                st[k] = None
        st['spot_pi'] = None
        cx, cy, side = square(e.x, e.y, e.x + 16, e.y + 16)
        draw_spot(cx, cy, side, force=True)

    def on_move(e):
        if not st['drag']:
            return
        cx, cy, side = square(st['x0'], st['y0'], e.x, e.y)
        draw_spot(cx, cy, side)

    def on_release(e):
        if not st['drag']:
            return
        st['drag'] = False
        cx, cy, side = square(st['x0'], st['y0'], e.x, e.y)
        # 显示坐标 -> 截屏像素：逐轴比例可能不同（多显示器 DPI 缩放），
        # 所以取两边中较大的边长，保证源图里也是正圆/正方形，而不是被拉成椭圆/矩形。
        sx = shot.width / float(vw)
        sy = shot.height / float(vh)
        side = min(int(round(side * max(sx, sy))), shot.width, shot.height)
        if side < 16:
            return
        ccx = min(max(cx * sx, side / 2.0), shot.width - side / 2.0)
        ccy = min(max(cy * sy, side / 2.0), shot.height - side / 2.0)
        x0 = int(ccx - side / 2.0)
        y0 = int(ccy - side / 2.0)
        finish(shot.crop((x0, y0, x0 + side, y0 + side)).convert('RGB'))

    cv.bind('<Button-1>', on_press)
    cv.bind('<B1-Motion>', on_move)
    cv.bind('<ButtonRelease-1>', on_release)
    cv.bind('<Button-3>', close)
    top.bind('<Escape>', close)
    top.focus_force()
    try:
        top.grab_set()
    except Exception:
        pass


