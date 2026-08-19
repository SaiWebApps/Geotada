class ItineraryStop {
  final int sortOrder;
  // ItineraryItem id — addresses this stop for per-stop narration audio
  // (Phase 1). Nullable: legacy/seed trips may not carry it.
  final String? stopId;
  final String poiId;
  final String poiName;
  final double lat;
  final double lng;
  // Null for a stop with no story — a rest (a bench) carries no beat and no
  // audio of its own; the audio key then falls back through stopId (S5.13).
  final String? beatId;
  final String lensName;
  final String lensDisplay;
  final int durationMin;
  final int importanceTier;
  final String startTime;
  final String? scriptBody;
  final String? audioUrl;
  final double? audioDurationSec;
  // M2: encoded polyline of the walking leg INTO this stop; null when the
  // backend's routing fell back to haversine (Valhalla not running).
  final String? transitPolyline;
  // KE: ordered ids of this stop's beats the tour did NOT voice — the
  // "keep exploring here" extras (most-important first). Empty for stops
  // with no overflow and for old trips whose JSON lacks the key.
  final List<String> extraBeatIds;
  // KE: composed "keep exploring here" narration for [extraBeatIds], voiced
  // on demand off the tour's time budget; null until /compose has run.
  final String? extraNarration;
  // Phase 5 S5.10: the planner's own visit for this stop, in seconds — what
  // the phone's re-timing spends here (the longer of this and the narration
  // at the learned listening rate). Falls back to the rounded minutes.
  final int? dwellSeconds;

  const ItineraryStop({
    required this.sortOrder,
    this.stopId,
    required this.poiId,
    required this.poiName,
    required this.lat,
    required this.lng,
    this.beatId,
    required this.lensName,
    required this.lensDisplay,
    required this.durationMin,
    required this.importanceTier,
    required this.startTime,
    this.scriptBody,
    this.audioUrl,
    this.audioDurationSec,
    this.transitPolyline,
    this.extraBeatIds = const [],
    this.extraNarration,
    this.dwellSeconds,
  });

  /// Seconds the plan spends AT this stop (S5.10): the planner's exact visit
  /// when the wire carried it, else the rounded minutes.
  int get plannedVisitSeconds => dwellSeconds ?? durationMin * 60;

  factory ItineraryStop.fromJson(Map<String, dynamic> json) {
    return ItineraryStop(
      sortOrder: json['sort_order'] as int,
      stopId: json['stop_id'] as String?,
      poiId: json['poi_id'] as String,
      poiName: json['poi_name'] as String,
      lat: (json['lat'] as num).toDouble(),
      lng: (json['lng'] as num).toDouble(),
      beatId: json['beat_id'] as String?,
      // M0b: a stop with no lensed beat has null lens fields in the API
      // response; render as empty rather than crash.
      lensName: (json['lens_name'] as String?) ?? '',
      lensDisplay: (json['lens_display'] as String?) ?? '',
      durationMin: json['duration_min'] as int,
      importanceTier: json['importance_tier'] as int,
      startTime: json['start_time'] as String,
      scriptBody: json['script_body'] as String?,
      audioUrl: json['audio_url'] as String?,
      audioDurationSec: (json['audio_duration_sec'] as num?)?.toDouble(),
      transitPolyline: json['transit_polyline'] as String?,
      // KE: tolerate the key being absent (old trips) — default to empty.
      extraBeatIds: ((json['extra_beat_ids'] as List<dynamic>?) ?? const [])
          .map((e) => e as String)
          .toList(),
      extraNarration: json['extra_narration'] as String?,
      dwellSeconds: (json['dwell_seconds'] as num?)?.toInt(),
    );
  }

  Map<String, dynamic> toJson() => {
        'sort_order': sortOrder,
        'stop_id': stopId,
        'poi_id': poiId,
        'poi_name': poiName,
        'lat': lat,
        'lng': lng,
        'beat_id': beatId,
        'lens_name': lensName,
        'lens_display': lensDisplay,
        'duration_min': durationMin,
        'importance_tier': importanceTier,
        'start_time': startTime,
        'script_body': scriptBody,
        'audio_url': audioUrl,
        'audio_duration_sec': audioDurationSec,
        'transit_polyline': transitPolyline,
        'dwell_seconds': dwellSeconds,
        'extra_beat_ids': extraBeatIds,
        'extra_narration': extraNarration,
      };

  ItineraryStop copyWith({
    String? audioUrl,
    double? audioDurationSec,
    String? scriptBody,
  }) {
    return ItineraryStop(
      sortOrder: sortOrder,
      stopId: stopId,
      poiId: poiId,
      poiName: poiName,
      lat: lat,
      lng: lng,
      beatId: beatId,
      lensName: lensName,
      lensDisplay: lensDisplay,
      durationMin: durationMin,
      importanceTier: importanceTier,
      startTime: startTime,
      scriptBody: scriptBody ?? this.scriptBody,
      audioUrl: audioUrl ?? this.audioUrl,
      audioDurationSec: audioDurationSec ?? this.audioDurationSec,
      transitPolyline: transitPolyline,
      extraBeatIds: extraBeatIds,
      extraNarration: extraNarration,
      dwellSeconds: dwellSeconds,
    );
  }
}

// Phase 4 (design §8.1): POST /trips/generate still carries `options` on the
// wire (a list of exactly one; the field stays a list because stored
// pre-Phase-4 trips carry multi-option lists), but the phone neither parses
// nor shows it. The one day's route id is always `{trip_id}-opt1`, so there
// is nothing to choose and nothing to read — fromJson simply ignores the key.
class GeneratedTrip {
  final String tripId;
  final String tripName;
  final String profileId;
  final int totalStops;
  final int totalDurationMin;
  final int anchorCount;
  final int flavourCount;
  final List<ItineraryStop> stops;
  // Everything that quietly went worse while this tour was built — most often
  // that the walking times between stops were estimated rather than measured.
  // Each entry is the plain-English sentence the backend wrote for a human to
  // read (src/tour/degradations.py's `human` register); the machine-facing
  // fields are deliberately not parsed here. Absent or empty means nothing
  // degraded, which is a statement, not a silence.
  final List<String> degradationNotices;

  const GeneratedTrip({
    required this.tripId,
    required this.tripName,
    required this.profileId,
    required this.totalStops,
    required this.totalDurationMin,
    required this.anchorCount,
    required this.flavourCount,
    required this.stops,
    this.degradationNotices = const [],
  });

  factory GeneratedTrip.fromJson(Map<String, dynamic> json) {
    final stopsList = (json['stops'] as List<dynamic>)
        .map((s) => ItineraryStop.fromJson(s as Map<String, dynamic>))
        .toList();
    return GeneratedTrip(
      tripId: json['trip_id'] as String,
      tripName: json['trip_name'] as String,
      profileId: json['profile_id'] as String,
      totalStops: json['total_stops'] as int,
      totalDurationMin: json['total_duration_min'] as int,
      anchorCount: json['anchor_count'] as int,
      flavourCount: json['flavour_count'] as int,
      stops: stopsList,
      // Defensive by design: a missing key, a JSON null, a non-list value, a
      // non-map row, a row with no `human`, and a blank `human` all yield no
      // entry and none of them throws. An older server that sends no
      // degradations at all parses to an empty list, not an error.
      degradationNotices: [
        for (final row in (json['degradations'] as List<dynamic>?) ?? const [])
          if (row is Map<String, dynamic> &&
              (row['human'] as String?)?.trim().isNotEmpty == true)
            (row['human'] as String).trim(),
      ],
    );
  }

  Map<String, dynamic> toJson() => {
        'trip_id': tripId,
        'trip_name': tripName,
        'profile_id': profileId,
        'total_stops': totalStops,
        'total_duration_min': totalDurationMin,
        'anchor_count': anchorCount,
        'flavour_count': flavourCount,
        'stops': stops.map((s) => s.toJson()).toList(),
        'degradations': [
          for (final notice in degradationNotices) {'human': notice},
        ],
      };
}

// ---------------------------------------------------------------------------
// THE LIVING SESSION (Phase 5, design §4.6 / §8.2). The server plans and REPLANS;
// the phone holds the plan and its contingency set and SELECTS from it — it never
// decides. Everything below is what the wire hands the phone: a versioned plan,
// the day's promises with who is protected, and precomputed answers to the
// divergences that matter, each with the ONE question (only when a protected
// thing is touched) and its screen text (always).
// ---------------------------------------------------------------------------

/// One promise of the day (design §3.1) — a pin, a rest, the finish, or the
/// planner's anchor. `protected` is the person's own class (W5.2 R1.5): the only
/// kinds a session ever asks a question about.
class SessionPromise {
  final String promiseId;
  final String kind;
  final String name;
  final String arrivesHhmm;
  final String departsHhmm;
  final bool protected;

  const SessionPromise({
    required this.promiseId,
    required this.kind,
    required this.name,
    this.arrivesHhmm = '',
    this.departsHhmm = '',
    this.protected = false,
  });

  factory SessionPromise.fromJson(Map<String, dynamic> json) => SessionPromise(
    promiseId: json['promise_id'] as String,
    kind: json['kind'] as String,
    name: (json['name'] as String?) ?? '',
    arrivesHhmm: (json['arrives_hhmm'] as String?) ?? '',
    departsHhmm: (json['departs_hhmm'] as String?) ?? '',
    protected: (json['protected'] as bool?) ?? false,
  );
}

/// One precomputed answer (design §4.6). `trigger` is a MATCHER, never a policy —
/// `{"kind": "running_late", "stop_id": ..., "band_minutes": [10, 20]}`,
/// `running_early`, `minutes_left` (an open day), `stop_skipped`,
/// `promise_at_risk`, `wrap_up_from`. The phone matches its measured divergence
/// against these in SERVER order and takes the first that matches; it never
/// ranks them. `question` is non-null only when the entry touches a protected
/// thing (§4.2's two tiers) and `screenText` is never empty (§4.4.2).
class SessionContingency {
  final String contingencyId;
  final Map<String, dynamic> trigger;
  final int planVersion;
  final List<String> stopIds;
  final String screenText;
  final String? question;
  final String? defaultArm; // "keep" | "shorten"
  final List<String> alternateStopIds;
  final String? atRiskStopId;
  final String finishHhmm;

  const SessionContingency({
    required this.contingencyId,
    required this.trigger,
    required this.planVersion,
    required this.stopIds,
    required this.screenText,
    this.question,
    this.defaultArm,
    this.alternateStopIds = const [],
    this.atRiskStopId,
    this.finishHhmm = '',
  });

  String get kind => (trigger['kind'] as String?) ?? '';
  String? get triggerStopId => trigger['stop_id'] as String?;

  /// The band `[lo, hi)` in minutes, or null when the trigger carries none.
  List<int>? get bandMinutes {
    final raw = trigger['band_minutes'];
    if (raw is! List || raw.length != 2) return null;
    return [(raw[0] as num).toInt(), (raw[1] as num).toInt()];
  }

  factory SessionContingency.fromJson(Map<String, dynamic> json) =>
      SessionContingency(
        contingencyId: json['contingency_id'] as String,
        trigger: (json['trigger'] as Map<String, dynamic>?) ?? const {},
        planVersion: (json['plan_version'] as num?)?.toInt() ?? 0,
        stopIds: ((json['stop_ids'] as List<dynamic>?) ?? const [])
            .map((e) => e as String)
            .toList(),
        screenText: (json['screen_text'] as String?) ?? '',
        question: json['question'] as String?,
        defaultArm: json['default_arm'] as String?,
        alternateStopIds:
            ((json['alternate_stop_ids'] as List<dynamic>?) ?? const [])
                .map((e) => e as String)
                .toList(),
        atRiskStopId: json['at_risk_stop_id'] as String?,
        finishHhmm: (json['finish_hhmm'] as String?) ?? '',
      );
}

/// GET /trips/{id}/session and every replan reply — the day the person is
/// standing in, versioned (design §8.2), with the contingency set beside it.
class SessionPlan {
  final String tripId;
  final int planVersion;
  final List<ItineraryStop> stops;
  final List<SessionPromise> promises;
  final int retimeToleranceSeconds;
  final List<SessionContingency> contingencies;
  final List<String> degradationNotices;

  /// The walking speed this day was planned at — the preset the phone re-times
  /// with until it has learned the person's own pace (design §4.1; S5.10).
  final double walkingPaceKmh;

  /// When the day's clock starts ("HH:MM"): the frame every server stop clock
  /// and the phone's own re-timing share (S5.10's seam compares in it).
  final String dayStartHhmm;

  /// When the day is planned to END ("HH:MM"): the phone's minutes-left on an
  /// open day (W5.2 R1.3 bands by minutes left) count down to this.
  final String plannedEndHhmm;

  /// The party the day was planned for (solo, couple, family, take_it_easy,
  /// with_luggage) or null: the screen-only switch is per PARTY (W5.2 R4).
  final String? party;

  /// Where the day ends and what to call it (null coords on an open walk with
  /// no end: the day ends at its last stop). The phone re-times the finish
  /// itself (W5.13): a precomputed line's clock is stale by the time it fires.
  final double? finishLat;
  final double? finishLng;
  final String finishName;

  /// wall | firm | open: a firm or wall finish that has moved past the tolerance
  /// earns one screen line (W5.14 Q3); an open day's finish moves in silence.
  final String endHardness;

  const SessionPlan({
    required this.tripId,
    required this.planVersion,
    required this.stops,
    this.promises = const [],
    required this.retimeToleranceSeconds,
    this.contingencies = const [],
    this.degradationNotices = const [],
    this.walkingPaceKmh = 3.0,
    this.dayStartHhmm = '',
    this.plannedEndHhmm = '',
    this.party,
    this.finishLat,
    this.finishLng,
    this.finishName = 'your finish',
    this.endHardness = 'firm',
  });

  factory SessionPlan.fromJson(Map<String, dynamic> json) => SessionPlan(
    tripId: json['trip_id'] as String,
    planVersion: (json['plan_version'] as num).toInt(),
    stops: ((json['stops'] as List<dynamic>?) ?? const [])
        .map((s) => ItineraryStop.fromJson(s as Map<String, dynamic>))
        .toList(),
    promises: ((json['promises'] as List<dynamic>?) ?? const [])
        .map((p) => SessionPromise.fromJson(p as Map<String, dynamic>))
        .toList(),
    retimeToleranceSeconds:
        (json['retime_tolerance_seconds'] as num?)?.toInt() ?? 180,
    contingencies: ((json['contingencies'] as List<dynamic>?) ?? const [])
        .map((c) => SessionContingency.fromJson(c as Map<String, dynamic>))
        .toList(),
    degradationNotices: [
      for (final row in (json['degradations'] as List<dynamic>?) ?? const [])
        if (row is Map<String, dynamic> &&
            (row['human'] as String?)?.trim().isNotEmpty == true)
          (row['human'] as String).trim(),
    ],
    walkingPaceKmh: (json['walking_pace_kmh'] as num?)?.toDouble() ?? 3.0,
    dayStartHhmm: (json['day_start_hhmm'] as String?) ?? '',
    plannedEndHhmm: (json['planned_end_hhmm'] as String?) ?? '',
    party: json['party'] as String?,
    finishLat: (json['finish_lat'] as num?)?.toDouble(),
    finishLng: (json['finish_lng'] as num?)?.toDouble(),
    finishName: (json['finish_name'] as String?) ?? 'your finish',
    endHardness: (json['end_hardness'] as String?) ?? 'firm',
  );
}
