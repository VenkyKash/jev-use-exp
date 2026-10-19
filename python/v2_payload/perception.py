"""General-purpose perception module for Payload v2.

Transforms optical regions (text and interactive icons) into clustered visual
lines with coarse spatial tags, and generates immutable coordinate click
candidates bound to exact capture_ids when AX controls are sparse or absent.
"""
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
import math

from core import Candidate


@dataclass(frozen=True)
class VisualRegion:
    id: str
    kind: str  # 'text' or 'icon'
    text: str
    bounds: Dict[str, float]  # x, y, width, height in window-local screenshot px
    confidence: float
    interactive: bool = False


@dataclass(frozen=True)
class VisualLine:
    text: str
    location: str  # e.g., 'top-left', 'center', 'bottom-right'
    y_center: float
    regions: Tuple[VisualRegion, ...]


def parse_raw_regions(raw_regions: Any, min_confidence: float = 0.5) -> List[VisualRegion]:
    """Normalize raw regions from cua-perception into structured VisualRegion objects."""
    if isinstance(raw_regions, dict):
        raw_regions = raw_regions.get("regions", [])
    if not isinstance(raw_regions, (list, tuple)):
        return []
    result = []
    for r in raw_regions:
        if not isinstance(r, dict):
            continue
        conf = float(r.get("confidence", 0.0))
        if conf < min_confidence:
            continue
        kind = str(r.get("kind", "text"))
        text = str(r.get("text", "") or r.get("label", "")).replace("\u200e", "").replace("\u200f", "").strip()
        bounds = r.get("bounds")
        if not isinstance(bounds, dict):
            continue
        # Ensure valid numerical bounds
        if not all(k in bounds and isinstance(bounds[k], (int, float)) for k in ("x", "y", "width", "height")):
            continue
        if bounds["width"] <= 0 or bounds["height"] <= 0:
            continue
        interactive = bool(r.get("interactive", False))
        result.append(VisualRegion(
            id=str(r.get("id", f"reg-{len(result)}")),
            kind=kind,
            text=text,
            bounds={k: float(bounds[k]) for k in ("x", "y", "width", "height")},
            confidence=conf,
            interactive=interactive,
        ))
    return result


def cluster_into_lines(regions: List[VisualRegion], window_width: float, window_height: float) -> List[VisualLine]:
    """Group text regions into visual lines by vertical overlap, ordered top-to-bottom, left-to-right."""
    text_regions = [r for r in regions if r.kind == "text" and r.text]
    if not text_regions:
        return []

    # Sort primarily by y-midpoint
    sorted_regs = sorted(text_regions, key=lambda r: (r.bounds["y"] + r.bounds["height"] / 2.0))
    lines: List[List[VisualRegion]] = []

    for reg in sorted_regs:
        ry_mid = reg.bounds["y"] + reg.bounds["height"] / 2.0
        r_height = reg.bounds["height"]
        
        placed = False
        for line in lines:
            line_y_mid = sum(item.bounds["y"] + item.bounds["height"] / 2.0 for item in line) / len(line)
            avg_height = sum(item.bounds["height"] for item in line) / len(line)
            # If vertical distance is within 60% of average height, consider same line
            if abs(ry_mid - line_y_mid) <= max(r_height, avg_height) * 0.6:
                line.append(reg)
                placed = True
                break
        if not placed:
            lines.append([reg])

    result_lines = []
    w = max(1.0, window_width)
    h = max(1.0, window_height)

    for line in lines:
        # Sort items left to right
        line.sort(key=lambda r: r.bounds["x"])
        combined_text = " ".join(r.text for r in line)
        avg_x = sum(r.bounds["x"] + r.bounds["width"] / 2.0 for r in line) / len(line)
        avg_y = sum(r.bounds["y"] + r.bounds["height"] / 2.0 for r in line) / len(line)

        # Compute coarse 3x3 location tag
        v_tag = "top" if avg_y < h * 0.33 else ("bottom" if avg_y > h * 0.66 else "middle")
        h_tag = "left" if avg_x < w * 0.33 else ("right" if avg_x > w * 0.66 else "center")
        loc = f"{v_tag}-{h_tag}"

        result_lines.append(VisualLine(
            text=combined_text,
            location=loc,
            y_center=avg_y,
            regions=tuple(line),
        ))

    # Sort all lines from top to bottom
    result_lines.sort(key=lambda l: l.y_center)
    return result_lines


def format_visual_lines_for_prompt(lines: List[VisualLine], max_lines: int = 40, max_bytes: int = 3500) -> List[str]:
    """Format visual lines for Jev state presentation with a strict budget and overflow reporting.
    
    Preserves both top lines (headers, menus, top rows) and bottom lines (tabs, status bars, footers)
    when budget constraints require truncation.
    """
    if not lines:
        return []

    if len(lines) <= max_lines:
        candidates = list(lines)
        omitted_in_middle = 0
    else:
        head_count = max_lines // 2
        tail_count = max_lines - head_count
        candidates = list(lines[:head_count]) + list(lines[-tail_count:])
        omitted_in_middle = len(lines) - max_lines

    formatted = []
    total_bytes = 0
    overflow = 0

    for idx, line in enumerate(candidates):
        if omitted_in_middle > 0 and idx == (max_lines // 2):
            marker = f"... ({omitted_in_middle} intermediate visually detected lines omitted due to budget)"
            marker_bytes = len(marker.encode("utf-8"))
            if total_bytes + marker_bytes <= max_bytes:
                formatted.append(marker)
                total_bytes += marker_bytes

        entry = f"[{line.location}] {line.text}"
        entry_bytes = len(entry.encode("utf-8"))
        if total_bytes + entry_bytes > max_bytes:
            overflow += 1
            continue
        formatted.append(entry)
        total_bytes += entry_bytes

    if overflow > 0:
        formatted.append(f"... ({overflow} additional visually detected lines omitted due to byte budget)")
    return formatted


def should_trigger_adaptive_perception(
    observation: Any,
    has_dominant_canvas: bool,
    force_look_closely: bool = False,
    last_capture_id: Optional[str] = None
) -> Tuple[bool, bool]:
    """Decide whether to invoke optical perception based on accessibility density and window type.
    
    Returns:
        (should_run, use_cached)
    """
    if force_look_closely:
        return (True, False)
        
    cid = getattr(observation, "capture_id", None)
    if not cid:
        return (False, False)

    # Initial grounding on the task: run optical perception once to ground layout
    if last_capture_id is None:
        return (True, False)

    # Subsequent steps: only Jev's explicit decision (force_look_closely) triggers OCR
    return (False, True)


def build_visual_click_candidates(
    regions: List[VisualRegion],
    observation: Any,
    accepts: Any,
    existing_candidates: Dict[str, Any],
    region_bounds: Optional[Tuple[float, float, float, float]] = None,
    max_candidates: int = 20
) -> List[Candidate]:
    """Generate immutable coordinate click candidates for visual regions not covered by AX controls."""
    cid = getattr(observation, "capture_id", None)
    if not cid:
        return []

    # Find window origin to translate AX screen frames to window-local coordinates
    win_x = 0.0
    win_y = 0.0
    for e in getattr(observation, "elements", ()):
        if getattr(e, "role", "") == "AXWindow" and getattr(e, "frame", None):
            win_x = float(e.frame[0])
            win_y = float(e.frame[1])
            break

    # Map existing interactive AX controls to avoid duplicate clicks, but exclude
    # large canvas background containers (like spreadsheet grids or DAW timeline backdrops)
    ax_boxes = []
    for e in getattr(observation, "elements", ()):
        f = getattr(e, "frame", None)
        if f and isinstance(f, (list, tuple)) and len(f) == 4:
            area = float(f[2]) * float(f[3])
            # Skip the window container itself or massive background containers
            if getattr(e, "role", "") in ("AXWindow", "AXUnknown") or area >= 100000:
                continue
            # Translate from screen coordinates to window-local coordinates
            rel_f = (float(f[0]) - win_x, float(f[1]) - win_y, float(f[2]), float(f[3]))
            ax_boxes.append(rel_f)

    def overlaps_ax(box: Dict[str, float]) -> bool:
        bx, by, bw, bh = box["x"], box["y"], box["width"], box["height"]
        for ax_f in ax_boxes:
            ax_x, ax_y, ax_w, ax_h = ax_f
            # Check bounding box overlap
            if not (bx + bw < ax_x or bx > ax_x + ax_w or by + bh < ax_y or by > ax_y + ax_h):
                return True
        return False

    candidates = []
    # Filter candidates: text regions and interactive icons
    clickable_regions = []
    for r in regions:
        if (r.kind == "text" and r.text and len(r.text) <= 60) or (r.kind == "icon" and r.interactive):
            if region_bounds:
                rx, ry, rw, rh = region_bounds
                by_mid = r.bounds["y"] + r.bounds["height"] / 2.0
                bx_mid = r.bounds["x"] + r.bounds["width"] / 2.0
                if not (rx <= bx_mid <= rx + rw and ry <= by_mid <= ry + rh):
                    continue
            clickable_regions.append(r)

    w_width = 1000.0
    for e in getattr(observation, "elements", ()):
        f = getattr(e, "frame", None)
        if f and isinstance(f, (list, tuple)) and len(f) == 4 and getattr(e, "parent", None) is None:
            w_width = float(f[2])
            break

    # Sort candidates in natural visual reading order: top-to-bottom, left-to-right
    def visual_sort_key(r):
        y_band = round(r.bounds["y"] / 16.0) * 16.0
        return (y_band, r.bounds["x"])

    clickable_regions.sort(key=visual_sort_key)

    for r in clickable_regions:
        if len(candidates) >= max_candidates:
            break
        if overlaps_ax(r.bounds):
            continue

        cx = r.bounds["x"] + r.bounds["width"] / 2.0
        cy = r.bounds["y"] + r.bounds["height"] / 2.0
        c_id = f"visual-click-{r.id}"
        if c_id not in existing_candidates:
            desc = f"Click visually rendered {r.kind} {r.text!r} (at {int(cx)}, {int(cy)})"
            args = {
                "pid": observation.pid,
                "window_id": observation.window_id,
                "capture_id": cid,
                "x": cx,
                "y": cy,
                "delivery_mode": "foreground"
            }
            if accepts("click", args):
                candidates.append(Candidate(c_id, desc, "click", args))

        # Shift-click to extend selection into range (if modifier is accepted and capacity permits)
        if len(candidates) < max_candidates and r.kind == "text":
            shift_c_id = f"visual-shift-click-{r.id}"
            if shift_c_id not in existing_candidates:
                shift_args = {
                    "pid": observation.pid,
                    "window_id": observation.window_id,
                    "capture_id": cid,
                    "x": cx,
                    "y": cy,
                    "modifier": ["shift"],
                    "delivery_mode": "foreground"
                }
                if accepts("click", shift_args):
                    shift_desc = f"Shift-click visually rendered text {r.text!r} (at {int(cx)}, {int(cy)}) to extend selection into a range"
                    candidates.append(Candidate(shift_c_id, shift_desc, "click", shift_args))

    return candidates
