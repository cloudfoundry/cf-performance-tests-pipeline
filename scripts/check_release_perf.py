#!/usr/bin/env python3
"""
Usage: python3 check_release_perf.py <capi-version>
  e.g. python3 check_release_perf.py 1.251.0

Scans results/rails/{mysql,postgres,postgres15} for JSON test results,
finds 10 runs before the given capi release and all runs from that release
onward, then outputs an HTML file with charts for endpoints that changed
by >=25% compared to the baseline (mean of the 10 prior runs).
"""

import argparse
import datetime
import glob
import json
import os
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

CHANGE_THRESHOLD = 0.25   # 25%
BASELINE_RUNS = 10
DB_TYPES = ["postgres15", "postgres", "mysql"]

SCRIPT_DIR = Path(__file__).parent
REPO_ROOT = SCRIPT_DIR.parent
RESULTS_BASE = REPO_ROOT / "results" / "rails"


def parse_version(version_str: str):
    """Parse a version string like '1.251.0' or '1.252.0-rc (abc1234)' into a
    comparable tuple.  RC builds sort *before* the final release of the same
    version number so that the timeline is preserved correctly.
    Returns (major, minor, patch, rc_flag, rc_sha) where rc_flag=0 means final."""
    m = re.match(r'(\d+)\.(\d+)\.(\d+)(?:-rc\s*\(([^)]+)\))?', version_str.strip())
    if not m:
        return (0, 0, 0, 0, '')
    major, minor, patch = int(m.group(1)), int(m.group(2)), int(m.group(3))
    rc_sha = m.group(4) or ''
    # rc builds come before the final; use 0 for final, 1 for rc so final > rc
    rc_flag = 1 if rc_sha else 0
    return (major, minor, patch, rc_flag, rc_sha)


def version_base(version_str: str):
    """Return (major, minor, patch) tuple ignoring rc suffix."""
    m = re.match(r'(\d+)\.(\d+)\.(\d+)', version_str.strip())
    if not m:
        return (0, 0, 0)
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)))


def format_ts(ts: int) -> str:
    return datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M')


def load_json_results(db_type: str):
    """Load all valid JSON result files for a given DB type.
    Returns a list of dicts with keys: timestamp, capi_version, cf_version, measurements.
    Sorted by timestamp ascending."""
    base = RESULTS_BASE / db_type / "results"
    if not base.exists():
        return []

    records = []
    for suite_dir in sorted(base.iterdir()):
        if not suite_dir.is_dir():
            continue
        for version_dir in sorted(suite_dir.iterdir()):
            if not version_dir.is_dir():
                continue
            for json_file in sorted(version_dir.glob("*-test-results-*.json")):
                try:
                    with open(json_file) as f:
                        data = json.load(f)
                except Exception:
                    continue
                if not all(k in data for k in ('cfDeploymentVersion', 'capiVersion', 'timestamp', 'measurements')):
                    continue
                records.append({
                    'timestamp': data['timestamp'],
                    'capi_version': data['capiVersion'],
                    'cf_version': data['cfDeploymentVersion'],
                    'measurements': data['measurements'],
                    'file': str(json_file),
                    'suite': suite_dir.name,
                    'api_version': version_dir.name,
                })

    records.sort(key=lambda r: r['timestamp'])
    return records


def collect_endpoint_series(records):
    """Build per-endpoint time series from all records.
    Returns: {endpoint_name: [ {label, ts, smallest, average, largest}, ... ]}
    """
    series = {}
    for rec in records:
        label = f"{rec['cf_version']} / {format_ts(rec['timestamp'])} / {rec['capi_version']}"
        for ep, meas in rec['measurements'].items():
            rt = meas.get('request time', {})
            if 'Average' not in rt:
                continue
            if ep not in series:
                series[ep] = []
            series[ep].append({
                'label': label,
                'ts': rec['timestamp'],
                'capi_version': rec['capi_version'],
                'smallest': rt.get('Smallest', rt['Average']),
                'average': rt['Average'],
                'largest': rt.get('Largest', rt['Average']),
            })
    # Each endpoint list is already ordered because records are sorted
    return series


def find_changed_endpoints(series, target_base, baseline_runs=BASELINE_RUNS, threshold=CHANGE_THRESHOLD):
    """For each endpoint, determine if the average changed by >= threshold when
    the target release first appeared, compared to the mean of the prior runs.

    Splitting is done by timeline position (timestamp order), not by version
    number comparison, because RC builds of a later release often run
    concurrently with or just before the stable release we want to check.

    Returns: {endpoint_name: {'baseline_avg': float, 'change': float, 'direction': 'worse'|'better',
                               'data_points': [...all points for window...],
                               'target_start_idx': int  (index in data_points where target begins)}}
    """
    changed = {}
    target_tuple = version_base(target_base)

    for ep, points in series.items():
        # Points are already sorted by timestamp (records were sorted before building series).
        # Find the index of the first point whose capi version matches the target.
        first_target_idx = None
        for idx, p in enumerate(points):
            if version_base(p['capi_version']) == target_tuple:
                first_target_idx = idx
                break

        if first_target_idx is None:
            continue  # target release never appeared

        # Baseline: the `baseline_runs` runs immediately before the first target run,
        # excluding any runs from versions >= target (e.g. RC builds that ran just before
        # the stable release was tagged).
        pre_target = [p for p in points[:first_target_idx]
                      if version_base(p['capi_version']) < target_tuple]
        baseline_points = pre_target[-baseline_runs:]
        if not baseline_points:
            continue

        baseline_avg = sum(p['average'] for p in baseline_points) / len(baseline_points)
        if baseline_avg == 0:
            continue

        # Only runs of exactly the target version (no newer releases)
        target_only = [p for p in points[first_target_idx:]
                       if version_base(p['capi_version']) == target_tuple]
        if not target_only:
            continue

        target_mean = sum(p['average'] for p in target_only) / len(target_only)
        change = (target_mean - baseline_avg) / baseline_avg  # positive = worse (slower)

        if abs(change) < threshold:
            continue

        # Detect flappy: large-amplitude alternating swings (not just small wiggles).
        # We require both high reversal rate AND that each reversal's swing amplitude
        # is large relative to the mean — ruling out smooth trends with minor noise.
        window_avgs = [p['average'] for p in baseline_points + target_only]
        mean_w = sum(window_avgs) / len(window_avgs)
        diffs = [window_avgs[i+1] - window_avgs[i] for i in range(len(window_avgs)-1)]
        reversal_pairs = [(i, diffs[i], diffs[i+1]) for i in range(len(diffs)-1) if diffs[i] * diffs[i+1] < 0]
        reversal_rate = len(reversal_pairs) / max(len(diffs) - 1, 1)
        if reversal_pairs and mean_w:
            # amplitude at each reversal = combined jump in and out of the peak/trough
            avg_reversal_amplitude = sum(abs(d1) + abs(d2) for _, d1, d2 in reversal_pairs) / len(reversal_pairs) / mean_w
        else:
            avg_reversal_amplitude = 0
        # Flappy: reversals in >50% of pairs AND each reversal swings >40% of the mean
        is_flappy = reversal_rate > 0.5 and avg_reversal_amplitude > 0.40

        # Window: baseline runs + target-version runs only (no later releases)
        window = baseline_points + target_only
        target_start_idx = len(baseline_points)

        changed[ep] = {
            'baseline_avg': baseline_avg,
            'change': change,
            'direction': 'flappy' if is_flappy else ('worse' if change > 0 else 'better'),
            'data_points': window,
            'target_start_idx': target_start_idx,
        }

    return changed


# ---------------------------------------------------------------------------
# HTML / Chart generation (inline Chart.js)
# ---------------------------------------------------------------------------

CHART_JS_CDN = "https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"

HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>CAPI {version} Performance Test Results Check</title>
<script src="{chartjs}"></script>
<style>
  body {{ font-family: system-ui, sans-serif; background: #e8eef4; margin: 0; padding: 16px; color: #222; }}
  h1 {{ font-size: 1.4rem; margin-bottom: 4px; }}
  .subtitle {{ color: #666; font-size: 0.9rem; margin-bottom: 24px; }}
  .columns {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 24px; align-items: start; }}
  .column {{ min-width: 0; }}
  h2 {{ font-size: 1.1rem; margin-top: 0; margin-bottom: 8px; border-bottom: 2px solid #c5d3e0; padding-bottom: 4px; }}
  h3 {{ font-size: 0.85rem; margin: 12px 0 4px; color: #444; }}
  .badge {{ display:inline-block; padding: 2px 5px; border-radius: 4px; font-size: 0.7rem; font-weight: bold; vertical-align: middle; }}
  .worse {{ background:#fde8e8; color:#c0392b; }}
  .better {{ background:#e8f8e8; color:#1a7a1a; }}
  .flappy {{ background:#fff0d8; color:#b05a00; }}
  .chart-wrap {{ background: white; border: 1px solid #c5d3e0; border-radius: 6px; padding: 10px 12px; margin-bottom: 16px; cursor: pointer; position: relative; }}
  .chart-wrap:hover {{ box-shadow: 0 2px 8px rgba(0,0,0,0.15); }}
  .chart-title {{ font-size: 0.85rem; font-weight: bold; color: #444; margin: 0 0 4px 0; padding-right: 70px; }}
  .chart-badge {{ position: absolute; top: 10px; right: 12px; }}
  canvas {{ max-width: 100%; }}
  .no-changes {{ color: #888; font-style: italic; padding: 8px 0; }}
  .summary-table {{ width: 100%; border-collapse: collapse; font-size: 0.8rem; margin-bottom: 16px; }}
  .summary-table th, .summary-table td {{ border: 1px solid #b0c4d8; padding: 5px 8px; text-align: left; }}
  .summary-table th {{ background: #c8d8e8; }}
  .summary-table td {{ background: #d8e6f0; }}
  .summary-table tr:hover td {{ background: #ccdce8; cursor: pointer; }}
  .summary-table .col-ep {{ width: 40%; word-break: break-word; }}
  .summary-table .col-num {{ width: 13%; white-space: nowrap; }}
  .summary-table .col-chg {{ width: 10%; white-space: nowrap; }}
  .summary-table .col-dir {{ width: 10%; text-align: center; }}
  .badge {{ display:inline-block; padding: 2px 5px; border-radius: 4px; font-size: 0.7rem; font-weight: bold; margin-left: 6px; vertical-align: middle; }}
  .tooltip-wrap {{ position: relative; display: inline-block; cursor: help; border-bottom: 1px dotted #555; }}
  .tooltip-wrap .tooltip-text {{
    visibility: hidden; opacity: 0;
    background: #333; color: #fff;
    font-size: 0.75rem; font-weight: normal;
    text-align: left; white-space: nowrap;
    border-radius: 4px; padding: 5px 8px;
    position: absolute; z-index: 10;
    bottom: 125%; left: 50%; transform: translateX(-50%);
    transition: opacity 0.15s;
    pointer-events: none;
  }}
  .tooltip-wrap:hover .tooltip-text {{ visibility: visible; opacity: 1; }}
  /* modal overlay */
  #modal-overlay {{
    display: none; position: fixed; inset: 0;
    background: rgba(0,0,0,0.7); z-index: 1000;
    align-items: center; justify-content: center;
  }}
  #modal-overlay.active {{ display: flex; }}
  #modal-box {{
    background: white; border-radius: 8px; padding: 20px 24px;
    width: 92vw; max-height: 90vh; box-sizing: border-box;
    display: flex; flex-direction: column; gap: 8px;
  }}
  #modal-title {{ font-size: 0.95rem; font-weight: bold; color: #333; }}
  #modal-canvas-wrap {{ flex: 1; min-height: 0; position: relative; }}
  #modal-canvas-wrap canvas {{ width: 100% !important; height: 100% !important; }}
</style>
</head>
<body>
<h1>CAPI {version} Performance Test Results Check</h1>
<p class="subtitle">
  Endpoints with &ge;{threshold}% change in average response time compared to baseline
  (mean of up to {baseline} runs before the release).<br/>
  Baseline runs shown in <span style="color:#888">grey</span> region,
  target release in <span style="color:#e67e22">orange</span> vertical band.
</p>

<div class="columns">
{body}
</div>

<!-- modal overlay -->
<div id="modal-overlay">
  <div id="modal-box">
    <div style="display:flex; justify-content:space-between; align-items:center;">
      <span id="modal-title"></span>
      <span style="cursor:pointer; font-size:1.3rem; color:#888; line-height:1;" onclick="closeModal()">&#x2715;</span>
    </div>
    <div id="modal-canvas-wrap" style="height: 70vh;"><canvas id="modal-canvas"></canvas></div>
  </div>
</div>

<script>
// chart registry: id -> Chart.js config (data + options)
const chartRegistry = {{}};

function openModal(chartId, title) {{
  const overlay = document.getElementById('modal-overlay');
  document.getElementById('modal-title').textContent = title;
  const wrap = document.getElementById('modal-canvas-wrap');
  wrap.innerHTML = '<canvas id="modal-canvas"></canvas>';
  const reg = chartRegistry[chartId];
  if (reg) new Chart(document.getElementById('modal-canvas'), {{
    type: 'line',
    plugins: [reg.plugin],
    data: JSON.parse(JSON.stringify(reg.data)),
    options: JSON.parse(JSON.stringify(reg.options)),
  }});
  overlay.classList.add('active');
}}

function closeModal() {{
  document.getElementById('modal-overlay').classList.remove('active');
}}

document.getElementById('modal-overlay').addEventListener('click', function(e) {{
  if (e.target === this) closeModal();
}});

document.addEventListener('keydown', function(e) {{
  if (e.key === 'Escape') closeModal();
}});

{scripts}
</script>
</body>
</html>
"""

# Chart.js dataset colors matching the existing matplotlib charts (blue/orange/green)
COLORS = {
    'smallest': {'border': '#1f77b4', 'bg': 'rgba(31,119,180,0.15)'},
    'average':  {'border': '#ff7f0e', 'bg': 'rgba(255,127,14,0.15)'},
    'largest':  {'border': '#2ca02c', 'bg': 'rgba(44,160,44,0.15)'},
}


def make_chart_id(db_type, ep_name):
    import hashlib
    safe = re.sub(r'[^a-zA-Z0-9]', '_', f"{db_type}_{ep_name}")
    if len(safe) > 80:
        suffix = hashlib.md5(f"{db_type}_{ep_name}".encode()).hexdigest()[:8]
        safe = safe[:72] + '_' + suffix
    return safe


def js_array(values):
    def fmt(v):
        if v is None:
            return 'null'
        return f'{v:.6f}'
    return '[' + ', '.join(fmt(v) for v in values) + ']'


def build_db_section(db_type, changed_endpoints, threshold=CHANGE_THRESHOLD):
    if not changed_endpoints:
        return f'<div class="column"><h2>DB: {db_type}</h2>\n<p class="no-changes">No endpoints changed by &ge;{int(threshold*100)}% for this DB type.</p>\n</div>', ''

    # worse first, then flappy, then better — each group sorted by magnitude
    sorted_eps = (
        sorted([(k, v) for k, v in changed_endpoints.items() if v['direction'] == 'worse'], key=lambda x: -x[1]['change']) +
        sorted([(k, v) for k, v in changed_endpoints.items() if v['direction'] == 'flappy'], key=lambda x: -abs(x[1]['change'])) +
        sorted([(k, v) for k, v in changed_endpoints.items() if v['direction'] == 'better'], key=lambda x: x[1]['change'])
    )

    html_parts = [f'<div class="column">\n<h2>DB: {db_type}</h2>\n']
    html_parts.append('<table class="summary-table"><tr>'
                      '<th class="col-ep">Endpoint</th>'
                      '<th class="col-num"><span class="tooltip-wrap">Baseline avg (s)'
                      '<span class="tooltip-text">Mean of the &apos;Average&apos; response time<br/>across the 10 baseline runs before this release</span>'
                      '</span></th>'
                      '<th class="col-num">Latest value (s)</th>'
                      '<th class="col-chg">Change</th>'
                      '<th class="col-dir">Direction</th></tr>\n')
    for ep, info in sorted_eps:
        pct = info['change'] * 100
        sign = '+' if pct > 0 else ''
        chart_id = make_chart_id(db_type, ep)
        new_value = info['data_points'][-1]['average']
        html_parts.append(
            f'<tr style="cursor:pointer;" onclick="document.getElementById(\'anchor_{chart_id}\').scrollIntoView({{behavior:\'smooth\',block:\'start\'}})">'
            f'<td class="col-ep">{ep}</td>'
            f'<td class="col-num">{info["baseline_avg"]:.4f}</td>'
            f'<td class="col-num">{new_value:.4f}</td>'
            f'<td class="col-chg">{sign}{pct:.1f}%</td>'
            f'<td class="col-dir"><span class="badge {info["direction"]}">{info["direction"].upper()}</span></td></tr>\n'
        )
    html_parts.append('</table>\n')

    js_blocks = []

    for ep, info in sorted_eps:
        chart_id = make_chart_id(db_type, ep)
        points = info['data_points']
        labels = [p['label'] for p in points]
        smallest = [p['smallest'] for p in points]
        average = [p['average'] for p in points]
        largest = [p['largest'] for p in points]
        tidx = info['target_start_idx']
        pct = info['change'] * 100
        sign = '+' if pct > 0 else ''
        direction = info['direction']

        html_parts.append(
            f'<div id="anchor_{chart_id}" class="chart-wrap" onclick="openModal(\'{chart_id}\', \'{ep.replace(chr(39), chr(39)+chr(39))} ({sign}{pct:.1f}%)\')">\n'
            f'<span class="badge {direction} chart-badge">{sign}{pct:.1f}%</span>\n'
            f'<p class="chart-title">{ep}</p>\n'
            f'<canvas id="{chart_id}" height="80"></canvas>\n'
            f'</div>\n'
        )

        # Build JS for this chart
        labels_js = json.dumps(labels)
        smallest_js = js_array(smallest)
        average_js = js_array(average)
        largest_js = js_array(largest)

        # Shade plugin defined as a named global so it survives JSON.parse/stringify
        # when the modal re-creates the chart from the stored config.
        shade_plugin_var = f"shadePlugin_{chart_id}"
        shade_plugin_def = f"""
const {shade_plugin_var} = {{
  id: 'shadeRegions_{chart_id}',
  beforeDraw(chart) {{
    const {{ctx, chartArea, scales}} = chart;
    if (!chartArea) return;
    const xScale = scales.x;
    const baselineEnd = {tidx - 1};
    const targetStart = {tidx};
    if (baselineEnd >= 0) {{
      const x0 = xScale.getPixelForValue(0);
      const x1 = xScale.getPixelForValue(baselineEnd);
      ctx.save();
      ctx.fillStyle = 'rgba(200,200,200,0.25)';
      ctx.fillRect(x0 - (x1-x0)/2, chartArea.top, (x1-x0) + (x1-x0)/2, chartArea.height);
      ctx.restore();
    }}
    const targetCount = chart.data.labels.length - targetStart;
    if (targetCount > 0) {{
      const xt0 = xScale.getPixelForValue(targetStart);
      const xt1 = xScale.getPixelForValue(chart.data.labels.length - 1);
      const step = (chart.data.labels.length > 1) ? (xt1 - xScale.getPixelForValue(0)) / (chart.data.labels.length - 1) : 0;
      ctx.save();
      ctx.fillStyle = 'rgba(255,165,0,0.10)';
      ctx.fillRect(xt0 - step/2, chartArea.top, (xt1 - xt0) + step, chartArea.height);
      ctx.restore();
    }}
  }}
}};"""

        js_blocks.append(f"""
(function() {{
  {shade_plugin_def}
  const ctx_{chart_id} = document.getElementById('{chart_id}').getContext('2d');
  const data_{chart_id} = {{
      labels: {labels_js},
      datasets: [
        {{
          label: 'Smallest',
          data: {smallest_js},
          borderColor: '{COLORS["smallest"]["border"]}',
          backgroundColor: '{COLORS["smallest"]["bg"]}',
          pointRadius: 4, pointHoverRadius: 6, tension: 0.1, spanGaps: true,
        }},
        {{
          label: 'Average',
          data: {average_js},
          borderColor: '{COLORS["average"]["border"]}',
          backgroundColor: '{COLORS["average"]["bg"]}',
          pointRadius: 4, pointHoverRadius: 6, tension: 0.1, spanGaps: true,
        }},
        {{
          label: 'Largest',
          data: {largest_js},
          borderColor: '{COLORS["largest"]["border"]}',
          backgroundColor: '{COLORS["largest"]["bg"]}',
          pointRadius: 4, pointHoverRadius: 6, tension: 0.1, spanGaps: true,
        }},
      ]
  }};
  const options_{chart_id} = {{
      responsive: true,
      interaction: {{ mode: 'index', intersect: false }},
      plugins: {{
        legend: {{ position: 'right' }},
        tooltip: {{
          callbacks: {{
            label: function(ctx) {{
              return ctx.dataset.label + ': ' + (ctx.parsed.y !== null ? ctx.parsed.y.toFixed(4) + ' s' : 'N/A');
            }}
          }}
        }}
      }},
      scales: {{
        x: {{ ticks: {{ maxRotation: 60, minRotation: 45, font: {{ size: 10 }} }} }},
        y: {{ title: {{ display: true, text: 'Runtime (s)' }}, beginAtZero: false }}
      }}
  }};
  // store data+options+plugin ref for modal reuse
  chartRegistry['{chart_id}'] = {{ data: data_{chart_id}, options: options_{chart_id}, plugin: {shade_plugin_var} }};
  new Chart(ctx_{chart_id}, {{ type: 'line', plugins: [{shade_plugin_var}], data: data_{chart_id}, options: options_{chart_id} }});
}})();
""")

    return ''.join(html_parts) + '</div>\n', '\n'.join(js_blocks)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description='Generate performance delta HTML for a CAPI release')
    parser.add_argument('version', help='CAPI release version to check, e.g. 1.251.0')
    parser.add_argument('--output', '-o', default=None, help='Output HTML file (default: /tmp/capi-<version>-perf-delta.html)')
    parser.add_argument('--threshold', type=float, default=CHANGE_THRESHOLD,
                        help=f'Change threshold as fraction (default: {CHANGE_THRESHOLD} = 25%%)')
    parser.add_argument('--baseline-runs', type=int, default=BASELINE_RUNS,
                        help=f'Number of baseline runs before the release (default: {BASELINE_RUNS})')
    args = parser.parse_args()

    target_version = args.version.strip()
    output_file = args.output or f"/tmp/capi-{target_version}-perf-delta.html"

    print(f"Checking CAPI release: {target_version}")
    print(f"Change threshold: {args.threshold*100:.0f}%  |  Baseline runs: {args.baseline_runs}")
    print(f"Output will be saved to: {output_file}")

    all_html = []
    all_js = []

    for db_type in DB_TYPES:
        print(f"\n--- {db_type} ---")
        records = load_json_results(db_type)
        if not records:
            print(f"  No records found for {db_type}, skipping.")
            all_html.append(f'<div class="column"><h2>DB: {db_type}</h2>\n<p class="no-changes">No result files found.</p>\n</div>')
            continue

        print(f"  Loaded {len(records)} result files")

        series = collect_endpoint_series(records)
        print(f"  Found {len(series)} endpoints")

        changed = find_changed_endpoints(series, target_version,
                                         baseline_runs=args.baseline_runs,
                                         threshold=args.threshold)
        print(f"  Changed endpoints: {len(changed)}")
        for ep, info in sorted(changed.items(), key=lambda x: -abs(x[1]['change'])):
            pct = info['change'] * 100
            sign = '+' if pct > 0 else ''
            direction_label = f"[{info['direction']}]" if info['direction'] == 'flappy' else ''
            print(f"    {sign}{pct:.1f}%  {direction_label}  {ep}")

        section_html, section_js = build_db_section(db_type, changed, args.threshold)
        all_html.append(section_html)
        all_js.append(section_js)

    body = '\n'.join(all_html)
    scripts = '\n'.join(all_js)

    html = HTML_TEMPLATE.format(
        version=target_version,
        chartjs=CHART_JS_CDN,
        baseline=args.baseline_runs,
        threshold=int(args.threshold * 100),
        body=body,
        scripts=scripts,
    )

    with open(output_file, 'w') as f:
        f.write(html)

    print(f"\nOutput written to: {output_file}")

    import webbrowser
    webbrowser.open(f"file://{os.path.abspath(output_file)}")


if __name__ == '__main__':
    main()
