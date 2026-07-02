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
    );
  }
}

/// One ordered stop inside a [RouteOption] flavour — the subset of the
/// backend §2.8 RouteOptionStop shape the flavour picker needs.
class RouteOptionStop {
  final String name;
  // Spotlight output band: "dwell" (full stop) or "vignette" (walk-past).
  // Backend default is "dwell" (contract.py), mirrored here.
  final String band;
  final int minutes;
  final double spotlight;

  const RouteOptionStop({
    required this.name,
    this.band = 'dwell',
    this.minutes = 0,
    this.spotlight = 0.0,
  });

  factory RouteOptionStop.fromJson(Map<String, dynamic> json) {
    return RouteOptionStop(
      name: json['name'] as String,
      band: (json['band'] as String?) ?? 'dwell',
      minutes: (json['minutes'] as num?)?.toInt() ?? 0,
      spotlight: (json['spotlight'] as num?)?.toDouble() ?? 0.0,
    );
  }

  Map<String, dynamic> toJson() => {
        'name': name,
        'band': band,
        'minutes': minutes,
        'spotlight': spotlight,
      };
}

/// One tour flavour from POST /trips/generate `options` (§2.8) — the subset
/// the flavour picker needs. options[0] is the backend-persisted default.
class RouteOption {
  final String routeId;
  final List<RouteOptionStop> stops;
  final int etaSeconds;
  final String? lensCoverageNote;

  const RouteOption({
    required this.routeId,
    required this.stops,
    required this.etaSeconds,
    this.lensCoverageNote,
  });

  factory RouteOption.fromJson(Map<String, dynamic> json) {
    return RouteOption(
      routeId: json['route_id'] as String,
      stops: ((json['stops'] as List<dynamic>?) ?? const [])
          .map((s) => RouteOptionStop.fromJson(s as Map<String, dynamic>))
          .toList(),
      etaSeconds: json['eta_seconds'] as int,
      lensCoverageNote: json['lens_coverage_note'] as String?,
    );
  }

  Map<String, dynamic> toJson() => {
        'route_id': routeId,
        'stops': stops.map((s) => s.toJson()).toList(),
        'eta_seconds': etaSeconds,
        'lens_coverage_note': lensCoverageNote,
      };
}

class GeneratedTrip {
  final String tripId;
  final String tripName;
  final String profileId;
  final int totalStops;
  final int totalDurationMin;
  final int anchorCount;
  final int flavourCount;
  final List<ItineraryStop> stops;
  // k-flavour RouteOptions from POST /trips/generate. GET /trips never
  // returns them, so absent parses to [] (back-compat) — the flavour picker
  // only shows for a just-generated trip.
  final List<RouteOption> options;

  const GeneratedTrip({
    required this.tripId,
    required this.tripName,
    required this.profileId,
    required this.totalStops,
    required this.totalDurationMin,
    required this.anchorCount,
    required this.flavourCount,
    required this.stops,
    this.options = const [],
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
      options: ((json['options'] as List<dynamic>?) ?? const [])
          .map((o) => RouteOption.fromJson(o as Map<String, dynamic>))
          .toList(),
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
        'options': options.map((o) => o.toJson()).toList(),
      };
}
