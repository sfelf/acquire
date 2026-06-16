from pathlib import Path
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
COVERAGE_XML = ROOT / "coverage.xml"
BADGE_PATH = ROOT / ".github" / "badges" / "coverage.svg"


def coverage_color(percentage):
    if percentage >= 90:
        return "#4c1"
    if percentage >= 75:
        return "#97ca00"
    if percentage >= 60:
        return "#dfb317"
    return "#e05d44"


def make_badge(percentage):
    label = "coverage"
    value = f"{percentage:.0f}%"
    label_width = 67
    value_width = max(38, 10 + len(value) * 7)
    width = label_width + value_width
    color = coverage_color(percentage)

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="20" role="img" aria-label="{label}: {value}">
  <title>{label}: {value}</title>
  <linearGradient id="s" x2="0" y2="100%">
    <stop offset="0" stop-color="#bbb" stop-opacity=".1"/>
    <stop offset="1" stop-opacity=".1"/>
  </linearGradient>
  <clipPath id="r"><rect width="{width}" height="20" rx="3" fill="#fff"/></clipPath>
  <g clip-path="url(#r)">
    <rect width="{label_width}" height="20" fill="#555"/>
    <rect x="{label_width}" width="{value_width}" height="20" fill="{color}"/>
    <rect width="{width}" height="20" fill="url(#s)"/>
  </g>
  <g fill="#fff" text-anchor="middle" font-family="Verdana,Geneva,DejaVu Sans,sans-serif" text-rendering="geometricPrecision" font-size="110">
    <text aria-hidden="true" x="{label_width * 5}" y="150" fill="#010101" fill-opacity=".3" transform="scale(.1)" textLength="{(label_width - 10) * 10}">{label}</text>
    <text x="{label_width * 5}" y="140" transform="scale(.1)" fill="#fff" textLength="{(label_width - 10) * 10}">{label}</text>
    <text aria-hidden="true" x="{(label_width + value_width / 2) * 10}" y="150" fill="#010101" fill-opacity=".3" transform="scale(.1)" textLength="{(value_width - 10) * 10}">{value}</text>
    <text x="{(label_width + value_width / 2) * 10}" y="140" transform="scale(.1)" fill="#fff" textLength="{(value_width - 10) * 10}">{value}</text>
  </g>
</svg>
"""


def main():
    coverage = ET.parse(COVERAGE_XML).getroot()
    percentage = float(coverage.attrib["line-rate"]) * 100
    BADGE_PATH.parent.mkdir(parents=True, exist_ok=True)
    BADGE_PATH.write_text(make_badge(percentage))


if __name__ == "__main__":
    main()
