#!/usr/bin/env python3
"""
Kaart Ontwerper - Maak voor- en achterkant kaarten, exporteer als dubbelzijdig PDF
Vereisten: pip install reportlab Pillow
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, colorchooser, simpledialog
from PIL import Image, ImageTk
import os
import json
import copy

# ReportLab imports
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.lib.utils import ImageReader

# â”€â”€ Kaartformaat (A6 liggend) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
CARD_W_MM = 148.5
CARD_H_MM = 105.0
CANVAS_W   = 594   # pixels in editor (4x schaal)
CANVAS_H   = 420

def mm_to_px(val):  return val / CARD_W_MM * CANVAS_W
def px_to_mm_x(val): return val / CANVAS_W * CARD_W_MM
def px_to_mm_y(val): return val / CANVAS_H * CARD_H_MM


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
class Element:
    """Basis klasse voor een element op de kaart."""
    def __init__(self, x=50, y=50):
        self.x = x      # pixels (canvas-coÃ¶rdinaten)
        self.y = y
        self.selected = False

    def move(self, dx, dy):
        self.x += dx
        self.y += dy

    def to_dict(self): raise NotImplementedError
    @classmethod
    def from_dict(cls, d): raise NotImplementedError


class TextElement(Element):
    def __init__(self, x=50, y=50, text="Tekst", font="Helvetica",
                 size=24, bold=False, italic=False, color="#000000", align="left"):
        super().__init__(x, y)
        self.text   = text
        self.font   = font
        self.size   = size
        self.bold   = bold
        self.italic = italic
        self.color  = color
        self.align  = align

    def to_dict(self):
        return {"type": "text", "x": self.x, "y": self.y, "text": self.text,
                "font": self.font, "size": self.size, "bold": self.bold,
                "italic": self.italic, "color": self.color, "align": self.align}

    @classmethod
    def from_dict(cls, d):
        return cls(d["x"], d["y"], d["text"], d["font"], d["size"],
                   d["bold"], d["italic"], d["color"], d.get("align","left"))


class ImageElement(Element):
    def __init__(self, x=50, y=50, path="", width=100, height=100):
        super().__init__(x, y)
        self.path   = path
        self.width  = width
        self.height = height
        self._photo = None   # cached PhotoImage

    def load_photo(self):
        if not self.path or not os.path.exists(self.path):
            return None
        try:
            img = Image.open(self.path).resize(
                (max(1,int(self.width)), max(1,int(self.height))), Image.LANCZOS)
            self._photo = ImageTk.PhotoImage(img)
        except Exception:
            self._photo = None
        return self._photo

    def to_dict(self):
        return {"type": "image", "x": self.x, "y": self.y,
                "path": self.path, "width": self.width, "height": self.height}

    @classmethod
    def from_dict(cls, d):
        return cls(d["x"], d["y"], d["path"], d["width"], d["height"])


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
class CardCanvas(tk.Canvas):
    """Interactief canvas voor Ã©Ã©n kaart-zijde."""

    HANDLE_SIZE = 7

    def __init__(self, master, bg_color="#ffffff", **kw):
        super().__init__(master, width=CANVAS_W, height=CANVAS_H,
                         bg=bg_color, cursor="arrow",
                         highlightthickness=2, highlightbackground="#666", **kw)
        self.bg_color  = bg_color
        self.elements  = []        # list[Element]
        self.selected  = None      # Element | None
        self._drag     = None      # (start_x, start_y, elem_x0, elem_y0)
        self._resize   = False
        self._resize_orig = None

        self.bind("<ButtonPress-1>",   self._on_press)
        self.bind("<B1-Motion>",       self._on_drag)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Double-Button-1>", self._on_dblclick)
        self.bind("<Delete>",          self._on_delete)
        self.bind("<BackSpace>",       self._on_delete)
        self.focus_set()

        self.on_selection_changed = None   # callback(elem | None)

    # â”€â”€ Rendering â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    def redraw(self):
        self.delete("all")
        self.configure(bg=self.bg_color)
        for el in self.elements:
            self._draw_element(el)
        if self.selected:
            self._draw_handles(self.selected)

    def _draw_element(self, el):
        if isinstance(el, TextElement):
            font_spec = (el.font, int(el.size))
            style = []
            if el.bold:   style.append("bold")
            if el.italic: style.append("italic")
            if style:     font_spec = (el.font, int(el.size), " ".join(style))
            anchor = {"left": "nw", "center": "n", "right": "ne"}.get(el.align, "nw")
            self.create_text(el.x, el.y, text=el.text, font=font_spec,
                             fill=el.color, anchor=anchor, tags=f"el_{id(el)}")
        elif isinstance(el, ImageElement):
            photo = el.load_photo()
            if photo:
                self.create_image(el.x, el.y, image=photo, anchor="nw",
                                  tags=f"el_{id(el)}")
                el._photo = photo  # keep reference!
            else:
                # Placeholder
                self.create_rectangle(el.x, el.y, el.x+el.width, el.y+el.height,
                                      outline="#aaa", dash=(4,4))
                self.create_text(el.x + el.width//2, el.y + el.height//2,
                                 text="[afbeelding]", fill="#aaa")

    def _draw_handles(self, el):
        bbox = self._bbox(el)
        if not bbox: return
        x1,y1,x2,y2 = bbox
        self.create_rectangle(x1, y1, x2, y2, outline="#3a9bd5",
                              dash=(4,3), width=1, tags="handle")
        s = self.HANDLE_SIZE
        # bottom-right resize handle
        self.create_rectangle(x2-s, y2-s, x2+s, y2+s,
                              fill="#3a9bd5", outline="white", tags="handle_br")

    def _bbox(self, el):
        if isinstance(el, TextElement):
            items = self.find_withtag(f"el_{id(el)}")
            if items:
                return self.bbox(items[0])
        elif isinstance(el, ImageElement):
            return (el.x, el.y, el.x + el.width, el.y + el.height)
        return None

    # â”€â”€ Mouse events â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    def _on_press(self, event):
        self.focus_set()
        x, y = event.x, event.y

        # Check resize handle first
        items = self.find_overlapping(x-5, y-5, x+5, y+5)
        if any(self.gettags(i) == ("handle_br",) for i in items):
            self._resize = True
            self._resize_orig = (x, y,
                                 getattr(self.selected, "width",  0),
                                 getattr(self.selected, "height", 0))
            return

        # Pick element (reverse order = top first)
        hit = None
        for el in reversed(self.elements):
            bb = self._bbox(el)
            if bb:
                bx1,by1,bx2,by2 = bb
                if bx1 <= x <= bx2 and by1 <= y <= by2:
                    hit = el; break
        
        # Also try canvas item tags for text
        if not hit:
            overlapping = self.find_overlapping(x-2, y-2, x+2, y+2)
            for item in overlapping:
                tags = self.gettags(item)
                for t in tags:
                    if t.startswith("el_"):
                        eid = int(t[3:])
                        for el in self.elements:
                            if id(el) == eid:
                                hit = el; break

        self.selected = hit
        if hit:
            self._drag = (x, y, hit.x, hit.y)
        else:
            self._drag = None
        self.redraw()
        if self.on_selection_changed:
            self.on_selection_changed(self.selected)

    def _on_drag(self, event):
        if self._resize and self.selected:
            ox, oy, ow, oh = self._resize_orig
            dx = event.x - ox
            dy = event.y - oy
            if isinstance(self.selected, ImageElement):
                self.selected.width  = max(10, ow + dx)
                self.selected.height = max(10, oh + dy)
            elif isinstance(self.selected, TextElement):
                self.selected.size = max(6, int(oh + dy * 0.3))
            self.redraw()
        elif self._drag and self.selected:
            ox, oy, ex0, ey0 = self._drag
            self.selected.x = ex0 + (event.x - ox)
            self.selected.y = ey0 + (event.y - oy)
            self.redraw()

    def _on_release(self, event):
        self._drag = None
        self._resize = False
        self._resize_orig = None

    def _on_dblclick(self, event):
        if self.selected and isinstance(self.selected, TextElement):
            self._edit_text(self.selected)

    def _on_delete(self, event):
        if self.selected and self.selected in self.elements:
            self.elements.remove(self.selected)
            self.selected = None
            self.redraw()
            if self.on_selection_changed:
                self.on_selection_changed(None)

    def _edit_text(self, el):
        dlg = TextEditDialog(self, el)
        self.wait_window(dlg)
        self.redraw()
        if self.on_selection_changed:
            self.on_selection_changed(self.selected)

    # â”€â”€ Public API â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    def add_text(self):
        el = TextElement(x=60, y=60, text="Nieuwe tekst")
        self.elements.append(el)
        self.selected = el
        self.redraw()
        self._edit_text(el)
        if self.on_selection_changed:
            self.on_selection_changed(self.selected)

    def add_image(self):
        path = filedialog.askopenfilename(
            title="Kies afbeelding",
            filetypes=[("Afbeeldingen", "*.png *.jpg *.jpeg *.gif *.bmp *.webp"),
                       ("Alle bestanden", "*.*")])
        if not path: return
        el = ImageElement(x=30, y=30, path=path, width=150, height=120)
        self.elements.append(el)
        self.selected = el
        self.redraw()
        if self.on_selection_changed:
            self.on_selection_changed(self.selected)

    def set_bg(self, color):
        self.bg_color = color
        self.redraw()

    def to_dict(self):
        return {"bg": self.bg_color,
                "elements": [e.to_dict() for e in self.elements]}

    def load_dict(self, d):
        self.bg_color = d.get("bg", "#ffffff")
        self.elements = []
        for ed in d.get("elements", []):
            if ed["type"] == "text":
                self.elements.append(TextElement.from_dict(ed))
            elif ed["type"] == "image":
                self.elements.append(ImageElement.from_dict(ed))
        self.selected = None
        self.redraw()


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
class TextEditDialog(tk.Toplevel):
    """Dialog voor het bewerken van tekstelementen."""

    FONTS = ["Helvetica", "Times-Roman", "Courier", "Arial"]

    def __init__(self, parent, el: TextElement):
        super().__init__(parent)
        self.el = el
        self.title("Tekst bewerken")
        self.resizable(False, False)
        self.grab_set()
        self.configure(bg="#1e1e1e")
        self._build()
        self.transient(parent)

    def _build(self):
        pad = {"padx": 8, "pady": 5}
        lbl_kw = {"bg": "#1e1e1e", "fg": "#ddd", "font": ("Segoe UI", 9)}
        frame = tk.Frame(self, bg="#1e1e1e", padx=14, pady=12)
        frame.pack()

        # Text area
        tk.Label(frame, text="Tekst:", **lbl_kw).grid(row=0, column=0, sticky="nw", **pad)
        self.txt = tk.Text(frame, width=36, height=5, bg="#2d2d2d", fg="white",
                           insertbackground="white", font=("Segoe UI", 10),
                           relief="flat", borderwidth=4)
        self.txt.grid(row=0, column=1, **pad)
        self.txt.insert("1.0", self.el.text)

        # Font
        tk.Label(frame, text="Lettertype:", **lbl_kw).grid(row=1, column=0, sticky="w", **pad)
        self.font_var = tk.StringVar(value=self.el.font)
        ttk.Combobox(frame, textvariable=self.font_var,
                     values=self.FONTS, state="readonly", width=18
                     ).grid(row=1, column=1, sticky="w", **pad)

        # Size
        tk.Label(frame, text="Grootte:", **lbl_kw).grid(row=2, column=0, sticky="w", **pad)
        self.size_var = tk.IntVar(value=self.el.size)
        tk.Spinbox(frame, from_=6, to=200, textvariable=self.size_var,
                   width=6, bg="#2d2d2d", fg="white", insertbackground="white"
                   ).grid(row=2, column=1, sticky="w", **pad)

        # Bold / Italic
        self.bold_var   = tk.BooleanVar(value=self.el.bold)
        self.italic_var = tk.BooleanVar(value=self.el.italic)
        bf = tk.Frame(frame, bg="#1e1e1e")
        bf.grid(row=3, column=1, sticky="w", **pad)
        tk.Checkbutton(bf, text="Vet", variable=self.bold_var,
                       bg="#1e1e1e", fg="#ddd", selectcolor="#333",
                       activebackground="#1e1e1e").pack(side="left")
        tk.Checkbutton(bf, text="Cursief", variable=self.italic_var,
                       bg="#1e1e1e", fg="#ddd", selectcolor="#333",
                       activebackground="#1e1e1e").pack(side="left", padx=8)

        # Align
        tk.Label(frame, text="Uitlijning:", **lbl_kw).grid(row=4, column=0, sticky="w", **pad)
        self.align_var = tk.StringVar(value=self.el.align)
        af = tk.Frame(frame, bg="#1e1e1e")
        af.grid(row=4, column=1, sticky="w", **pad)
        for val, lbl in [("left","Links"),("center","Midden"),("right","Rechts")]:
            tk.Radiobutton(af, text=lbl, variable=self.align_var, value=val,
                           bg="#1e1e1e", fg="#ddd", selectcolor="#333",
                           activebackground="#1e1e1e").pack(side="left", padx=4)

        # Color
        tk.Label(frame, text="Kleur:", **lbl_kw).grid(row=5, column=0, sticky="w", **pad)
        self.color_var = tk.StringVar(value=self.el.color)
        cf = tk.Frame(frame, bg="#1e1e1e")
        cf.grid(row=5, column=1, sticky="w", **pad)
        self.color_preview = tk.Label(cf, bg=self.el.color, width=3, relief="solid")
        self.color_preview.pack(side="left")
        tk.Button(cf, text="Kies kleurâ€¦", command=self._pick_color,
                  bg="#333", fg="white", relief="flat", padx=8
                  ).pack(side="left", padx=6)

        # Buttons
        bf2 = tk.Frame(frame, bg="#1e1e1e")
        bf2.grid(row=6, column=0, columnspan=2, pady=(10,0))
        tk.Button(bf2, text="OK", command=self._ok,
                  bg="#3a9bd5", fg="white", relief="flat",
                  padx=18, pady=5, font=("Segoe UI", 9, "bold")
                  ).pack(side="left", padx=6)
        tk.Button(bf2, text="Annuleren", command=self.destroy,
                  bg="#555", fg="white", relief="flat", padx=12, pady=5
                  ).pack(side="left")

    def _pick_color(self):
        color = colorchooser.askcolor(self.color_var.get(), parent=self)[1]
        if color:
            self.color_var.set(color)
            self.color_preview.configure(bg=color)

    def _ok(self):
        self.el.text   = self.txt.get("1.0", "end").strip()
        self.el.font   = self.font_var.get()
        self.el.size   = self.size_var.get()
        self.el.bold   = self.bold_var.get()
        self.el.italic = self.italic_var.get()
        self.el.color  = self.color_var.get()
        self.el.align  = self.align_var.get()
        self.destroy()


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
class PropertiesPanel(tk.Frame):
    """Rechter paneel â€” toont eigenschappen van het geselecteerde element."""

    def __init__(self, master, **kw):
        super().__init__(master, bg="#1e1e1e", width=220, **kw)
        self.pack_propagate(False)
        self.current_canvas = None
        self.current_el = None
        self._build_empty()

    def _build_empty(self):
        for w in self.winfo_children(): w.destroy()
        tk.Label(self, text="Eigenschappen", bg="#1e1e1e", fg="#888",
                 font=("Segoe UI", 10, "bold")).pack(pady=16)
        tk.Label(self, text="Selecteer een element\nom eigenschappen te zien.",
                 bg="#1e1e1e", fg="#555",
                 font=("Segoe UI", 9), justify="center").pack()

    def show(self, el, canvas: CardCanvas):
        self.current_canvas = canvas
        self.current_el = el
        for w in self.winfo_children(): w.destroy()

        lbl_kw = {"bg": "#1e1e1e", "fg": "#bbb", "font": ("Segoe UI", 9)}
        pad = {"padx": 10, "pady": 4}

        tk.Label(self, text="Eigenschappen", bg="#1e1e1e", fg="#eee",
                 font=("Segoe UI", 10, "bold")).pack(pady=(14,6))

        sep = tk.Frame(self, bg="#333", height=1); sep.pack(fill="x", padx=10, pady=2)

        if el is None:
            tk.Label(self, text="Niets geselecteerd.",
                     bg="#1e1e1e", fg="#555", font=("Segoe UI",9)).pack(pady=10)
            return

        def row(label, widget_fn):
            f = tk.Frame(self, bg="#1e1e1e")
            f.pack(fill="x", **pad)
            tk.Label(f, text=label, width=9, anchor="w", **lbl_kw).pack(side="left")
            widget_fn(f)

        # X / Y position
        self.x_var = tk.IntVar(value=int(el.x))
        self.y_var = tk.IntVar(value=int(el.y))

        def pos_row(label, var):
            f = tk.Frame(self, bg="#1e1e1e")
            f.pack(fill="x", **pad)
            tk.Label(f, text=label, width=9, anchor="w", **lbl_kw).pack(side="left")
            sp = tk.Spinbox(f, from_=-500, to=2000, textvariable=var, width=7,
                            bg="#2d2d2d", fg="white", insertbackground="white",
                            command=self._apply_pos, relief="flat")
            sp.pack(side="left")
            sp.bind("<Return>", lambda e: self._apply_pos())

        pos_row("X (px):", self.x_var)
        pos_row("Y (px):", self.y_var)

        if isinstance(el, ImageElement):
            tk.Frame(self, bg="#333", height=1).pack(fill="x", padx=10, pady=4)
            self.w_var = tk.IntVar(value=int(el.width))
            self.h_var = tk.IntVar(value=int(el.height))

            def img_row(label, var):
                f = tk.Frame(self, bg="#1e1e1e")
                f.pack(fill="x", **pad)
                tk.Label(f, text=label, width=9, anchor="w", **lbl_kw).pack(side="left")
                sp = tk.Spinbox(f, from_=1, to=3000, textvariable=var, width=7,
                                bg="#2d2d2d", fg="white", insertbackground="white",
                                command=self._apply_size, relief="flat")
                sp.pack(side="left")
                sp.bind("<Return>", lambda e: self._apply_size())

            img_row("Breedte:", self.w_var)
            img_row("Hoogte:", self.h_var)

            tk.Button(self, text="Vervang afbeeldingâ€¦",
                      command=self._replace_image,
                      bg="#333", fg="white", relief="flat",
                      padx=8, pady=4).pack(pady=6)

        if isinstance(el, TextElement):
            tk.Frame(self, bg="#333", height=1).pack(fill="x", padx=10, pady=4)
            tk.Button(self, text="Tekst bewerkenâ€¦",
                      command=self._edit_text,
                      bg="#3a9bd5", fg="white", relief="flat",
                      padx=8, pady=5, font=("Segoe UI",9,"bold")).pack(pady=6)

        tk.Frame(self, bg="#333", height=1).pack(fill="x", padx=10, pady=6)
        tk.Button(self, text="ðŸ—‘ Verwijderen",
                  command=self._delete,
                  bg="#8b2020", fg="white", relief="flat",
                  padx=8, pady=4).pack()

    def _apply_pos(self):
        if self.current_el:
            self.current_el.x = self.x_var.get()
            self.current_el.y = self.y_var.get()
            if self.current_canvas:
                self.current_canvas.redraw()

    def _apply_size(self):
        el = self.current_el
        if isinstance(el, ImageElement):
            el.width  = self.w_var.get()
            el.height = self.h_var.get()
            if self.current_canvas:
                self.current_canvas.redraw()

    def _replace_image(self):
        el = self.current_el
        if not isinstance(el, ImageElement): return
        path = filedialog.askopenfilename(
            title="Kies afbeelding",
            filetypes=[("Afbeeldingen","*.png *.jpg *.jpeg *.gif *.bmp *.webp"),
                       ("Alle bestanden","*.*")])
        if path:
            el.path = path
            el._photo = None
            if self.current_canvas: self.current_canvas.redraw()

    def _edit_text(self):
        el = self.current_el
        if isinstance(el, TextElement) and self.current_canvas:
            dlg = TextEditDialog(self.current_canvas, el)
            self.winfo_toplevel().wait_window(dlg)
            self.current_canvas.redraw()
            self.show(el, self.current_canvas)

    def _delete(self):
        if self.current_el and self.current_canvas:
            if self.current_el in self.current_canvas.elements:
                self.current_canvas.elements.remove(self.current_el)
            self.current_canvas.selected = None
            self.current_canvas.redraw()
            self.show(None, self.current_canvas)


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Kaart Ontwerper  â€¢  A6 dubbelzijdig")
        self.configure(bg="#141414")
        self.resizable(True, True)
        self._build_ui()
        self._active_canvas = self.front_canvas
        self.minsize(900, 620)

    # â”€â”€ UI bouwen â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    def _build_ui(self):
        # â”€â”€ Toolbar â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        toolbar = tk.Frame(self, bg="#1a1a1a", pady=6)
        toolbar.pack(fill="x", side="top")

        def tb_btn(text, cmd, color="#333"):
            return tk.Button(toolbar, text=text, command=cmd,
                             bg=color, fg="white", relief="flat",
                             padx=12, pady=5, font=("Segoe UI", 9),
                             cursor="hand2")

        tk.Label(toolbar, text="  âœ¦ Kaart Ontwerper",
                 bg="#1a1a1a", fg="#e8c97a",
                 font=("Georgia", 13, "italic")).pack(side="left", padx=8)

        tb_btn("+ Tekst",       self._add_text,   "#2a5c8a").pack(side="left", padx=3)
        tb_btn("+ Afbeelding",  self._add_image,  "#2a6b4a").pack(side="left", padx=3)

        tk.Frame(toolbar, bg="#444", width=1, height=28).pack(side="left", padx=8)

        tb_btn("Achtergrond",   self._set_bg,     "#555"  ).pack(side="left", padx=3)

        tk.Frame(toolbar, bg="#444", width=1, height=28).pack(side="left", padx=8)

        tb_btn("ðŸ’¾ Opslaan",     self._save,       "#555"  ).pack(side="left", padx=3)
        tb_btn("ðŸ“‚ Openen",      self._open,       "#555"  ).pack(side="left", padx=3)

        tk.Frame(toolbar, bg="#444", width=1, height=28).pack(side="left", padx=8)

        tb_btn("ðŸ“„ Exporteer PDF", self._export_pdf, "#8b2020").pack(side="left", padx=3)

        # â”€â”€ Tab-switcher â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        tab_bar = tk.Frame(self, bg="#141414", pady=6)
        tab_bar.pack(fill="x")

        self.tab_front = tk.Button(tab_bar, text="â–£  Voorkant",
                                   command=lambda: self._switch("front"),
                                   bg="#3a9bd5", fg="white", relief="flat",
                                   padx=20, pady=6, font=("Segoe UI",10,"bold"),
                                   cursor="hand2")
        self.tab_front.pack(side="left", padx=(16,4))

        self.tab_back  = tk.Button(tab_bar, text="â–£  Achterkant",
                                   command=lambda: self._switch("back"),
                                   bg="#333", fg="#aaa", relief="flat",
                                   padx=20, pady=6, font=("Segoe UI",10),
                                   cursor="hand2")
        self.tab_back.pack(side="left", padx=4)

        tk.Label(tab_bar, text="A6  148,5 Ã— 105 mm",
                 bg="#141414", fg="#555", font=("Segoe UI",9)
                 ).pack(side="right", padx=16)

        # â”€â”€ Content area â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        content = tk.Frame(self, bg="#141414")
        content.pack(fill="both", expand=True)

        # Left: canvas container (both sides stacked, one visible)
        canvas_outer = tk.Frame(content, bg="#141414")
        canvas_outer.pack(side="left", fill="both", expand=True, padx=20, pady=16)

        tk.Label(canvas_outer, text="â†• sleep elementen  |  dubbelklik = tekst bewerken  |  Del = verwijderen",
                 bg="#141414", fg="#444", font=("Segoe UI",8)).pack(pady=(0,6))

        self.front_frame = tk.Frame(canvas_outer, bg="#141414")
        self.front_frame.pack()
        self.front_canvas = CardCanvas(self.front_frame, bg_color="#ffffff")
        self.front_canvas.pack()
        self.front_canvas.on_selection_changed = self._on_selection

        self.back_frame = tk.Frame(canvas_outer, bg="#141414")
        # not packed yet
        self.back_canvas = CardCanvas(self.back_frame, bg_color="#f5f0e8")
        self.back_canvas.pack()
        self.back_canvas.on_selection_changed = self._on_selection

        # Right: properties
        self.props = PropertiesPanel(content)
        self.props.pack(side="right", fill="y", padx=(0,16), pady=16)

        self._switch("front")

    # â”€â”€ Side switching â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    def _switch(self, side):
        if side == "front":
            self.back_frame.pack_forget()
            self.front_frame.pack()
            self._active_canvas = self.front_canvas
            self.tab_front.configure(bg="#3a9bd5", fg="white", font=("Segoe UI",10,"bold"))
            self.tab_back.configure(bg="#333", fg="#aaa", font=("Segoe UI",10))
        else:
            self.front_frame.pack_forget()
            self.back_frame.pack()
            self._active_canvas = self.back_canvas
            self.tab_back.configure(bg="#3a9bd5", fg="white", font=("Segoe UI",10,"bold"))
            self.tab_front.configure(bg="#333", fg="#aaa", font=("Segoe UI",10))
        self.props.show(self._active_canvas.selected, self._active_canvas)

    # â”€â”€ Toolbar callbacks â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    def _add_text(self):
        self._active_canvas.add_text()

    def _add_image(self):
        self._active_canvas.add_image()

    def _set_bg(self):
        color = colorchooser.askcolor(
            self._active_canvas.bg_color, parent=self,
            title="Achtergrondkleur kiezen")[1]
        if color:
            self._active_canvas.set_bg(color)

    def _on_selection(self, el):
        self.props.show(el, self._active_canvas)

    # â”€â”€ Save / Open â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    def _save(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".kaart",
            filetypes=[("Kaartbestand","*.kaart"),("JSON","*.json")],
            title="Ontwerp opslaan")
        if not path: return
        data = {"front": self.front_canvas.to_dict(),
                "back":  self.back_canvas.to_dict()}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        messagebox.showinfo("Opgeslagen", f"Ontwerp opgeslagen:\n{path}")

    def _open(self):
        path = filedialog.askopenfilename(
            filetypes=[("Kaartbestand","*.kaart"),("JSON","*.json")],
            title="Ontwerp openen")
        if not path: return
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        self.front_canvas.load_dict(data.get("front", {}))
        self.back_canvas.load_dict(data.get("back",  {}))
        self.props.show(None, self._active_canvas)
        messagebox.showinfo("Geopend", f"Ontwerp geladen:\n{path}")

    # â”€â”€ PDF Export â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    def _export_pdf(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".pdf",
            filetypes=[("PDF","*.pdf")],
            title="PDF opslaan alsâ€¦",
            initialfile="kaart_dubbelzijdig.pdf")
        if not path: return

        try:
            self._render_pdf(path)
            messagebox.showinfo(
                "PDF GeÃ«xporteerd",
                f"âœ…  PDF opgeslagen:\n{path}\n\n"
                "Pagina 1 = voorkant\nPagina 2 = achterkant\n\n"
                "Druk in op: Dubbelzijdig  â†’  Omslaan langs korte zijde\n"
                "(flip on short edge / flip on short side)")
        except Exception as e:
            messagebox.showerror("Fout bij exporteren", str(e))

    def _render_pdf(self, path):
        """Render beide zijden naar een A4-PDF (gecentreerd), klaar voor dubbelzijdig printen."""
        # A4 landscape of portrait? We center the A6 card on A4 portrait.
        page_w, page_h = A4  # 210 x 297 mm in points

        card_w_pt = CARD_W_MM * mm
        card_h_pt = CARD_H_MM * mm
        off_x = (page_w - card_w_pt) / 2
        off_y = (page_h - card_h_pt) / 2

        c = rl_canvas.Canvas(path, pagesize=A4)

        for side_canvas in [self.front_canvas, self.back_canvas]:
            data = side_canvas.to_dict()

            # Background
            bg = data.get("bg", "#ffffff")
            r, g, b = self._hex_to_rgb01(bg)
            c.setFillColorRGB(r, g, b)
            c.rect(off_x, off_y, card_w_pt, card_h_pt, fill=1, stroke=0)

            # Cut marks (small corner lines)
            c.setStrokeColorRGB(0.7, 0.7, 0.7)
            c.setLineWidth(0.3)
            for cx, cy in [(off_x, off_y),
                           (off_x+card_w_pt, off_y),
                           (off_x, off_y+card_h_pt),
                           (off_x+card_w_pt, off_y+card_h_pt)]:
                c.line(cx-8, cy, cx-3, cy)
                c.line(cx+3, cy, cx+8, cy)
                c.line(cx, cy-8, cx, cy-3)
                c.line(cx, cy+3, cx, cy+8)

            # Elements
            for el_d in data.get("elements", []):
                ex_mm = px_to_mm_x(el_d["x"])
                ey_mm = px_to_mm_y(el_d["y"])
                # ReportLab Y=0 is bottom; flip
                ex_pt = off_x + ex_mm * mm
                ey_pt = off_y + card_h_pt - ey_mm * mm

                if el_d["type"] == "text":
                    self._draw_text_rl(c, el_d, ex_pt, ey_pt)
                elif el_d["type"] == "image":
                    self._draw_image_rl(c, el_d, ex_pt, ey_pt)

            c.showPage()

        c.save()

    def _draw_text_rl(self, c, d, x, y):
        font = d.get("font", "Helvetica")
        bold   = d.get("bold",   False)
        italic = d.get("italic", False)

        # Map to ReportLab built-in fonts
        base = font if font in ("Helvetica","Times-Roman","Courier") else "Helvetica"
        if base == "Helvetica":
            if bold and italic: fn = "Helvetica-BoldOblique"
            elif bold:          fn = "Helvetica-Bold"
            elif italic:        fn = "Helvetica-Oblique"
            else:               fn = "Helvetica"
        elif base == "Times-Roman":
            if bold and italic: fn = "Times-BoldItalic"
            elif bold:          fn = "Times-Bold"
            elif italic:        fn = "Times-Italic"
            else:               fn = "Times-Roman"
        else:  # Courier
            if bold and italic: fn = "Courier-BoldOblique"
            elif bold:          fn = "Courier-Bold"
            elif italic:        fn = "Courier-Oblique"
            else:               fn = "Courier"

        # Scale font size from pixels to mm to points (approximate)
        size_px = d.get("size", 24)
        size_pt = size_px / CANVAS_H * CARD_H_MM * mm * 0.85

        r, g, b = self._hex_to_rgb01(d.get("color","#000000"))
        c.setFillColorRGB(r, g, b)
        c.setFont(fn, size_pt)

        align = d.get("align","left")
        text  = d.get("text","")
        # Multi-line support
        lines = text.split("\n")
        line_h = size_pt * 1.2
        for i, line in enumerate(lines):
            ly = y - i * line_h
            if align == "center":
                c.drawCentredString(x, ly, line)
            elif align == "right":
                c.drawRightString(x, ly, line)
            else:
                c.drawString(x, ly, line)

    def _draw_image_rl(self, c, d, x, y):
        path = d.get("path","")
        if not path or not os.path.exists(path): return
        w_pt = (d.get("width",100)  / CANVAS_W) * CARD_W_MM * mm
        h_pt = (d.get("height",100) / CANVAS_H) * CARD_H_MM * mm
        # y is top-left in canvas, but rl y is bottom-left
        c.drawImage(ImageReader(path),
                    x, y - h_pt, width=w_pt, height=h_pt,
                    preserveAspectRatio=False, mask="auto")

    @staticmethod
    def _hex_to_rgb01(hex_color):
        h = hex_color.lstrip("#")
        if len(h) == 3: h = "".join(c*2 for c in h)
        r = int(h[0:2],16)/255
        g = int(h[2:4],16)/255
        b = int(h[4:6],16)/255
        return r, g, b


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
if __name__ == "__main__":
    app = App()
    app.mainloop()
