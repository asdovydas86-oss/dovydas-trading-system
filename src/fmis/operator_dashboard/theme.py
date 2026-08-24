"""Every appearance decision, in one module and no other.

**This file is the redesign seam.** The brief that produced this dashboard said
the visual design *will* change. So the appearance lives here as one string, and
`fmis.operator_dashboard.render` emits semantic class names that mean what the
value *is* rather than what it should look like — `state-unavailable`, not
`amber`. Replacing this module changes the entire look without touching one line
of read-model construction, and replacing the render layer entirely still leaves
`models.py` and `sections.py` untouched.

**Colour semantics are deliberately conservative.** Three rules, and they are
what the palette below encodes:

  * **Green is not buy and red is not sell.** Colour marks a measured number's
    sign, a status, or an availability — never a suggested action. A confirmed
    setup is not painted green, because *confirmed* is a state the engines
    reached, not an instruction the owner should follow.

  * **WAIT must not look like failure, and NO TRADE must not look like an
    error.** Both are legitimate conclusions, and the most common way a
    dashboard lies is by painting a correct refusal in the colour of a fault.
    They get neutral treatment; only genuine unreadability is marked as a
    problem.

  * **Unavailable is not zero.** An absent figure renders in the muted absence
    style with its reason beside it, never as a dash that could be misread as a
    measured zero, and never as a blank cell.

**Dark by default, and light supported.** `prefers-color-scheme` picks; both
palettes are defined because the owner will read this at a desk and on a laptop
in daylight, and a dashboard that is unreadable in one of those is a dashboard
that gets closed.
"""

from __future__ import annotations

__all__ = ["STYLESHEET", "EQUITY_CHART_WIDTH", "EQUITY_CHART_HEIGHT"]

#: The equity chart's viewBox, in user units. Pixels are interpolated between
#: closed-trade steps; observations are not. The chart says so on the page.
EQUITY_CHART_WIDTH = 720
EQUITY_CHART_HEIGHT = 200


STYLESHEET = """
:root {
  --bg: #12151a;
  --panel: #181c23;
  --panel-2: #1e232b;
  --border: #2b323d;
  --text: #dde3ec;
  --muted: #8b95a5;
  --faint: #626c7c;
  --accent: #6ea8fe;
  --positive: #4ec9a0;
  --negative: #e0736d;
  --attention: #d8a657;
  --problem: #cf6679;
  --neutral: #7d8794;
}

@media (prefers-color-scheme: light) {
  :root {
    --bg: #f4f6f9;
    --panel: #ffffff;
    --panel-2: #f0f3f7;
    --border: #d6dce5;
    --text: #1b2029;
    --muted: #5c6675;
    --faint: #838d9c;
    --accent: #1f5fd0;
    --positive: #1a7f5f;
    --negative: #b03a34;
    --attention: #8a6116;
    --problem: #a32d3f;
    --neutral: #5c6675;
  }
}

* { box-sizing: border-box; }

body {
  margin: 0;
  background: var(--bg);
  color: var(--text);
  font: 13px/1.5 ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace;
}

a { color: var(--accent); text-decoration: none; }
a:hover { text-decoration: underline; }

/* ---------------------------------------------------------------- header */

header.top {
  position: sticky;
  top: 0;
  z-index: 10;
  background: var(--panel);
  border-bottom: 1px solid var(--border);
  padding: 10px 18px;
}

.brand {
  display: flex;
  align-items: baseline;
  gap: 14px;
  flex-wrap: wrap;
}

.brand h1 {
  font-size: 14px;
  letter-spacing: 0.14em;
  margin: 0;
  text-transform: uppercase;
}

.brand .ro {
  border: 1px solid var(--border);
  border-radius: 3px;
  color: var(--muted);
  font-size: 10px;
  letter-spacing: 0.12em;
  padding: 1px 7px;
  text-transform: uppercase;
}

.stamps {
  color: var(--muted);
  display: flex;
  flex-wrap: wrap;
  font-size: 11px;
  gap: 16px;
  margin-left: auto;
}

.stamps b { color: var(--text); font-weight: 600; }

nav.tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 2px;
  margin-top: 10px;
}

nav.tabs a {
  border: 1px solid transparent;
  border-radius: 3px 3px 0 0;
  color: var(--muted);
  font-size: 11px;
  letter-spacing: 0.1em;
  padding: 6px 13px;
  text-transform: uppercase;
}

nav.tabs a:hover { background: var(--panel-2); text-decoration: none; }

nav.tabs a.on {
  background: var(--panel-2);
  border-color: var(--border);
  color: var(--text);
}

/* ------------------------------------------------------------------ page */

main { margin: 0 auto; max-width: 1360px; padding: 18px; }

section.panel {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 4px;
  margin-bottom: 16px;
  overflow: hidden;
}

section.panel > h2 {
  align-items: baseline;
  background: var(--panel-2);
  border-bottom: 1px solid var(--border);
  display: flex;
  flex-wrap: wrap;
  font-size: 11px;
  gap: 12px;
  letter-spacing: 0.14em;
  margin: 0;
  padding: 8px 14px;
  text-transform: uppercase;
}

section.panel > h2 .meta {
  color: var(--faint);
  font-size: 10px;
  font-weight: 400;
  letter-spacing: 0.04em;
  margin-left: auto;
  text-transform: none;
}

.body { padding: 12px 14px; }

.grid {
  display: grid;
  gap: 16px;
  grid-template-columns: repeat(auto-fit, minmax(330px, 1fr));
}

/* ----------------------------------------------------------------- tiles */

.tiles {
  display: grid;
  gap: 10px;
  grid-template-columns: repeat(auto-fit, minmax(112px, 1fr));
}

.tile {
  background: var(--panel-2);
  border: 1px solid var(--border);
  border-radius: 3px;
  padding: 9px 11px;
}

.tile .k {
  color: var(--muted);
  font-size: 10px;
  letter-spacing: 0.09em;
  text-transform: uppercase;
}

.tile .v { font-size: 19px; margin-top: 3px; }
.tile .v.small { font-size: 13px; word-break: break-all; }

/* ---------------------------------------------------------------- tables */

table { border-collapse: collapse; font-size: 12px; width: 100%; }

th {
  border-bottom: 1px solid var(--border);
  color: var(--muted);
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.09em;
  padding: 6px 9px;
  text-align: left;
  text-transform: uppercase;
  white-space: nowrap;
}

td {
  border-bottom: 1px solid var(--border);
  padding: 6px 9px;
  vertical-align: top;
}

tbody tr:last-child td { border-bottom: none; }
tbody tr:hover { background: var(--panel-2); }

td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
td.sym { font-weight: 600; white-space: nowrap; }

.scroll { overflow-x: auto; }

/* ------------------------------------------------------- value semantics */

/* Sign of a measured number. Never an instruction. */
.pos { color: var(--positive); }
.neg { color: var(--negative); }
.zero { color: var(--text); }

/* Absence. Never rendered as a dash alone, never as a blank. */
.absent {
  color: var(--faint);
  font-style: italic;
}

.absent .why {
  color: var(--faint);
  display: block;
  font-size: 10px;
  font-style: normal;
  max-width: 46ch;
}

/* Secondary text that is muted but is NOT an absence — a market's full name
   under its id, a warning's evidence line. It borrows the muted colour and
   must not borrow the italic that marks a missing value, or a present value
   would read as a gap. */
.sub {
  color: var(--faint);
  font-size: 11px;
}

/* Distinct absence reasons for one table, printed once beneath it. */
ul.footnotes {
  color: var(--muted);
  font-size: 11px;
  margin: 4px 0;
  padding-left: 17px;
}

ul.footnotes li { margin: 2px 0; max-width: 100ch; }

/* ------------------------------------------------------ status chips */

.chip {
  border: 1px solid var(--border);
  border-radius: 3px;
  display: inline-block;
  font-size: 10px;
  letter-spacing: 0.08em;
  padding: 1px 7px;
  text-transform: uppercase;
  white-space: nowrap;
}

/* A state an engine reached. Emphasis, not endorsement: CONFIRMED is
   readable, not celebratory, because it is not a recommendation. */
.chip.state-confirmed { border-color: var(--accent); color: var(--accent); }
.chip.state-candidate { border-color: var(--neutral); color: var(--text); }

/* WAIT and NO TRADE are conclusions. Neutral, never the colour of a fault. */
.chip.state-wait { border-color: var(--border); color: var(--muted); }
.chip.state-no-trade { border-color: var(--border); color: var(--muted); }

/* Availability, not desirability. */
.chip.state-available { border-color: var(--positive); color: var(--positive); }
.chip.state-behind_schedule { border-color: var(--attention); color: var(--attention); }
.chip.state-schedule_unknown { border-color: var(--border); color: var(--muted); }
.chip.state-unsupported { border-color: var(--border); color: var(--faint); }
.chip.state-unavailable { border-color: var(--problem); color: var(--problem); }
.chip.state-absent { border-color: var(--border); color: var(--faint); }
.chip.state-empty { border-color: var(--border); color: var(--muted); }

.chip.sev-blocking { border-color: var(--problem); color: var(--problem); }
.chip.sev-attention { border-color: var(--attention); color: var(--attention); }
.chip.sev-informational { border-color: var(--border); color: var(--muted); }

/* ------------------------------------------------------------- messages */

.failed {
  background: var(--panel-2);
  border: 1px solid var(--problem);
  border-left-width: 3px;
  border-radius: 3px;
  padding: 10px 12px;
}

.failed .t {
  color: var(--problem);
  font-size: 10px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
}

.failed .m { color: var(--text); margin-top: 5px; word-break: break-word; }

.note {
  color: var(--muted);
  font-size: 11px;
  margin: 6px 0;
  max-width: 96ch;
}

.empty { color: var(--muted); font-style: italic; padding: 6px 0; }

/* --------------------------------------------------------------- detail */

details { margin-top: 8px; }

details > summary {
  color: var(--muted);
  cursor: pointer;
  font-size: 10px;
  letter-spacing: 0.09em;
  text-transform: uppercase;
  user-select: none;
}

details > summary:hover { color: var(--text); }
details[open] > summary { margin-bottom: 7px; }

dl.kv { display: grid; gap: 4px 14px; grid-template-columns: max-content 1fr; margin: 0; }
dl.kv dt { color: var(--muted); font-size: 11px; }
dl.kv dd { margin: 0; word-break: break-word; }

ul.plain { margin: 4px 0; padding-left: 17px; }
ul.plain li { margin: 2px 0; max-width: 92ch; }

/* ---------------------------------------------------------------- chart */

.chart { display: block; height: auto; max-width: 100%; width: 100%; }
.chart .axis { stroke: var(--border); stroke-width: 1; }
.chart .line { fill: none; stroke: var(--accent); stroke-width: 1.5; }
.chart .zero { stroke: var(--faint); stroke-dasharray: 3 3; stroke-width: 1; }
.chart .dot { fill: var(--accent); }
.chart text { fill: var(--muted); font-size: 10px; }

footer.foot {
  border-top: 1px solid var(--border);
  color: var(--faint);
  font-size: 11px;
  margin-top: 22px;
  padding: 14px 18px 30px;
}

footer.foot p { margin: 5px 0; max-width: 104ch; }
"""
