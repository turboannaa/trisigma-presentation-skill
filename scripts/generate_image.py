#!/usr/bin/env python3
"""
generate_image.py — генерация графиков и схем в стиле Trisigma.

Типы:
  barchart   — столбчатая диаграмма (групповая или одиночная)
  linechart  — линейный график
  piechart   — круговая диаграмма
  flowchart  — блок-схема / архитектурная схема (блоки + стрелки + группы)

Использование:
  python3 scripts/generate_image.py --type barchart --config config.json [--upload] [--out result.png]
  python3 scripts/generate_image.py --type barchart --config '{"labels":...}' [--upload]

Флаги:
  --type     Тип изображения: barchart | linechart | piechart | flowchart
  --config   Путь к JSON-файлу или JSON-строка
  --upload   Загрузить в Google Drive и вернуть URL
  --out      Куда сохранить PNG (по умолчанию /tmp/trisigma_image.png)

После --upload выводит строку вида:
  URL: https://drive.google.com/uc?export=view&id=...
"""

import argparse
import json
import math
import os
import sys
import warnings

warnings.filterwarnings("ignore")

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.patheffects as pe
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Arc
import numpy as np

# ─── Brand palette ─────────────────────────────────────────────────────────────
C = {
    "dark":       "#003bff",   # Trisigma blue
    "medium":     "#6b9fff",   # mid blue
    "light":      "#b3ccff",   # light blue
    "xlight":     "#ccdaff",   # extra light blue
    "bg_blue":    "#f0f7ff",   # very light blue bg
    "bg_grey":    "#f4f5f7",   # light grey bg
    "border":     "#d0deff",   # border
    "text":       "#000000",
    "white":      "#ffffff",
    "axis":       "#cccccc",
}

SERIES_COLORS = [C["dark"], C["medium"], C["light"]]

DPI = 150


def setup_style():
    plt.rcParams.update({
        "font.family":       "sans-serif",
        "font.sans-serif":   ["Inter Tight", "Inter", "Helvetica Neue", "Arial", "DejaVu Sans"],
        "font.size":         11,
        "axes.spines.top":   False,
        "axes.spines.right": False,
        "axes.spines.left":  True,
        "axes.spines.bottom":True,
        "axes.edgecolor":    C["axis"],
        "axes.linewidth":    0.8,
        "xtick.color":       "#555555",
        "ytick.color":       "#555555",
        "xtick.labelsize":   10,
        "ytick.labelsize":   10,
        "figure.facecolor":  C["white"],
        "axes.facecolor":    C["white"],
        "grid.color":        "#eeeeee",
        "grid.linewidth":    0.6,
        "legend.frameon":    False,
        "legend.fontsize":   10,
    })


# ═══════════════════════════════════════════════════════════════════════════════
# BAR CHART
# ═══════════════════════════════════════════════════════════════════════════════

def make_barchart(cfg):
    """
    cfg keys:
      title     (str, optional)
      subtitle  (str, optional)
      labels    list[str]          — подписи групп по X
      series    list[{name, values}]  — ряды данных
      y_label   (str, optional)
      y_max     (float, optional)
      legend    (bool, default True)
      bar_width (float, default 0.22)
      colors    list[str] (optional, override palette)
    """
    setup_style()

    labels  = cfg["labels"]
    series  = cfg["series"]
    n_groups = len(labels)
    n_series = len(series)

    colors  = cfg.get("colors", SERIES_COLORS[:n_series])
    bw      = cfg.get("bar_width", 0.22)
    legend  = cfg.get("legend", True)
    y_max   = cfg.get("y_max", None)

    fig_w = max(7, n_groups * 2.2 + (2.5 if legend else 0.5))
    fig, ax = plt.subplots(figsize=(fig_w, 4.5))

    x = np.arange(n_groups)
    offsets = np.linspace(-(n_series - 1) / 2 * bw, (n_series - 1) / 2 * bw, n_series)

    for i, (ser, color, offset) in enumerate(zip(series, colors, offsets)):
        bars = ax.bar(x + offset, ser["values"], width=bw * 0.95,
                      color=color, label=ser.get("name", f"Series {i+1}"),
                      zorder=3, edgecolor="none", linewidth=0)
        # round tops
        for bar in bars:
            bar.set_linewidth(0)

    ax.set_xticks(x)
    ax.set_xticklabels([l.upper() for l in labels], fontsize=10, color="#333333")
    ax.yaxis.grid(True, zorder=0)
    ax.set_axisbelow(True)

    if y_max:
        ax.set_ylim(0, y_max)
    else:
        all_vals = [v for s in series for v in s["values"]]
        ax.set_ylim(0, max(all_vals) * 1.18)

    if cfg.get("y_label"):
        ax.set_ylabel(cfg["y_label"], fontsize=10, color="#555555")

    if cfg.get("title"):
        fig.suptitle(cfg["title"], fontsize=13, fontweight="bold",
                     x=0.05, ha="left", y=1.01, color=C["text"])

    if cfg.get("subtitle"):
        ax.set_title(cfg["subtitle"], fontsize=10, color="#555555",
                     loc="left", pad=6)

    if legend:
        handles = [mpatches.Patch(color=colors[i], label=ser.get("name", f"Series {i+1}"))
                   for i, ser in enumerate(series)]
        ax.legend(handles=handles, loc="upper left",
                  bbox_to_anchor=(1.02, 1), borderaxespad=0,
                  labelspacing=0.9, handlelength=0.9, handleheight=0.9)

    ax.spines["bottom"].set_color(C["axis"])
    ax.spines["left"].set_color(C["axis"])
    ax.tick_params(axis="both", length=0, pad=6)

    fig.tight_layout()
    return fig


# ═══════════════════════════════════════════════════════════════════════════════
# LINE CHART
# ═══════════════════════════════════════════════════════════════════════════════

def make_linechart(cfg):
    """
    cfg keys:
      title, subtitle, y_label
      x_labels  list[str]
      series    list[{name, values, dashed(bool)?}]
      y_max, legend
      colors
    """
    setup_style()

    x_labels = cfg.get("x_labels", [])
    series   = cfg["series"]
    n_series = len(series)
    colors   = cfg.get("colors", SERIES_COLORS[:n_series])
    legend   = cfg.get("legend", True)

    fig_w = max(7, len(x_labels) * 0.9 + (2.5 if legend else 0.5))
    fig, ax = plt.subplots(figsize=(fig_w, 4.5))

    x = np.arange(len(x_labels)) if x_labels else None

    for ser, color in zip(series, colors):
        vals = ser["values"]
        xs = x if x is not None else np.arange(len(vals))
        ls = "--" if ser.get("dashed") else "-"
        ax.plot(xs, vals, color=color, linewidth=2.2, linestyle=ls,
                marker="o", markersize=5, markerfacecolor=color,
                markeredgewidth=0, label=ser.get("name", ""), zorder=3)

        # light fill under line
        ax.fill_between(xs, vals, alpha=0.07, color=color, zorder=2)

    if x_labels:
        ax.set_xticks(x)
        ax.set_xticklabels(x_labels, fontsize=10, color="#333333")

    ax.yaxis.grid(True, zorder=0)
    ax.set_axisbelow(True)

    if cfg.get("y_max"):
        ax.set_ylim(0, cfg["y_max"])

    if cfg.get("y_label"):
        ax.set_ylabel(cfg["y_label"], fontsize=10, color="#555555")

    if cfg.get("title"):
        fig.suptitle(cfg["title"], fontsize=13, fontweight="bold",
                     x=0.05, ha="left", y=1.01, color=C["text"])

    if cfg.get("subtitle"):
        ax.set_title(cfg["subtitle"], fontsize=10, color="#555555", loc="left", pad=6)

    if legend and any(s.get("name") for s in series):
        ax.legend(loc="upper left", bbox_to_anchor=(1.02, 1),
                  borderaxespad=0, labelspacing=0.9)

    ax.spines["bottom"].set_color(C["axis"])
    ax.spines["left"].set_color(C["axis"])
    ax.tick_params(length=0, pad=6)
    fig.tight_layout()
    return fig


# ═══════════════════════════════════════════════════════════════════════════════
# PIE CHART
# ═══════════════════════════════════════════════════════════════════════════════

def make_piechart(cfg):
    """
    cfg keys:
      title, subtitle
      slices  list[{label, value, color(optional)}]
      donut   bool (default True)
      legend  bool (default True)
    """
    setup_style()

    slices  = cfg["slices"]
    labels  = [s["label"] for s in slices]
    values  = [s["value"] for s in slices]
    colors  = [s.get("color", SERIES_COLORS[i % len(SERIES_COLORS)])
               for i, s in enumerate(slices)]
    donut   = cfg.get("donut", True)
    legend  = cfg.get("legend", True)

    fig, ax = plt.subplots(figsize=(6, 4.5))
    wedge_props = {"linewidth": 2, "edgecolor": C["white"]}

    wedges, texts, autotexts = ax.pie(
        values,
        labels=None,
        colors=colors,
        autopct="%1.0f%%",
        startangle=90,
        wedgeprops=wedge_props,
        pctdistance=0.75 if donut else 0.6,
        textprops={"fontsize": 9, "color": C["white"], "fontweight": "bold"},
    )

    if donut:
        centre = plt.Circle((0, 0), 0.52, color=C["white"])
        ax.add_patch(centre)

    if legend:
        ax.legend(wedges, labels, loc="center left",
                  bbox_to_anchor=(1, 0.5), labelspacing=0.9,
                  handlelength=1, handleheight=1)

    if cfg.get("title"):
        fig.suptitle(cfg["title"], fontsize=13, fontweight="bold",
                     x=0.05, ha="left", y=1.02, color=C["text"])

    ax.set_aspect("equal")
    fig.tight_layout()
    return fig


# ═══════════════════════════════════════════════════════════════════════════════
# FLOW CHART  (блоки + стрелки)
# ═══════════════════════════════════════════════════════════════════════════════

# Цвета узлов
NODE_STYLES = {
    "dark":    {"facecolor": C["dark"],    "textcolor": C["white"],  "edgecolor": C["dark"]},
    "medium":  {"facecolor": C["medium"],  "textcolor": C["white"],  "edgecolor": C["medium"]},
    "light":   {"facecolor": C["light"],   "textcolor": C["dark"],   "edgecolor": C["light"]},
    "xlight":  {"facecolor": C["xlight"],  "textcolor": C["dark"],   "edgecolor": C["xlight"]},
    "outline": {"facecolor": C["white"],   "textcolor": C["dark"],   "edgecolor": C["dark"]},
    "bg_blue": {"facecolor": C["bg_blue"], "textcolor": C["dark"],   "edgecolor": C["border"]},
    "bg_grey": {"facecolor": C["bg_grey"], "textcolor": C["dark"],   "edgecolor": C["border"]},
}


def _draw_node(ax, node, all_nodes):
    """Draw a single box node.
    Supports optional 'title' + 'subtitle' for two-line cards with distinct styling.
    If only 'label' is provided, it is drawn centered as before.
    """
    x, y   = node["x"], node["y"]
    w, h   = node.get("w", 1.6), node.get("h", 0.45)
    style  = NODE_STYLES.get(node.get("style", "dark"), NODE_STYLES["dark"])
    radius = node.get("radius", 0.12)

    # rounding_size in data units — use min of w/h based fraction
    r = min(radius, w * 0.06, h * 0.25)
    box = FancyBboxPatch(
        (x - w / 2, y - h / 2), w, h,
        boxstyle=f"round,pad=0,rounding_size={r}",
        facecolor=style["facecolor"],
        edgecolor=style["edgecolor"],
        linewidth=0,          # no border stroke (avoids white anti-alias fringe)
        antialiased=False,    # no white fringe on RGBA transparent background
        zorder=3,
    )
    ax.add_patch(box)

    title    = node.get("title")
    subtitle = node.get("subtitle")

    if title:
        # Two-part card: title near top-left, subtitle just below it
        pad_x = w * 0.06
        pad_y = h * 0.14
        title_y = y + h / 2 - pad_y

        title_color = node.get("title_color", C["dark"])
        text_color  = node.get("text_color",  style["textcolor"])

        t = ax.text(x - w / 2 + pad_x, title_y, title,
                ha="left", va="top",
                fontsize=node.get("title_fontsize", node.get("fontsize", 9)),
                color=title_color, fontweight="bold",
                zorder=4, multialignment="left")

        if subtitle:
            # Gap based on actual title height in data units (scale-aware)
            title_fs = node.get("title_fontsize", node.get("fontsize", 9))
            title_lines = title.count("\n") + 1
            dupp_y = node.get("_dupp_y", 0.005)
            # 1 line height ≈ fontsize/72 * DPI * 1.35 (line spacing factor)
            title_line_h = title_fs / 72.0 * DPI * 1.35 * dupp_y
            gap = title_lines * title_line_h * 1.05  # 5% extra buffer
            subtitle_y = title_y - gap

            ax.text(x - w / 2 + pad_x, subtitle_y, subtitle,
                    ha="left", va="top",
                    fontsize=node.get("fontsize", 8.5),
                    color=text_color, zorder=4,
                    multialignment="left")
    else:
        label = node.get("label", "")
        ax.text(x, y, label,
                ha="center", va="center", fontsize=node.get("fontsize", 9),
                color=style["textcolor"], zorder=4,
                multialignment="center",
                wrap=False)


def _draw_group(ax, grp):
    """Draw a dashed-border container group."""
    x, y = grp["x"], grp["y"]
    w, h = grp.get("w", 2.2), grp.get("h", 2.0)

    r = min(0.15, w * 0.04, h * 0.08)
    box = FancyBboxPatch(
        (x, y), w, h,
        boxstyle=f"round,pad=0,rounding_size={r}",
        facecolor="none",
        edgecolor=C["border"],
        linewidth=1.2,
        linestyle="--",
        zorder=2,
    )
    ax.add_patch(box)

    if grp.get("label"):
        ax.text(x + 0.18, y + h - 0.18, grp["label"],
                ha="left", va="top",
                fontsize=grp.get("fontsize", 9.5),
                color=C["text"], fontweight="normal", zorder=4)


def _node_center(nid, node_map):
    n = node_map[nid]
    return n["x"], n["y"]


def _node_edge(nid, node_map, direction):
    """Get the edge point of a node in a given direction (right/left/up/down)."""
    n = node_map[nid]
    x, y = n["x"], n["y"]
    w, h = n.get("w", 1.6), n.get("h", 0.45)
    if direction == "right": return x + w / 2, y
    if direction == "left":  return x - w / 2, y
    if direction == "up":    return x, y + h / 2
    if direction == "down":  return x, y - h / 2
    return x, y


def _draw_arrow(ax, edge, node_map):
    """Draw an arrow between two nodes."""
    src = edge["from"]
    dst = edge["to"]

    # determine exit/enter direction
    exit_dir  = edge.get("exit",  "right")
    enter_dir = edge.get("enter", "left")

    sx, sy = _node_edge(src, node_map, exit_dir)
    ex, ey = _node_edge(dst, node_map, enter_dir)

    # optional waypoints for routing
    waypoints = edge.get("waypoints", [])

    color = edge.get("color", C["dark"])
    lw    = edge.get("lw", 1.2)

    if waypoints:
        # draw polyline
        pts = [(sx, sy)] + [tuple(p) for p in waypoints] + [(ex, ey)]
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        ax.plot(xs[:-1], ys[:-1], color=color, lw=lw, zorder=2, solid_capstyle="round")
        # arrow at the end
        ax.annotate("", xy=(ex, ey), xytext=(xs[-2], ys[-2]),
                    arrowprops=dict(arrowstyle="-|>", color=color,
                                   lw=lw, mutation_scale=10),
                    zorder=2)
    else:
        ax.annotate("", xy=(ex, ey), xytext=(sx, sy),
                    arrowprops=dict(arrowstyle="-|>", color=color,
                                   lw=lw, mutation_scale=10,
                                   connectionstyle=edge.get("curve", "arc3,rad=0")),
                    zorder=2)


def _draw_step_number(ax, num, x, y, size=0.28):
    """Draw a circled step number that appears as a true circle regardless of axes aspect ratio."""
    from matplotlib.patches import Ellipse as MEllipse
    xl = ax.get_xlim()
    yl = ax.get_ylim()
    fw, fh = ax.get_figure().get_size_inches()
    x_range = xl[1] - xl[0]
    y_range = yl[1] - yl[0]
    # Compute y-radius so the ellipse appears as a perfect circle in display space
    # display_rx = rx * fw/x_range; display_ry = ry * fh/y_range; for circle: rx*fw/x_range = ry*fh/y_range
    rx = size / 2
    ry = rx * (y_range / x_range) * (fw / fh)
    ellipse = MEllipse((x, y), 2 * rx, 2 * ry,
                       facecolor=C["dark"], edgecolor="none", zorder=5, linewidth=0)
    ax.add_patch(ellipse)
    ax.text(x, y, str(num), ha="center", va="center",
            fontsize=max(6, size * 28), color=C["white"], fontweight="bold", zorder=6)


def _estimate_node_height(node, dupp_y):
    """Estimate node height in data units to fit title + subtitle text."""
    title    = node.get("title")
    subtitle = node.get("subtitle")
    label    = node.get("label", "")

    pad_y_data = 0.14 * node.get("h", 0.45)  # fallback if no auto_h

    if title:
        title_fs    = node.get("title_fontsize", node.get("fontsize", 9))
        sub_fs      = node.get("fontsize", 8.5)
        title_lines = title.count("\n") + 1
        sub_lines   = subtitle.count("\n") + 1 if subtitle else 0

        line_h_title = title_fs / 72.0 * DPI * 1.35 * dupp_y
        line_h_sub   = sub_fs   / 72.0 * DPI * 1.35 * dupp_y

        top_pad    = title_fs / 72.0 * DPI * 0.9 * dupp_y   # top breathing room
        bottom_pad = top_pad
        inter_gap  = line_h_title * 0.4  # gap between title block and subtitle block

        total_text = (title_lines * line_h_title + inter_gap +
                      sub_lines   * line_h_sub)
        h = top_pad + total_text + bottom_pad
    else:
        fs = node.get("fontsize", 9)
        lines = max(label.count("\n") + 1, 1)
        line_h = fs / 72.0 * DPI * 1.35 * dupp_y
        pad = line_h * 0.8
        h = lines * line_h + 2 * pad

    return max(h, 0.3)


def make_flowchart(cfg):
    """
    cfg keys:
      title          (str, optional)
      canvas         [width, height] in data units (default auto)
      nodes  list of:
        id, label, x, y
        w (default 1.6), h (default 0.45)
        auto_h (bool) — auto-size height to fit text content
        style: dark|medium|light|xlight|outline|bg_blue|bg_grey
        fontsize (default 9)
        radius (default 0.12)
      groups  list of:
        label, x, y, w, h  — OR auto-computed if node_ids given
        node_ids  list[str] — nodes that belong to this group (for auto-bounds)
        pad       float     — equal padding around nodes (default 0.5)
        auto_center bool    — recompute bounds from node_ids (default True)
        fontsize (default 9.5)
      edges  list of:
        from, to
        exit:  right|left|up|down  (default right)
        enter: right|left|up|down  (default left)
        waypoints: [[x,y], ...]   (optional manual routing)
        curve: "arc3,rad=0.2"     (optional matplotlib connectionstyle)
        color  (default dark blue)
        lw     (default 1.2)
      step_numbers  list of {num, x, y}  (optional circled numbers)
      bottom_labels list of {text, x, y} (optional captions below columns)
      figsize  [w, h] (optional override)
    """
    setup_style()

    nodes   = cfg.get("nodes", [])
    groups  = cfg.get("groups", [])
    edges   = cfg.get("edges", [])
    step_ns = cfg.get("step_numbers", [])
    b_labels= cfg.get("bottom_labels", [])

    # build node map
    node_map = {n["id"]: n for n in nodes}

    # figure size
    if cfg.get("figsize"):
        fw, fh = cfg["figsize"]
    else:
        all_x = [n["x"] for n in nodes] + [g["x"] for g in groups] + \
                [g["x"] + g.get("w", 2.2) for g in groups]
        all_y = [n["y"] for n in nodes] + [g["y"] for g in groups] + \
                [g["y"] + g.get("h", 2.0) for g in groups]
        if all_x:
            span_x = max(all_x) - min(all_x) + 3.0
            span_y = max(all_y) - min(all_y) + 2.5
        else:
            span_x, span_y = 12, 7
        fw = max(10, span_x * 1.1)
        fh = max(5.5, span_y * 1.2)

    fig, ax = plt.subplots(figsize=(fw, fh))
    ax.axis("off")

    # ── White background (для схем на тёмных фонах) ───────────────────────────
    if cfg.get("white_bg"):
        fig.patch.set_facecolor("white")
        ax.set_facecolor("white")

    # ── Rough dupp_y estimate (for auto_h pass) ───────────────────────────────
    rough_ys = [n["y"] for n in nodes] or [0, 1]
    rough_y_range = (max(rough_ys) - min(rough_ys) + 2.0)
    rough_dupp_y = rough_y_range / (fh * DPI)

    # ── Auto-height pass: compute h for nodes with auto_h=True ───────────────
    for n in nodes:
        if n.get("auto_h"):
            n["h"] = _estimate_node_height(n, rough_dupp_y)

    # ── Auto-center groups around their nodes ─────────────────────────────────
    for grp in groups:
        if not grp.get("auto_center", True):
            continue
        node_ids = grp.get("node_ids")
        grp_nodes = [n for n in nodes if n["id"] in node_ids] if node_ids else nodes
        if not grp_nodes:
            continue
        grp_pad = grp.get("pad", 0.5)
        nodes_top   = max(n["y"] + n.get("h", 0.45) / 2 for n in grp_nodes)
        nodes_bot   = min(n["y"] - n.get("h", 0.45) / 2 for n in grp_nodes)
        nodes_left  = min(n["x"] - n.get("w", 1.6)  / 2 for n in grp_nodes)
        nodes_right = max(n["x"] + n.get("w", 1.6)  / 2 for n in grp_nodes)
        grp["x"] = nodes_left  - grp_pad
        grp["y"] = nodes_bot   - grp_pad
        grp["w"] = (nodes_right - nodes_left) + 2 * grp_pad
        grp["h"] = (nodes_top   - nodes_bot)  + 2 * grp_pad

    # ── compute bounds for ax limits — use full node extents ─────────────────
    all_x = (
        [n["x"] - n.get("w", 1.6) / 2 for n in nodes] +
        [n["x"] + n.get("w", 1.6) / 2 for n in nodes] +
        [g["x"]               for g in groups] +
        [g["x"] + g.get("w", 2.2) for g in groups] +
        [sn["x"] for sn in step_ns] +
        [bl["x"] for bl in b_labels]
    )
    all_y = (
        [n["y"] - n.get("h", 0.45) / 2 for n in nodes] +
        [n["y"] + n.get("h", 0.45) / 2 for n in nodes] +
        [g["y"]               for g in groups] +
        [g["y"] + g.get("h", 2.0) for g in groups] +
        [sn["y"] for sn in step_ns] +
        [bl["y"] for bl in b_labels]
    )

    if all_x:
        # Extra padding when groups present (dashed border needs room)
        pad = 0.7 if groups else 0.4
        ax.set_xlim(min(all_x) - pad, max(all_x) + pad)
        ax.set_ylim(min(all_y) - pad, max(all_y) + pad)

    # Compute data-units-per-pixel (y-axis) for font-gap calculation
    if all_y:
        y_range = (max(all_y) + pad) - (min(all_y) - pad)
        dupp_y = y_range / (fh * DPI)  # data units per pixel, y-axis
    else:
        dupp_y = 0.005
    # Inject scale into each node so _draw_node can compute correct gap
    for n in nodes:
        n['_dupp_y'] = dupp_y

    # draw groups first (behind everything)
    for grp in groups:
        _draw_group(ax, grp)

    # draw edges
    for edge in edges:
        _draw_arrow(ax, edge, node_map)

    # draw nodes
    for node in nodes:
        _draw_node(ax, node, node_map)

    # draw step numbers
    for sn in step_ns:
        _draw_step_number(ax, sn["num"], sn["x"], sn["y"], sn.get("size", 0.28))

    # draw bottom labels
    for bl in b_labels:
        ax.text(bl["x"], bl["y"], bl["text"],
                ha="center", va="top",
                fontsize=bl.get("fontsize", 9),
                color=C["text"], multialignment="center")

    if cfg.get("title"):
        fig.suptitle(cfg["title"], fontsize=13, fontweight="bold",
                     x=0.02, ha="left", y=1.0, color=C["text"])

    fig.tight_layout(pad=0.3)
    return fig


# ═══════════════════════════════════════════════════════════════════════════════
# GOOGLE DRIVE UPLOAD
# ═══════════════════════════════════════════════════════════════════════════════

def upload_to_drive(filepath, filename=None):
    """Upload a PNG to Google Drive, make it public, return view URL."""
    import pickle
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    TOKEN_PATH = os.path.join(os.path.dirname(__file__), "..", "token.json")
    TOKEN_PATH = os.path.abspath(TOKEN_PATH)

    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request

    SCOPES = [
        "https://www.googleapis.com/auth/presentations",
        "https://www.googleapis.com/auth/drive",
    ]

    creds = None
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            raise RuntimeError("Нет действующего токена. Запусти scripts/auth.py")

    drive = build("drive", "v3", credentials=creds)

    if not filename:
        filename = os.path.basename(filepath)

    file_meta = {
        "name": filename,
        "mimeType": "image/png",
    }
    media = MediaFileUpload(filepath, mimetype="image/png", resumable=False)

    f = drive.files().create(body=file_meta, media_body=media, fields="id").execute()
    file_id = f["id"]

    # make public
    drive.permissions().create(
        fileId=file_id,
        body={"type": "anyone", "role": "reader"},
    ).execute()

    url = f"https://drive.google.com/uc?export=view&id={file_id}"
    return url


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

MAKERS = {
    "barchart":  make_barchart,
    "linechart": make_linechart,
    "piechart":  make_piechart,
    "flowchart": make_flowchart,
}


def main():
    parser = argparse.ArgumentParser(description="Генерация изображений Trisigma")
    parser.add_argument("--type",   required=True, choices=MAKERS.keys())
    parser.add_argument("--config", required=True,
                        help="JSON-файл или JSON-строка с параметрами")
    parser.add_argument("--upload", action="store_true",
                        help="Загрузить в Google Drive и вывести URL")
    parser.add_argument("--out",    default="/tmp/trisigma_image.png",
                        help="Куда сохранить PNG")
    args = parser.parse_args()

    # load config
    if os.path.isfile(args.config):
        with open(args.config) as f:
            cfg = json.load(f)
    else:
        try:
            cfg = json.loads(args.config)
        except json.JSONDecodeError as e:
            print(f"Ошибка парсинга JSON: {e}", file=sys.stderr)
            sys.exit(1)

    # generate
    fig = MAKERS[args.type](cfg)
    transparent = not cfg.get("white_bg", False)
    fig.savefig(args.out, dpi=DPI, bbox_inches="tight",
                transparent=transparent, edgecolor="none")
    plt.close(fig)
    print(f"Saved: {args.out}")

    # upload
    if args.upload:
        url = upload_to_drive(args.out)
        print(f"URL: {url}")


if __name__ == "__main__":
    main()
