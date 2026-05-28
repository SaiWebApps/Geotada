#!/usr/bin/env python3
"""Extract final JSON result from each agent's JSONL transcript.

Reads /private/tmp/claude-501/.../tasks/*.output (each is a JSONL transcript
of a sub-agent run) and writes the final assistant message's JSON object
to data/paris/.batch-results/<chunk_id>.json.

Tolerant: skips agents that haven't completed or whose final message can't be
parsed as JSON. Idempotent: re-running re-extracts but doesn't error on partial
success.
"""
from __future__ import annotations
import json
import re
import sys
from pathlib import Path

TASKS_DIR = Path("/private/tmp/claude-501/-Users-adamserblowski-Geotada/95eb2764-84eb-4c80-bcd1-ea00d6544fe5/tasks")
OUT_DIR = Path("data/paris/.batch-results")
OUT_DIR.mkdir(parents=True, exist_ok=True)

AGENT_TO_CHUNK = {
    "a2514d6b570c69139": "chunk-02a-vert-galant-jean-xxiii-rene-viviani",
    "ae4a6265e8ba46ed5": "chunk-02b-cluny-paul-langevin-ecole-normale",
    "a83c0bde1683f1ea8": "chunk-02c-arenes-jardin-des-plantes",
    "a4bf5d6fa8904b5b2": "chunk-03a-luxembourg-delacroix",
    "ac98b0fe43d8f351a": "chunk-03b-boucicaut-clinique-rodin",
    "a57ecb5bfff351e89": "chunk-04a-recamier-champ-de-mars-santiago",
    "a379039e1e0589c60": "chunk-04b-zadkine-atlantique-brassens-montsouris",
    "a28155f00a5876d34": "chunk-05a-bagatelle-balzac",
    "a94bfec7296a77b85": "chunk-05b-tuileries-palais-royal",
    "a760bf0366d2c6696": "chunk-06a-vallee-suisse-vosges-carnavalet",
    "ad9bd477d5d15d294": "chunk-06b-georges-cain-temple",
    "ad8ffffce24f58ecd": "chunk-07a-monceau-vie-romantique-batignolles",
    "a7f77a1a5573a66ee": "chunk-07b-suzanne-buisson-montmartre",
    "a0db220b217d11a2d": "chunk-08a-promenade-plantee-parc-floral",
    "a405d4f29a76942e7": "chunk-08b-maurice-gardette-roquette",
    "a9b8bfa6e2a0644fc": "chunk-08c-buttes-chaumont-pere-lachaise",
}

CODE_FENCE = re.compile(r"```(?:json)?\s*\n(.*?)\n```", re.DOTALL)


def _final_assistant_text(jsonl_path: Path) -> str | None:
    """Return text content of the last assistant message in a JSONL transcript."""
    if not jsonl_path.exists():
        return None
    last_text: str | None = None
    with jsonl_path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            # Try common shapes for assistant message text
            msg = rec.get("message") or rec
            if msg.get("role") != "assistant":
                continue
            content = msg.get("content")
            if isinstance(content, str):
                last_text = content
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        last_text = block.get("text", last_text)
    return last_text


_RESULT_KEYS = ("chunk_id", "beats", "pois", "review_queue", "summary")


def _balanced_objects(text: str):
    """Yield (start, end, parsed_dict) for every balanced top-level `{...}` blob
    in `text` that parses as JSON. Skips nested objects — only top-level."""
    depth = 0
    in_str = False
    esc = False
    start = -1
    for i, c in enumerate(text):
        if esc:
            esc = False
            continue
        if c == '\\':
            esc = True
            continue
        if c == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if c == '{':
            if depth == 0:
                start = i
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0 and start >= 0:
                blob = text[start:i + 1]
                try:
                    yield start, i + 1, json.loads(blob)
                except json.JSONDecodeError:
                    pass


def _extract_json_object(text: str) -> dict | None:
    """Pull the result JSON out of an agent's final message. Tolerates
    surrounding markdown fences, multiple inline `{...}` blocks, etc.

    Strategy: scan all candidate text segments (prefer fenced ```json``` blocks,
    fall back to the whole message), enumerate every balanced top-level object,
    and pick the first one that contains a recognizable result key."""
    candidates: list[str] = []
    for m in CODE_FENCE.finditer(text):
        candidates.append(m.group(1))
    candidates.append(text)  # fallback: scan the whole message

    best: dict | None = None
    best_size = -1
    for candidate in candidates:
        for _, _, obj in _balanced_objects(candidate):
            if not isinstance(obj, dict):
                continue
            if any(k in obj for k in _RESULT_KEYS):
                # Prefer the largest result-shaped object (handles cases where
                # the agent embeds smaller demo objects before the real one).
                size = len(obj)
                if size > best_size:
                    best = obj
                    best_size = size
    return best


def main() -> int:
    saved, missing, malformed = [], [], []
    for agent_id, chunk_id in AGENT_TO_CHUNK.items():
        jsonl = TASKS_DIR / f"{agent_id}.output"
        text = _final_assistant_text(jsonl)
        if text is None:
            missing.append((agent_id, chunk_id))
            continue
        obj = _extract_json_object(text)
        if obj is None:
            malformed.append((agent_id, chunk_id, len(text)))
            # Keep the raw text so we can hand-fix later
            (OUT_DIR / f"{chunk_id}.raw.txt").write_text(text)
            continue
        out_path = OUT_DIR / f"{chunk_id}.json"
        out_path.write_text(json.dumps(obj, indent=2))
        saved.append((chunk_id,
                      len(obj.get("beats") or []),
                      sum(1 for p in (obj.get("pois") or []) if p.get("is_new") or p.get("new_poi"))))

    print(f"saved: {len(saved)}")
    for chunk_id, beats, new_pois in saved:
        print(f"  {chunk_id}: {beats} beats, {new_pois} new POIs")
    print(f"\nmissing transcripts (agent not finished): {len(missing)}")
    for agent_id, chunk_id in missing:
        print(f"  {agent_id} -> {chunk_id}")
    print(f"\nmalformed JSON in final message: {len(malformed)}")
    for agent_id, chunk_id, n in malformed:
        print(f"  {agent_id} -> {chunk_id} ({n} chars saved as .raw.txt)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
