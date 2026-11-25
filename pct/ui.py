# -*- coding: utf-8 -*-
"""模糊匹配、下拉框（固定选中浅色 + 鼠标悬停深色）、悬浮提示、日志裁剪。"""
import tkinter as tk
from tkinter import ttk

SEL_BG = '#dbe9fb'        # 当前选中项（固定浅色）
SEL_FG = '#10233d'
HOVER_BG = '#8fb0d6'      # 鼠标悬停（深色）
HOVER_FG = '#ffffff'
LIST_BG = '#ffffff'
LIST_FG = '#1f1f1f'


# ==================== 通用小工具 ====================
def _fuzzy_match(needle, hay):
    """模糊匹配：忽略大小写与空格，先按子串，再按「顺序出现的字符」（子序列）。"""
    n = str(needle or '').strip().lower().replace(' ', '')
    if not n:
        return True
    h = str(hay or '')
    hl = h.lower().replace(' ', '')
    if n in hl:
        return True
    i = 0
    for ch in hl:
        if i < len(n) and ch == n[i]:
            i += 1
            if i == len(n):
                return True
    return False


def _fuzzy_rank(needle, hay):
    """越小越靠前：0=开头命中 1=子串命中 2=子序列命中 9=不命中。"""
    n = str(needle or '').strip().lower().replace(' ', '')
    if not n:
        return 0
    hl = str(hay or '').lower().replace(' ', '')
    p = hl.find(n)
    if p == 0:
        return 0
    if p > 0:
        return 1
    return 2 if _fuzzy_match(n, hl) else 9


class FuzzyCombo(tk.Frame):
    """可输入、可点开的下拉框（自绘弹层）。

    - 选中项固定浅蓝底；鼠标移到别的条目上是深蓝底。
    - 支持边打字边模糊过滤；上下键移动、回车确认、Esc 关闭。
    - 对外保留旧 ttk.Combobox 的常用接口：get/set/current/refresh_values/
      bind('<<ComboboxSelected>>')/['values']。
    """

    def __init__(self, master, values_getter=None, on_pick=None, textvariable=None,
                 width=60, **kw):
        tk.Frame.__init__(self, master, **kw)
        self._get_all = values_getter or (lambda: [])
        self._on_pick = on_pick
        self._pick_cbs = []
        self._values = []
        self._cursor = -1
        self._pop = None
        self._tree = None
        self._closing = False
        self._out_bind = None
        self.var = textvariable or tk.StringVar()
        self.entry = tk.Entry(self, textvariable=self.var, width=width,
                              relief='flat', bd=0, highlightthickness=0)
        self.entry.pack(side='left', fill='x', expand=True, padx=(3, 0), pady=1)
        self.arrow = tk.Label(self, text='▾', width=2, cursor='hand2')
        self.arrow.pack(side='right')
        self.entry.bind('<Button-1>', self._open, add='+')
        self.arrow.bind('<Button-1>', self._open)
        self.entry.bind('<KeyRelease>', self._typed)
        self.entry.bind('<Down>', lambda e: self._move(1))
        self.entry.bind('<Up>', lambda e: self._move(-1))
        self.entry.bind('<Return>', self._enter)
        self.entry.bind('<KP_Enter>', self._enter)
        self.entry.bind('<Escape>', lambda e: self._close())
        self.entry.bind('<FocusOut>', lambda e: self.after(120, self._maybe_close))
        self.entry.bind('<Tab>', lambda e: (self._close(), None)[1])

    # ---------- 兼容接口 ----------
    def get(self):
        return self.var.get()

    def set(self, v):
        self.var.set(v)

    def current(self, idx=None):
        if idx is None:
            try:
                return self._values.index(self.get())
            except ValueError:
                return -1
        if 0 <= idx < len(self._values):
            self.var.set(self._values[idx])
            self._refresh_marks()

    def __setitem__(self, key, val):
        if key == 'values':
            self._values = list(val)
            self._refresh_marks()
            return
        self.configure({key: val})

    def configure(self, cnf=None, **kw):
        vals = kw.pop('values', None)
        if vals is not None:
            self._values = list(vals)
        if kw or cnf:
            tk.Frame.configure(self, cnf or {}, **kw)

    def bind(self, seq=None, func=None, add=None):
        if seq == '<<ComboboxSelected>>':
            self._pick_cbs.append(func)
            return None
        return tk.Frame.bind(self, seq, func, add)

    # ---------- 数据 ----------
    def refresh_values(self, filt=None):
        allv = list(self._get_all())
        txt = (filt if filt is not None else self.get()) or ''
        if txt.strip():
            hits = [v for v in allv if _fuzzy_match(txt, v)]
            hits.sort(key=lambda v: (_fuzzy_rank(txt, v), len(v), v.lower()))
        else:
            hits = allv
        self._values = hits or allv
        if self._tree is not None:
            self._fill()
        return hits

    def _refresh_marks(self):
        if self._tree is not None:
            self._fill()

    # ---------- 弹层 ----------
    def _ensure_pop(self):
        if self._pop is not None:
            return
        self._pop = tk.Toplevel(self)
        self._pop.withdraw()
        self._pop.overrideredirect(True)
        try:
            self._pop.attributes('-topmost', True)
        except tk.TclError:
            pass
        wrap = tk.Frame(self._pop, bg='#7a7a7a', bd=0)
        wrap.pack(fill='both', expand=True)
        tv = ttk.Treeview(wrap, columns=('v',), show='', height=12, selectmode='browse')
        tv.column('v', width=380, anchor='w')
        tv.tag_configure('sel', background=SEL_BG, foreground=SEL_FG)
        tv.tag_configure('hover', background=HOVER_BG, foreground=HOVER_FG)
        vs = ttk.Scrollbar(wrap, orient='vertical', command=tv.yview)
        tv.configure(yscrollcommand=vs.set)
        vs.pack(side='right', fill='y')
        tv.pack(side='left', fill='both', expand=True)
        tv.bind('<Motion>', self._hover)
        tv.bind('<ButtonRelease-1>', self._click)
        tv.bind('<Leave>', lambda e: self._clear_hover())
        self._tree = tv

    def _fill(self):
        tv = self._tree
        for it in tv.get_children():
            tv.delete(it)
        cur = self.get()
        for i, v in enumerate(self._values):
            tags = ('sel',) if v == cur else ()
            tv.insert('', 'end', iid=str(i), values=(v,), tags=tags)
        self._cursor = self._values.index(cur) if cur in self._values else -1
        if self._cursor >= 0:
            tv.see(str(self._cursor))

    def _open(self, *_a):
        self._ensure_pop()
        if not self._values:
            self.refresh_values(filt='')
        else:
            self._fill()
        self.update_idletasks()
        h = min(len(self._values), 12) * 21 + 4
        x = self.winfo_rootx()
        y = self.winfo_rooty() + self.winfo_height()
        self._pop.geometry('%dx%d+%d+%d' % (max(self.winfo_width(), 380), max(h, 24), x, y))
        self._pop.deiconify()
        self._pop.lift()
        self.entry.focus_set()
        self._bind_outside_soon()
        return 'break'

    def _bind_outside_soon(self):
        # 延迟一点再挂，避免「点开自己的那一下」立刻被当成点外面
        try:
            self.after(60, self._bind_outside)
        except tk.TclError:
            pass

    def _bind_outside(self):
        if self._pop is None or not self._pop.winfo_ismapped():
            return
        top = self.winfo_toplevel()
        if self._out_bind is None:
            try:
                self._out_bind = top.bind('<Button-1>', self._click_outside, add='+')
            except tk.TclError:
                self._out_bind = None

    def _click_outside(self, event):
        """点在弹层外面（主窗口任何位置）就收起；点自己或弹层里不受影响。"""
        w = getattr(event, 'widget', None)
        try:
            while w is not None:
                if w is self or w is self._pop:
                    return
                if self._pop is not None and str(w).startswith(str(self._pop)):
                    return
                w = getattr(w, 'master', None)
        except Exception:
            return
        self._close()

    def _unbind_outside(self):
        if self._out_bind is None:
            return
        try:
            self.winfo_toplevel().unbind('<Button-1>', self._out_bind)
        except tk.TclError:
            pass
        self._out_bind = None

    def _close(self):
        if self._pop is not None:
            self._pop.withdraw()
        self._cursor = -1
        self._unbind_outside()

    def _maybe_close(self):
        if self._pop is not None and self._pop.winfo_ismapped():
            try:
                if self._pop.focus_get() is not None:
                    return
            except tk.TclError:
                pass
            self._close()

    # ---------- 交互 ----------
    def _typed(self, e):
        if e.keysym in ('Up', 'Down', 'Left', 'Right', 'Return', 'KP_Enter', 'Escape', 'Tab',
                        'Home', 'End', 'Prior', 'Next', 'Shift_L', 'Shift_R',
                        'Control_L', 'Control_R', 'Alt_L', 'Alt_R'):
            return
        self.refresh_values(filt=self.get())
        if self._pop is None or not self._pop.winfo_ismapped():
            self._open()
        else:
            self._fill()

    def _move(self, d):
        if not self._values:
            return 'break'
        if self._pop is None or not self._pop.winfo_ismapped():
            self._open()
        n = len(self._values)
        self._cursor = (self._cursor + d) % n
        for it in self._tree.get_children():
            self._tree.item(it, tags=('sel',) if it == str(self._cursor) else ())
        self._tree.see(str(self._cursor))
        return 'break'

    def _hover(self, e):
        if self._tree is None:
            return
        it = self._tree.identify_row(e.y)
        for i in self._tree.get_children():
            if i == it:
                if 'sel' not in self._tree.item(i, 'tags'):
                    self._tree.item(i, tags=('hover',))
            else:
                if 'sel' in self._tree.item(i, 'tags'):
                    self._tree.item(i, tags=('sel',))
                else:
                    self._tree.item(i, tags=())

    def _clear_hover(self):
        if self._tree is None:
            return
        for i in self._tree.get_children():
            self._tree.item(i, tags=('sel',) if 'sel' in self._tree.item(i, 'tags') else ())

    def _click(self, e):
        if self._tree is None:
            return
        it = self._tree.identify_row(e.y)
        if not it:
            return
        idx = int(it)
        if 0 <= idx < len(self._values):
            self.var.set(self._values[idx])
            self._close()
            self._fire()

    def _enter(self, *_a):
        if self._pop is not None and self._pop.winfo_ismapped() and 0 <= self._cursor < len(self._values):
            self.var.set(self._values[self._cursor])
            self._close()
            self._fire()
            return 'break'
        # 没弹层：按输入内容精确/唯一模糊命中
        txt = (self.get() or '').strip()
        allv = list(self._get_all())
        if txt in allv:
            self.var.set(txt)
            self._fire()
            return 'break'
        hits = [v for v in allv if _fuzzy_match(txt, v)]
        if len(hits) == 1:
            self.var.set(hits[0])
            self._fire()
        return 'break'

    def _fire(self):
        self.refresh_values(filt='')
        for cb in self._pick_cbs:
            try:
                cb(None)
            except Exception:
                pass
        if self._on_pick:
            try:
                self._on_pick()
            except Exception:
                pass


class ToolTip(object):
    """鼠标停在控件上时弹出的小提示（hover 悬浮窗）。"""

    def __init__(self, widget, text, delay=420, wraplength=380):
        self.w = widget
        self.text = text
        self.delay = delay
        self.wraplength = wraplength
        self.tip = None
        self._after = None
        widget.bind('<Enter>', self._schedule, add='+')
        widget.bind('<Leave>', self._hide, add='+')
        widget.bind('<ButtonPress>', self._hide, add='+')

    def _schedule(self, *_a):
        self._cancel()
        self._after = self.w.after(self.delay, self._show)

    def _cancel(self):
        if self._after is not None:
            try:
                self.w.after_cancel(self._after)
            except Exception:
                pass
            self._after = None

    def _show(self):
        if self.tip is not None or not self.text:
            return
        try:
            x = self.w.winfo_rootx() + 12
            y = self.w.winfo_rooty() + self.w.winfo_height() + 6
        except Exception:
            return
        tip = tk.Toplevel(self.w)
        tip.wm_overrideredirect(True)
        try:
            tip.attributes('-topmost', True)
        except tk.TclError:
            pass
        tk.Label(tip, text=self.text, justify='left', background='#ffffe1',
                 relief='solid', borderwidth=1, wraplength=self.wraplength,
                 font=('Microsoft YaHei UI', 9)).pack(ipadx=4, ipady=3)
        tip.wm_geometry('+%d+%d' % (x, y))
        self.tip = tip

    def _hide(self, *_a):
        self._cancel()
        if self.tip is not None:
            try:
                self.tip.destroy()
            except Exception:
                pass
            self.tip = None


def log_trim(w, keep=400):
    """日志框只留最近 keep 行，避免越跑越卡。"""
    try:
        n = int(w.index('end-1c').split('.')[0])
        if n > keep:
            w.delete('1.0', '%d.0' % (n - keep + 1))
    except Exception:
        pass
