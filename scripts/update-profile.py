import os
import json
import urllib.request
import urllib.parse
import re
from datetime import datetime, timezone

def fetch_repos_graphql(token):
    query = """
    query {
      viewer {
        repositories(first: 100, isFork: false, ownerAffiliations: OWNER) {
          nodes {
            name
            isPrivate
            languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
              edges {
                size
                node {
                  name
                  color
                }
              }
            }
          }
        }
      }
    }
    """
    req = urllib.request.Request(
        'https://api.github.com/graphql',
        data=json.dumps({'query': query}).encode('utf-8'),
        headers={
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json',
            'User-Agent': 'wuzzstoreservice-profile-updater'
        }
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode('utf-8'))

def calculate_stats(data):
    repos = data['data']['viewer']['repositories']['nodes']
    repo_count = 0
    lang_shares = {}
    lang_colors = {}

    for r in repos:
        edges = r['languages']['edges']
        total_size = sum(e['size'] for e in edges)
        if total_size == 0:
            continue
        repo_count += 1
        for e in edges:
            name = e['node']['name']
            color = e['node']['color'] or '#8b949e'
            lang_colors[name] = color
            fraction = e['size'] / total_size
            lang_shares[name] = lang_shares.get(name, 0.0) + fraction

    results = []
    for name, val in lang_shares.items():
        pct = (val / repo_count) * 100
        results.append((name, pct, lang_colors[name]))

    results.sort(key=lambda x: x[1], reverse=True)
    return results, repo_count

def generate_svg(results, output_path):
    top_languages = [r for r in results if r[1] >= 5.0]
    other_languages = [r for r in results if r[1] < 5.0]
    other_pct = sum(x[1] for x in other_languages)
    
    chart_data = list(top_languages)
    if other_pct > 0:
        chart_data.append(('Other', other_pct, '#8b949e'))

    total_w = 640
    running_x = 20
    stacked_rects = []
    for name, pct, col in chart_data:
        w = round(total_w * (pct / 100))
        stacked_rects.append(f'  <rect x="{running_x}" y="72" width="{w}" height="14" fill="{col}"/>')
        running_x += w

    # Fix total width overflow/underflow on last item
    if stacked_rects:
        diff = (running_x - 20) - total_w
        if diff != 0:
            last_name, last_pct, last_col = chart_data[-1]
            last_w = round(total_w * (last_pct / 100)) - diff
            stacked_rects[-1] = f'  <rect x="{running_x - round(total_w * (last_pct / 100))}" y="72" width="{last_w}" height="14" fill="{last_col}"/>'

    rows_svg = []
    y_pos = 110
    display_rows = list(top_languages)
    if other_pct > 0:
        other_names = " · ".join([x[0] for x in other_languages[:4]])
        if len(other_languages) > 4:
            other_names += " · Other"
        display_rows.append((other_names, other_pct, '#8b949e'))

    for name, pct, col in display_rows:
        bar_w = round(430 * (pct / 100))
        row = f"""    <circle cx="28" cy="{y_pos}" r="5" fill="{col}"/>
    <text x="42" y="{y_pos + 4}" fill="#c9d1d9">{name}</text>
    <text x="620" y="{y_pos + 4}" fill="#8b949e" text-anchor="end">{pct:.1f}%</text>
    <rect x="160" y="{y_pos - 5}" width="430" height="8" rx="4" fill="#21262d"/>
    <rect x="160" y="{y_pos - 5}" width="{bar_w}" height="8" rx="4" fill="{col}"/>"""
        rows_svg.append(row)
        y_pos += 24

    total_h = y_pos + 5
    svg_content = f"""<svg xmlns="http://www.w3.org/2000/svg" width="680" height="{total_h}" viewBox="0 0 680 {total_h}" role="img" aria-label="Language breakdown">
  <rect width="680" height="{total_h}" rx="12" fill="#0d1117"/>
  <text x="20" y="32" fill="#f0f6fc" font-family="Segoe UI, Helvetica, Arial, sans-serif" font-size="16" font-weight="600">Languages · repo-normalized</text>
  <text x="20" y="52" fill="#8b949e" font-family="Segoe UI, Helvetica, Arial, sans-serif" font-size="11">Share per repository (private + public), not raw LOC</text>

  <!-- stacked bar -->
  <rect x="20" y="72" width="640" height="14" rx="7" fill="#21262d"/>
{chr(10).join(stacked_rects)}

  <!-- rows -->
  <g font-family="Segoe UI, Helvetica, Arial, sans-serif" font-size="13">
{chr(10).join(rows_svg)}
  </g>
</svg>
"""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(svg_content)

def update_readme(results, readme_path):
    with open(readme_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Table
    table_lines = ["| Language | Share |", "|---|---:|"]
    for name, pct, _ in results[:6]:
        table_lines.append(f"| **{name}** | **{pct:.1f}%** |")
    other_pct = sum(x[1] for x in results[6:])
    if other_pct > 0:
        table_lines.append(f"| Other | {other_pct:.1f}% |")
    table_str = "\n".join(table_lines)

    # Text Bar Chart
    text_bars = []
    for name, pct, _ in results[:6]:
        bar_len = int(round(pct / 2))
        bar = '█' * bar_len + '░' * (50 - bar_len)
        text_bars.append(f"{name:12} {bar} {pct:5.1f}%")
    text_bar_str = "```text\n" + "\n".join(text_bars) + "\n```"

    # Badges
    badge_map = {
        'Python': ('3572A5', 'white'),
        'JavaScript': ('f1e05a', 'black'),
        'Go': ('00ADD8', 'white'),
        'TypeScript': ('3178C6', 'white'),
        'HTML': ('E34C26', 'white'),
        'Shell': ('89e051', 'black'),
        'CSS': ('663399', 'white')
    }

    badge_lines = []
    for name, pct, col in results[:6]:
        color_hex, logo_col = badge_map.get(name, (col.lstrip('#'), 'white'))
        badge_lines.append(f"[![{name}](https://img.shields.io/badge/{name}-{pct:.1f}%25-{color_hex}?style=flat-square&logo={name.lower()}&logoColor={logo_col})](https://wuzzstoreservice.github.io/#languages)")
    badge_str = "\n".join(badge_lines)

    section = f"""<!-- START_SECTION:languages -->
{table_str}

{text_bar_str}

{badge_str}
<!-- END_SECTION:languages -->"""

    if "<!-- START_SECTION:languages -->" in content:
        pattern = re.compile(r'<!-- START_SECTION:languages -->.*?<!-- END_SECTION:languages -->', re.DOTALL)
        new_content = pattern.sub(section, content)
    else:
        # Replace the existing static language block
        target_start = "| Language | Share |"
        target_end_marker = "---\n\n## Featured projects"
        
        start_idx = content.find(target_start)
        end_idx = content.find(target_end_marker)
        
        if start_idx != -1 and end_idx != -1:
            new_content = content[:start_idx] + section + "\n\n" + content[end_idx:]
        else:
            new_content = content

    with open(readme_path, 'w', encoding='utf-8') as f:
        f.write(new_content)

if __name__ == '__main__':
    token = os.environ.get('GITHUB_TOKEN')
    if not token:
        import subprocess
        token = subprocess.check_output(['gh', 'auth', 'token']).decode('utf-8').strip()
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.dirname(script_dir)
    
    data = fetch_repos_graphql(token)
    results, count = calculate_stats(data)
    print(f"Counted {count} repositories.")
    
    svg_path = os.path.join(repo_root, 'assets', 'languages.svg')
    generate_svg(results, svg_path)
    print(f"{svg_path} updated.")
    
    readme_path = os.path.join(repo_root, 'README.md')
    update_readme(results, readme_path)
    print(f"{readme_path} updated.")
