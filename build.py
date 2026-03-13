"""
build.py — Reads markdown posts from /posts, converts them to HTML,
and injects them into the template to produce the final index.html.

Dependencies: markdown, pyyaml
Install with:  pip install markdown pyyaml
"""

import os
import json
import yaml
import markdown
from datetime import datetime


# ---------------------------------------------------------------------------
# Configuration — paths relative to this script's location
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
POSTS_DIR = os.path.join(BASE_DIR, "posts")
TEMPLATE_PATH = os.path.join(BASE_DIR, "templates", "base.html")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")

# Spanish month abbreviations for date formatting
MONTHS_ES = {
    1: "ene", 2: "feb", 3: "mar", 4: "abr",
    5: "may", 6: "jun", 7: "jul", 8: "ago",
    9: "sep", 10: "oct", 11: "nov", 12: "dic",
}


def parse_post(filepath):
    """
    Reads a markdown file and returns a dict with its metadata and HTML body.

    Expected file format:
        ---
        title: "Post title"
        date: 2026-03-12
        excerpt: "Short description."
        ---

        Markdown content here...

    The --- blocks are called "frontmatter" (YAML metadata).
    Everything after the second --- is the post body in markdown.
    """
    with open(filepath, "r", encoding="utf-8") as f:
        raw = f.read()

    # Split on the frontmatter delimiters
    # raw.split("---") gives: ['', 'frontmatter content', 'body content']
    parts = raw.split("---", 2)
    if len(parts) < 3:
        raise ValueError(f"Invalid frontmatter in {filepath}")

    # Parse the YAML frontmatter into a Python dict
    meta = yaml.safe_load(parts[1])

    # Convert the markdown body to HTML
    body_md = parts[2].strip()
    body_html = markdown.markdown(body_md, extensions=['tables', 'fenced_code'])

    # Format the date in Spanish (e.g., "12 mar 2026")
    # The YAML parser gives us a datetime.date object from "2026-03-12"
    date_obj = meta["date"]
    if isinstance(date_obj, str):
        date_obj = datetime.strptime(date_obj, "%Y-%m-%d").date()

    date_display = f"{date_obj.day} {MONTHS_ES[date_obj.month]} {date_obj.year}"

    return {
        "title": meta["title"],
        "date": date_display,
        "date_sort": date_obj.isoformat(),  # keep ISO format for sorting
        "excerpt": meta["excerpt"],
        "body": body_html,
    }


def collect_posts():
    """
    Scans the posts/ directory for .md files, parses each one,
    and returns them sorted by date (newest first).
    """
    posts = []

    for filename in os.listdir(POSTS_DIR):
        if not filename.endswith(".md"):
            continue
        filepath = os.path.join(POSTS_DIR, filename)
        post = parse_post(filepath)
        posts.append(post)
        print(f"  Parsed: {filename} → \"{post['title']}\"")

    # Sort by date descending (newest first)
    posts.sort(key=lambda p: p["date_sort"], reverse=True)

    # Remove the sort key — the frontend doesn't need it
    for p in posts:
        del p["date_sort"]

    return posts


def build_site():
    """
    Main build function:
    1. Collect and parse all posts
    2. Read the HTML template
    3. Inject the posts data as JSON
    4. Write the final index.html to output/
    """
    print("Building site...")
    print()

    # Step 1: Parse all markdown posts
    print("Parsing posts:")
    posts = collect_posts()
    print(f"\n  Found {len(posts)} post(s)")

    # Step 2: Read the template
    with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
        template = f.read()

    # Step 3: Convert posts to JSON and inject into template
    # json.dumps handles escaping quotes, special characters, etc.
    posts_json = json.dumps(posts, ensure_ascii=False, indent=2)
    html = template.replace("__POSTS_DATA__", posts_json)

    # Step 4: Write the output
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    output_path = os.path.join(OUTPUT_DIR, "index.html")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"\n  Output: {output_path}")
    print("  Done!")


if __name__ == "__main__":
    build_site()
