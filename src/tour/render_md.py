"""Markdown renderer for generated tours.

Reproduces the user-readable format of the empirical walks at
``Docs/tour-builder/empirical-tours/01-place-des-vosges.md`` and
``02-ile-de-la-cite-notre-dame.md``: header → per-stop sections →
sentence-per-line with bold ``[SOURCE]`` attributions → footer with
validation summary + "what to look for" hints.

Pure function on a Script; no Neo4j, no LLM. Used by the
``scripts/tour_build.py`` harness and the ``/tour-build`` skill.
"""

from __future__ import annotations

from .contract import BeatSequence, Script, Sentence


def render_markdown(
    script: Script,
    *,
    cost_usd: float | None = None,
    haiku_input_tokens: int | None = None,
    haiku_output_tokens: int | None = None,
    wall_clock_seconds: float | None = None,
    beat_sequence: BeatSequence | None = None,
    tourability=None,
) -> str:
    """Render a Script + telemetry into the empirical-walks markdown format.

    Phase 6 added the optional ``tourability`` arg: when a YELLOW
    assessment is passed, a warning banner is prepended at the top so
    the user sees the thin-tour caveat before the script.
    """
    sub_lookup = _build_sub_lookup(beat_sequence)

    out: list[str] = []
    out.append(
        _header(script, cost_usd, haiku_input_tokens, haiku_output_tokens, wall_clock_seconds)
    )
    if tourability is not None and tourability.status == "YELLOW":
        out.append("")
        out.append(_yellow_banner(tourability, script.inputs.lenses))
    out.append("")
    out.append("---")
    out.append("")

    grouped = _group_by_stop(script.script)
    for stop_idx, sentences in grouped.items():
        if stop_idx >= len(script.selected_pois):
            heading = "## CLOSE"
        else:
            poi = script.selected_pois[stop_idx]
            heading = f"## STOP {stop_idx + 1} — {poi.name}"
        out.append(heading)
        out.append("")
        out.extend(_render_stop_block(sentences, sub_lookup))
        out.append("")

    out.append("---")
    out.append("")
    out.append(_footer(script, sub_lookup))
    return "\n".join(out).rstrip() + "\n"


def _header(
    script: Script,
    cost_usd: float | None,
    haiku_in: int | None,
    haiku_out: int | None,
    wall_clock_s: float | None,
) -> str:
    inp = script.inputs
    lat, lng = inp.start
    parts = [
        f"# Generated Tour — {inp.start_label or 'unnamed start'}",
        "",
        f"**Generated at:** {script.generated_at}",
        f"**City:** {inp.city_slug}",
        f"**Start:** ({lat:.5f}, {lng:.5f}){' — ' + inp.start_label if inp.start_label else ''}",
        f"**Duration target:** {inp.duration_min} min · **Round-trip:** {inp.round_trip}",
    ]
    if inp.lenses:
        parts.append(f"**Lens bias:** {', '.join(inp.lenses)}")
    if inp.theme_hint:
        parts.append(f"**Theme hint:** {inp.theme_hint}")
    parts.extend(
        [
            "",
            f"**Total audio time:** {script.total_audio_seconds // 60} min "
            f"({script.total_audio_seconds} s)",
            f"**Total walk time:** {script.total_walking_seconds // 60} min "
            f"({script.total_walking_seconds} s)",
            f"**Total walk distance:** {script.total_walk_distance_m} m",
            f"**Planned total:** {script.total_planned_seconds // 60} min "
            f"(err-short of stated {inp.duration_min} min)",
        ]
    )
    if cost_usd is not None:
        parts.append(f"**Haiku cost (this tour):** ${cost_usd:.5f}")
    if haiku_in is not None and haiku_out is not None:
        parts.append(f"**Haiku tokens:** {haiku_in} in + {haiku_out} out")
    if wall_clock_s is not None:
        parts.append(f"**Wall-clock:** {wall_clock_s:.1f} s")
    parts.append("")
    parts.append("**Selected POIs (in walk order):**")
    parts.append("")
    for i, poi in enumerate(script.selected_pois, 1):
        parts.append(
            f"  {i}. {poi.name} - tier {poi.tier} "
            f"- {len(poi.beat_ids)} beats - area={poi.area or '-'}"
        )
    return "\n".join(parts)


def _group_by_stop(sentences: tuple[Sentence, ...]) -> dict[int, list[Sentence]]:
    groups: dict[int, list[Sentence]] = {}
    for s in sentences:
        groups.setdefault(s.stop_idx, []).append(s)
    return groups


def stop_narration_text(script: Script) -> dict[int, str]:
    """Per-stop spoken narration: each stop's sentences joined in order.

    Groups ``script.script`` by ``stop_idx`` (cold-open, transit glue, beat
    sentences and closing all included) and joins each stop's sentence texts
    with a single space — the text that becomes one audio file per stop (M0b
    discards this today; Phase 1 wires it to TTS). Pure: no DB, no audio.
    Empty script → ``{}``.
    """
    grouped = _group_by_stop(script.script)
    return {idx: " ".join(s.text for s in sents) for idx, sents in grouped.items()}


def _render_stop_block(
    sentences: list[Sentence],
    sub_lookup: dict[str, tuple[str | None, str | None]],
) -> list[str]:
    """One sentence per line; sentences with the same sub-bucket share a sub-heading.

    The sub-bucket comes from the sub_location or trigger_address of the
    cited beat. Glue sentences attach to the active sub-bucket.
    """
    out: list[str] = []
    current_sub: tuple[str | None, str | None] | None = None

    for sent in sentences:
        sub_key: tuple[str | None, str | None] = (None, None)
        if sent.source_type == "beat":
            sub_key = sub_lookup.get(sent.source_id, (None, None))

        # Sub-headings only emitted for non-empty buckets, when changed,
        # and only for beat-typed sentences (glue inherits the active bucket).
        if sent.source_type == "beat" and sub_key != current_sub and any(sub_key):
            current_sub = sub_key
            label = _format_sub_label(sub_key)
            out.append(f"### {label}")
            out.append("")
        elif sent.source_type == "beat" and sub_key != current_sub and not any(sub_key):
            # Reset to "no sub-bucket" but don't emit a heading.
            current_sub = sub_key

        attribution = _format_attribution(sent)
        out.append(f"{sent.text} **{attribution}**")
        out.append("")
        if sent.source_id == "SYNTHESIZED_OPENER":
            out.append(
                "> **Note:** this tour stop has no canonical "
                "`stop_orientation` beat in the corpus; opener was "
                "synthesized from physical_cues + pronunciation. Quality "
                "gradient — see post-launch backlog item 4."
            )
            out.append("")
    return out


def _format_attribution(sent: Sentence) -> str:
    if sent.source_type == "beat":
        return f"[BEAT:{sent.source_id[:8]}]"
    # glue / arith / synthesized — emit the label verbatim
    return f"[{sent.source_id}]"


def _format_sub_label(sub_key: tuple[str | None, str | None]) -> str:
    sub_loc, trig = sub_key
    if sub_loc and trig:
        return f"{sub_loc} · {trig}"
    return sub_loc or trig or ""


def _build_sub_lookup(
    beat_sequence: BeatSequence | None,
) -> dict[str, tuple[str | None, str | None]]:
    """beat_id → (sub_location, trigger_address) so render can group sentences."""
    out: dict[str, tuple[str | None, str | None]] = {}
    if beat_sequence is None:
        return out
    for plan in beat_sequence.poi_beats:
        for beat in plan.beats:
            out[beat.id] = (beat.sub_location, beat.trigger_address)
    return out


def _yellow_banner(tourability, lenses: list[str] | None = None) -> str:
    """Top-of-tour warning when density.assess returned YELLOW."""
    fill_pct = round(tourability.fill_ratio * 100)
    lines = [
        f"> **⚠ THIN TOUR (YELLOW) — {fill_pct}% audio fill.**",
        "> This tour ran below the empirical 70-80% audio-fill bar; expect "
        "long stretches of silence between stops.",
    ]
    # Lens-specific disclosure: two tourists at the same start see the SAME
    # overall fill, so tell each how much of it matches THEIR interest.
    if lenses and tourability.on_lens_fill_ratio is not None:
        on_lens_pct = round(tourability.on_lens_fill_ratio * 100)
        lens_label = "/".join(lenses)
        lines.append(
            f"> For your interest ({lens_label}), only {on_lens_pct}% of the reachable "
            "audio is on-theme — the rest is other subjects."
        )
    if tourability.max_supportable_duration_min:
        lines.append(
            f"> Consider {tourability.max_supportable_duration_min}-min instead "
            "for richer content at this start point."
        )
    if tourability.round_trip and tourability.one_way_alternative_destination:
        lines.append(
            f"> Or try a one-way ending at {tourability.one_way_alternative_destination!r}."
        )
    return "\n".join(lines)


def _footer(
    script: Script,
    sub_lookup: dict[str, tuple[str | None, str | None]],
) -> str:
    rep = script.validation
    lines = [
        "## Validation summary",
        "",
        f"- Untraceable sentences: **{len(rep.untraceable_sentences)}** (gate: 0)",
        f"- Forbidden phrase hits: **{len(rep.forbidden_phrase_hits)}** (gate: 0)",
        f"- Validation passed: **{rep.passed}**",
    ]
    if rep.untraceable_sentences:
        lines.append("")
        lines.append("**Untraceable sentences (audit):**")
        for s in rep.untraceable_sentences[:10]:
            lines.append(f"  - {s.text!r} (source_id={s.source_id})")
    if rep.forbidden_phrase_hits:
        lines.append("")
        lines.append("**Forbidden phrase hits:**")
        for s, label in rep.forbidden_phrase_hits[:10]:
            lines.append(f"  - {label}: {s.text!r}")

    quality = _quality_hints(script, sub_lookup)
    if quality:
        lines.append("")
        lines.append("## What to look for when auditing")
        lines.append("")
        lines.extend(f"- {h}" for h in quality)

    if script.lens_coverage:
        lines.append("")
        lines.append("## Lens coverage")
        lines.append("")
        for lens, count in sorted(script.lens_coverage.items(), key=lambda kv: (-kv[1], kv[0])):
            lines.append(f"  - {lens}: {count}")

    return "\n".join(lines)


def _quality_hints(
    script: Script,
    sub_lookup: dict[str, tuple[str | None, str | None]],
) -> list[str]:
    hints: list[str] = []

    # Sparse anchors: tier-5 with <3 beats, tier-4 with <2.
    for poi in script.selected_pois:
        if poi.tier == 5 and len(poi.beat_ids) < 3:
            hints.append(
                f"{poi.name} is tier-5 but the tour landed only "
                f"{len(poi.beat_ids)} beats here — content density is thin."
            )
        elif poi.tier in (3, 4) and len(poi.beat_ids) < 2:
            hints.append(
                f"{poi.name} (tier {poi.tier}) carries only "
                f"{len(poi.beat_ids)} beats in this tour — likely a sparse anchor."
            )

    # SYNTHESIZED_OPENER fired
    if any(s.source_id == "SYNTHESIZED_OPENER" for s in script.script):
        hints.append(
            "Cold open used SYNTHESIZED_OPENER — the first stop has no "
            "canonical `stop_orientation` beat in the corpus. Expect a "
            "flatter cold-open feel than the Pariswalks gold standard "
            "(see backlog item 4 for the gap-fill plan)."
        )

    # Forbidden / untraceable already surfaced in the validation summary;
    # only mention as an audit hint if non-zero.
    if script.validation.untraceable_sentences:
        hints.append(
            "Untraceable sentences present — generation produced text "
            "that does not trace to a known beat or glue label. This "
            "should be 0 for a launch-ready tour."
        )

    if not script.selected_pois:
        hints.append(
            "No POIs selected — the start point may be outside the "
            "Paris corpus envelope, or the duration is too short to "
            "reach any reachable POI."
        )

    return hints


__all__ = ["render_markdown"]
