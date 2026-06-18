#!/usr/bin/env python3
"""
Split index.html into modular JS files + a slim HTML shell.
This is a careful refactoring to preserve all functionality.
"""

import re
import os

INPUT = "/Users/henryjin/PycharmProjects/AgentHub_/AgentHub-my flicker/index.html"
OUTPUT_DIR = "/Users/henryjin/PycharmProjects/AgentHub_/AgentHub-my flicker/js"

with open(INPUT, "r", encoding="utf-8") as f:
    content = f.read()

lines = content.split("\n")

# Helper to find line ranges
def find_line_range(start_patterns, end_patterns=None, single_match=False, start_offset=0):
    """Find line ranges matching start/end patterns."""
    results = []
    start = None
    for i, line in enumerate(lines[start_offset:], start=start_offset):
        if start is None:
            for p in start_patterns:
                if p in line:
                    start = i
                    if single_match:
                        break
        else:
            if end_patterns:
                for p in end_patterns:
                    if p in line:
                        results.append((start, i + 1))
                        start = None
                        break
            else:
                results.append((start, i + 1))
                start = None
                break
    return results

# We'll split by sections based on the structural analysis
# Let's define the sections carefully:

sections = []

# Section 1: HTML Head + Tailwind config + CSS (lines 1-351)
sections.append(("html_head", 0, 351))

# Section 2: Utility Functions (lines 352-454)
sections.append(("utils", 351, 454))

# Section 3: Global State & Schema (lines 455-1091)
sections.append(("state", 454, 1091))

# Section 4: Main Render & Dashboard (lines 1092-1350)
sections.append(("dashboard", 1091, 1350))

# Section 5: Mission Workspace - Chat (lines 1351-2430)
sections.append(("chat", 1350, 2430))

# Section 6: Right Editor Panel (lines 2499-2930)
sections.append(("editor_panel", 2498, 2930))

# Section 7: Chat Input & Modals (lines 2931-3981)
sections.append(("chat_modals", 2930, 3981))

# Section 8: Agents / Skills / Settings Pages (lines 3983-4895)
sections.append(("pages", 3982, 4895))

# Section 9: Agent Detail (lines 4897-6475)
sections.append(("agent_detail", 4896, 6475))

# Section 10: Skill Detail (lines 6477-6787)
sections.append(("skill_detail", 6476, 6787))

# Section 11: Version Diff (lines 6789-6843)
sections.append(("version_diff", 6788, 6843))

# Section 12: Knowledge Base (lines 6845-8324)
sections.append(("knowledge", 6844, 8324))

# Section 13: Settings & Quick Run (lines 8326-8413)
sections.append(("settings_quickrun", 8325, 8413))

# Section 14: Chat Interactions (lines 8415-9055)
sections.append(("chat_interactions", 8414, 9055))

# Section 15: SSE Stream (lines 9057-9079)
sections.append(("sse", 9056, 9079))

# Section 16: WebSocket (lines 9081-9242)
sections.append(("websocket", 9080, 9242))

# Section 17: Auth & API (lines 9244-9805)
sections.append(("api_auth", 9243, 9805))

# Now let's create the JS files
# We need to be careful about: the first section is HTML, the rest are JS

# For HTML, we keep it as the shell
# For JS, we need to wrap in <script> in the HTML or keep as pure JS

# Strategy: create JS files, then modify HTML to load them

js_files = {
    "utils.js": "utils",
    "state.js": "state",
    "dashboard.js": "dashboard",
    "chat.js": "chat",
    "editor_panel.js": "editor_panel",
    "chat_modals.js": "chat_modals",
    "pages.js": "pages",
    "agent_detail.js": "agent_detail",
    "skill_detail.js": "skill_detail",
    "version_diff.js": "version_diff",
    "knowledge.js": "knowledge",
    "settings_quickrun.js": "settings_quickrun",
    "chat_interactions.js": "chat_interactions",
    "sse.js": "sse",
    "websocket.js": "websocket",
    "api_auth.js": "api_auth",
}

# Write JS files
for filename, section_name in js_files.items():
    for name, start, end in sections:
        if name == section_name:
            section_lines = lines[start:end]
            # Remove HTML wrapper tags if present
            # These sections are inside <script> originally
            # We need to extract just the JS content
            js_content = "\n".join(section_lines)
            # If it's wrapped in <script>...</script>, extract the inner content
            js_content = re.sub(r'^\s*<script[^>]*>\s*', '', js_content)
            js_content = re.sub(r'\s*</script>\s*$', '', js_content)
            
            filepath = os.path.join(OUTPUT_DIR, filename)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(js_content)
            print(f"Written {filename} ({len(section_lines)} lines)")
            break

print("Done splitting JS files.")
print("Now creating new HTML shell...")

# Create the new HTML shell
# We need to keep: HTML head, and at the end load all JS files

html_lines = lines[0:351]  # Head section

# Add script tags to load JS files
script_tags = []
for filename in js_files.keys():
    script_tags.append(f'  <script src="js/{filename}"></script>')

# Create final HTML
final_html = "\n".join(html_lines)
# Remove the closing </head> and </html> tags if they are in the head section
# Actually the original file ends at line 351 with </script></head><body>...
# We need to reconstruct properly

# Let's read the original lines more carefully
print("Original line 350-351:")
print(lines[349])
print(lines[350])

# The original file structure is:
# Lines 1-351: head + tailwind config + CSS + some initial scripts
# Then line 352 onwards is <script> tag with all the JS
# Then at the end </script></body></html>

# Let's verify
print("Original line -5 to -1:")
for i in range(-5, 0):
    print(f"{len(lines)+i}: {lines[i]}")

# So we need to create a new HTML file that:
# 1. Keeps everything up to line 351 (before the first <script> of app logic)
# 2. Replaces the inline <script> with script src tags
# 3. Keeps the closing </body></html>

# The first <script> in the app logic starts at line 352
# Let's verify line 352
print("\nLine 352:")
print(lines[351])

# We need to extract the HTML shell correctly
# Let's find where the main app script starts
# It should be after the tailwind config and CSS

# Actually, looking at the analysis:
# Lines 1-351: HTML head with all external scripts, tailwind config, CSS
# Line 352: starts with <script> (the main app logic)
# Let's verify

print("\nLine 352 content:")
print(lines[351][:80])

# The end of the file:
# Line -2: </script>
# Line -1: </body></html>

# So we need to build:
# 1. Lines 1-351 (head + closing </head> + <body>)
# 2. Wait, line 351 might be the start of the first <script> tag

# Let's check more carefully
for i in range(345, 360):
    print(f"{i+1}: {lines[i][:60]}")

# Based on this, I'll create a proper HTML shell
# Let's just take lines 1-351 and add script src tags, then </body></html>

# Actually, the line numbers in the analysis are 1-indexed
# So line 1 in analysis = lines[0] in Python

# The first script tag with app logic starts at line 352
# So we need lines[0:351] for the HTML before the app logic
# And we need to add </body></html> at the end

shell_lines = lines[0:351]  # 0-350 = lines 1-351

# Check if line 351 is indeed before the app script
print("\nLast line of shell:")
print(lines[350])

# Let's also check what comes after
print("\nFirst line after shell:")
print(lines[351])

# Now create the new HTML
new_html_lines = []
new_html_lines.extend(lines[0:351])
new_html_lines.append("")
new_html_lines.append("  <!-- 加载模块化 JS -->")
for filename in js_files.keys():
    new_html_lines.append(f'  <script src="js/{filename}"></script>')
new_html_lines.append("")
new_html_lines.append("</body>")
new_html_lines.append("</html>")

new_html = "\n".join(new_html_lines)

# Save new HTML
new_html_path = "/Users/henryjin/PycharmProjects/AgentHub_/AgentHub-my flicker/index.html"
# Backup original
import shutil
shutil.copy(new_html_path, new_html_path + ".backup")
with open(new_html_path, "w", encoding="utf-8") as f:
    f.write(new_html)

print(f"\nNew HTML shell written to {new_html_path}")
print(f"Original backed up to {new_html_path}.backup")
print(f"JS files written to {OUTPUT_DIR}")
