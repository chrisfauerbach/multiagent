"""SVG sanitization utilities for LLM-generated covers."""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET

_SVG_NS = "http://www.w3.org/2000/svg"
_MAX_FONT_SIZE = 48
_MAX_CHARS_PER_LINE = 20
_SANITIZED_ATTR = "data-sanitized"


def sanitize_svg(svg: str) -> str:
    """Fix common LLM issues in SVG markup: broken tags, text overflow, etc."""
    svg = _fix_svg_open_tag(svg)
    svg = _fix_text_elements(svg)
    return svg


def _fix_svg_open_tag(svg: str) -> str:
    svg_open_match = re.match(r"<svg([^>]*?)>", svg, re.DOTALL)
    if not svg_open_match:
        return svg
    attrs_raw = svg_open_match.group(1)
    has_valid_xmlns = 'xmlns="http://www.w3.org/2000/svg"' in attrs_raw
    vb_match = re.search(r'viewBox="(\d[\d\s.]+)"', attrs_raw)
    if has_valid_xmlns and vb_match:
        return svg
    viewbox = vb_match.group(1) if vb_match else "0 0 600 900"
    clean_open = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{viewbox}">'
    body = svg[svg_open_match.end():]
    return clean_open + body


def _fix_text_elements(svg: str) -> str:
    """Center text, clamp font sizes, wrap long text, and prevent overlaps."""
    try:
        ET.register_namespace("", _SVG_NS)
        root = ET.fromstring(svg)
    except ET.ParseError:
        return svg

    # If the root already has our marker, the SVG was already sanitized
    if root.get(_SANITIZED_ATTR):
        return svg

    # Extract viewBox height for clamping
    vb = root.get("viewBox", "0 0 600 900")
    try:
        vb_height = float(vb.split()[3])
    except (IndexError, ValueError):
        vb_height = 900.0

    text_els = list(root.iter(f"{{{_SVG_NS}}}text"))
    def _get_y(el: ET.Element) -> float:
        try:
            return float(el.get("y", "0"))
        except ValueError:
            return 0.0
    text_els.sort(key=_get_y)

    y_shift = 0.0  # cumulative downward shift from prior wraps

    for text_el in text_els:
        text_el.set("text-anchor", "middle")
        for attr in ("alignment-baseline", "dominant-baseline"):
            if attr in text_el.attrib:
                del text_el.attrib[attr]

        raw_size = text_el.get("font-size", "24")
        try:
            size = float(re.sub(r"[^\d.]", "", raw_size))
        except ValueError:
            size = 24
        if size > _MAX_FONT_SIZE:
            size = _MAX_FONT_SIZE
            text_el.set("font-size", str(int(size)))

        # Apply accumulated shift from previous wraps, clamped to viewBox
        y_str = text_el.get("y", "400")
        try:
            orig_y = float(y_str)
        except ValueError:
            orig_y = 400
        adjusted_y = min(orig_y + y_shift, vb_height - size)

        full_text = (text_el.text or "").strip()
        existing_tspans = list(text_el.findall(f"{{{_SVG_NS}}}tspan"))
        if not full_text and not existing_tspans:
            if y_shift:
                text_el.set("y", str(int(adjusted_y)))
            continue

        if existing_tspans:
            # LLM-generated tspans: clamp font sizes, apply shift, track lines
            for tspan in existing_tspans:
                tspan.set("text-anchor", "middle")
                tspan_size = tspan.get("font-size", "")
                if tspan_size:
                    try:
                        ts = float(re.sub(r"[^\d.]", "", tspan_size))
                        if ts > _MAX_FONT_SIZE:
                            tspan.set("font-size", str(int(_MAX_FONT_SIZE)))
                    except ValueError:
                        pass
            # Apply prior shift to this element, then accumulate for next
            if y_shift:
                text_el.set("y", str(int(adjusted_y)))
                first = existing_tspans[0]
                fy = first.get("y")
                if fy:
                    try:
                        first.set("y", str(int(float(fy) + y_shift)))
                    except ValueError:
                        pass
            extra_lines = len(existing_tspans) - 1
            if extra_lines > 0:
                y_shift += extra_lines * size * 1.3
            continue

        # No wrapping needed — just apply shift
        if len(full_text) <= _MAX_CHARS_PER_LINE:
            if y_shift:
                text_el.set("y", str(int(adjusted_y)))
            continue

        # Word-wrap long text into tspan lines
        x = text_el.get("x", "300")
        line_height = size * 1.3

        words = full_text.split()
        lines: list[str] = []
        current = ""
        for word in words:
            test = f"{current} {word}".strip()
            if len(test) > _MAX_CHARS_PER_LINE and current:
                lines.append(current)
                current = word
            else:
                current = test
        if current:
            lines.append(current)

        # First line stays at adjusted_y; extra lines push everything below down
        extra_lines = len(lines) - 1
        y_shift += extra_lines * line_height

        text_el.text = None
        text_el.set("y", str(int(adjusted_y)))
        for child in list(text_el):
            text_el.remove(child)
        for i, line in enumerate(lines):
            tspan = ET.SubElement(text_el, f"{{{_SVG_NS}}}tspan")
            tspan.set("x", x)
            if i == 0:
                tspan.set("y", str(int(adjusted_y)))
                tspan.set("dy", "0")
            else:
                tspan.set("dy", str(line_height))
            tspan.text = line

    # Mark as sanitized so subsequent calls are no-ops
    root.set(_SANITIZED_ATTR, "1")
    return ET.tostring(root, encoding="unicode")
