class ItineraryStop {
  final int sortOrder;
  // ItineraryItem id — addresses this stop for per-stop narration audio
  // (Phase 1). Nullable: legacy/seed trips may not carry it.
  final String? stopId;
  final String poiId;
  final String poiName;
  final double lat;
  final double lng;
  final String beatId;
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

  const ItineraryStop({
    required this.sortOrder,
    this.stopId,
    required this.poiId,
    required this.poiName,
    required this.lat,
    required this.lng,
    required this.beatId,
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
  });

  factory ItineraryStop.fromJson(Map<String, dynamic> json) {
    return ItineraryStop(
      sortOrder: json['sort_order'] as int,
      stopId: json['stop_id'] as String?,
      poiId: json['poi_id'] as String,
      poiName: json['poi_name'] as String,
      lat: (json['lat'] as num).toDouble(),
      lng: (json['lng'] as num).toDouble(),
      beatId: json['beat_id'] as String,
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
