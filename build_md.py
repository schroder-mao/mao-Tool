import json
import re
import sys
from pathlib import Path


def slug(text):
    text = text.lower()
    for a, b in [("à","a"),("â","a"),("ä","a"),("é","e"),("è","e"),("ê","e"),
                 ("ë","e"),("î","i"),("ï","i"),("ô","o"),("ö","o"),("ù","u"),
                 ("û","u"),("ü","u"),("ç","c")]:
        text = text.replace(a, b)
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    data = json.loads(Path("tools.json").read_text(encoding="utf-8"))
    lines = [
        "# mao-Tool",
        "",
        "Site : https://schroder-mao.github.io/mao-Tool/",
        "",
        f"{len(data['tools'])} outils, {len(data['categories'])} catégories.",
        "",
        "## Sommaire",
    ]
    for cat in data["categories"]:
        count = sum(1 for t in data["tools"] if t["category"] == cat["id"])
        if count == 0:
            continue
        anchor = slug(cat["name"])
        lines.append(f"- [{cat['name']}](#{anchor}) ({count})")

    lines.append("")

    for cat in data["categories"]:
        tools = [t for t in data["tools"] if t["category"] == cat["id"]]
        if not tools:
            continue
        lines.append(f"## {cat['name']}")
        lines.append("")
        for t in sorted(tools, key=lambda x: x["name"].lower()):
            desc = t.get("description", "").strip()
            suffix = f" — {desc}" if desc else ""
            lines.append(f"- [{t['name']}]({t['url']}){suffix}")
        lines.append("")

    Path("maotool.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"maotool.md régénéré : {len(data['tools'])} outils, {len(data['categories'])} catégories")


if __name__ == "__main__":
    main()
