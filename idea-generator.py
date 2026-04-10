#!/usr/bin/env python3
"""
idea-generator.py — Kids Business Fair Idea Expander
=====================================================
Uses the Anthropic API (Claude) to generate new business ideas and merge
them into ideas.json. Run this any time you want to grow the idea library.

Usage:
  python idea-generator.py                  # adds 20 new ideas (default)
  python idea-generator.py --count 50       # adds 50 new ideas
  python idea-generator.py --replace        # replaces ideas.json from scratch
  python idea-generator.py --dry-run        # prints ideas without saving

Requirements:
  pip install anthropic
  export ANTHROPIC_API_KEY="your-key-here"
"""

import argparse
import json
import os
import sys
import re

try:
    import anthropic
except ImportError:
    print("Error: anthropic package not installed. Run: pip install anthropic")
    sys.exit(1)

# ── Configuration ────────────────────────────────────────────────────────────

IDEAS_FILE = os.path.join(os.path.dirname(__file__), "ideas.json")

# All valid tags — must match PASSION_TAGS / SKILL_TAGS / MARKET_TAGS in fair-builder.html
VALID_TAGS = [
    "art", "drawing", "crafting", "handmade", "plants", "growing",
    "animals", "music", "custom", "tech", "digital", "sports",
    "activities", "organizing", "helping", "sewing", "nature",
    "accessories", "building", "gifts", "kids", "cheap",
]

VALID_INVEST = ["low", "mid", "high"]
VALID_TIME   = ["quick", "med", "long"]

# ── Claude prompt ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are helping build a library of business ideas for kids ages 8–14 who are planning a table at a school fair or community market.

Each idea must follow these rules:
- NO food or drink (no lemonade, baked goods, snacks, candy, etc.)
- Must be something a kid can realistically make or sell at a fair table
- Must be age-appropriate and safe
- Must be specific enough to be actionable (not just "art" but "Watercolor Animal Portraits")

You will output a JSON array of idea objects. Each object has exactly these fields:
{
  "i": "<single emoji that represents the idea>",
  "n": "<short name, 2-5 words, Title Case>",
  "w": "<one sentence: why it works well at a fair, max 15 words>",
  "invest": "<one of: low | mid | high>",
  "time": "<one of: quick | med | long>",
  "tags": ["<tags from the allowed list only>"]
}

invest guide:
- low  = materials cost under $5 total
- mid  = materials cost $5–$20
- high = materials cost over $20

time guide:
- quick = each item takes under 15 minutes to make
- med   = each item takes 15–60 minutes
- long  = each item takes over an hour

Allowed tags (use only these, pick 2–5 per idea):
art, drawing, crafting, handmade, plants, growing, animals, music, custom, tech,
digital, sports, activities, organizing, helping, sewing, nature, accessories,
building, gifts, kids, cheap

Output ONLY the raw JSON array — no explanation, no markdown, no code fences."""

# ── Helpers ───────────────────────────────────────────────────────────────────

def load_existing() -> list[dict]:
    if os.path.exists(IDEAS_FILE):
        with open(IDEAS_FILE, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
                if isinstance(data, list):
                    return data
            except json.JSONDecodeError:
                print("Warning: ideas.json is malformed — treating as empty.")
    return []


def save_ideas(ideas: list[dict]) -> None:
    with open(IDEAS_FILE, "w", encoding="utf-8") as f:
        json.dump(ideas, f, ensure_ascii=False, indent=2)
    print(f"✅ Saved {len(ideas)} ideas to ideas.json")


def validate_idea(idea: dict, existing_names: set[str]) -> tuple[bool, str]:
    """Returns (ok, reason). Filters out bad or duplicate ideas."""
    if not isinstance(idea, dict):
        return False, "not a dict"
    for field in ("i", "n", "w", "invest", "time", "tags"):
        if field not in idea:
            return False, f"missing field '{field}'"
    if idea["invest"] not in VALID_INVEST:
        return False, f"bad invest '{idea['invest']}'"
    if idea["time"] not in VALID_TIME:
        return False, f"bad time '{idea['time']}'"
    if not isinstance(idea["tags"], list) or len(idea["tags"]) == 0:
        return False, "tags must be a non-empty list"
    bad_tags = [t for t in idea["tags"] if t not in VALID_TAGS]
    if bad_tags:
        return False, f"invalid tags: {bad_tags}"
    name = idea["n"].strip()
    if name.lower() in existing_names:
        return False, f"duplicate name '{name}'"
    # Quick food/drink filter
    food_words = ["lemon", "cookie", "cake", "bread", "muffin", "cupcake",
                  "brownie", "granola", "snack", "drink", "juice", "candy",
                  "chocolate", "bake", "baked", "food", "treat", "beverage",
                  "popcorn", "pretzel", "sandwich", "pizza"]
    combined = (name + " " + idea["w"]).lower()
    for word in food_words:
        if word in combined:
            return False, f"contains food/drink word '{word}'"
    return True, ""


def parse_json_from_response(text: str) -> list[dict]:
    """Extract JSON array from Claude's response, even if it has extra text."""
    # Try raw parse first
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass
    # Try to find a JSON array inside the text
    match = re.search(r'\[[\s\S]*\]', text)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    return []


def generate_ideas(count: int, existing_names: set[str]) -> list[dict]:
    """Ask Claude to generate `count` fresh, unique ideas."""
    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env

    user_prompt = (
        f"Generate exactly {count} unique business ideas for kids at a fair.\n"
        f"Do NOT include any of these ideas (already in the library): "
        f"{', '.join(sorted(existing_names)) if existing_names else 'none yet'}.\n"
        f"Output a JSON array of {count} objects."
    )

    print(f"🤖 Asking Claude for {count} new ideas…")

    message = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )

    raw = message.content[0].text
    ideas = parse_json_from_response(raw)

    if not ideas:
        print("❌ Claude returned no parseable JSON. Raw response:")
        print(raw[:500])
        return []

    return ideas


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Expand Julian's business idea library using Claude AI")
    parser.add_argument("--count",   type=int, default=20, help="Number of new ideas to generate (default: 20)")
    parser.add_argument("--replace", action="store_true",  help="Replace ideas.json from scratch instead of merging")
    parser.add_argument("--dry-run", action="store_true",  help="Print ideas without saving to file")
    args = parser.parse_args()

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("Error: ANTHROPIC_API_KEY environment variable is not set.")
        print("Get your key at: https://console.anthropic.com")
        sys.exit(1)

    # Load existing ideas
    existing = [] if args.replace else load_existing()
    existing_names = {idea["n"].lower() for idea in existing}
    print(f"📚 Existing library: {len(existing)} ideas")

    # Generate new ideas
    raw_new = generate_ideas(args.count, existing_names)
    print(f"📥 Claude returned {len(raw_new)} idea candidates")

    # Validate and filter
    accepted = []
    for idea in raw_new:
        ok, reason = validate_idea(idea, existing_names)
        if ok:
            idea["n"] = idea["n"].strip()  # normalize whitespace
            accepted.append(idea)
            existing_names.add(idea["n"].lower())
        else:
            print(f"  ⚠️  Skipped '{idea.get('n','?')}': {reason}")

    print(f"✔️  Accepted {len(accepted)} new ideas after validation")

    if args.dry_run:
        print("\n── Dry run — new ideas (not saved) ──")
        print(json.dumps(accepted, ensure_ascii=False, indent=2))
        return

    if accepted:
        merged = existing + accepted
        save_ideas(merged)
    else:
        print("No new ideas to add.")


if __name__ == "__main__":
    main()
