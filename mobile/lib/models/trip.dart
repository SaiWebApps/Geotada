class ItineraryStop {
  final int sortOrder;
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

  const ItineraryStop({
    required this.sortOrder,
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
  });

  factory ItineraryStop.fromJson(Map<String, dynamic> json) {
    return ItineraryStop(
      sortOrder: json['sort_order'] as int,
      poiId: json['poi_id'] as String,
      poiName: json['poi_name'] as String,
      lat: (json['lat'] as num).toDouble(),
      lng: (json['lng'] as num).toDouble(),
      beatId: json['beat_id'] as String,
      lensName: json['lens_name'] as String,
      lensDisplay: json['lens_display'] as String,
      durationMin: json['duration_min'] as int,
      importanceTier: json['importance_tier'] as int,
      startTime: json['start_time'] as String,
      scriptBody: json['script_body'] as String?,
      audioUrl: json['audio_url'] as String?,
      audioDurationSec: (json['audio_duration_sec'] as num?)?.toDouble(),
    );
  }

  Map<String, dynamic> toJson() => {
        'sort_order': sortOrder,
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
      };

  ItineraryStop copyWith({
    String? audioUrl,
    double? audioDurationSec,
    String? scriptBody,
  }) {
    return ItineraryStop(
      sortOrder: sortOrder,
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
    );
  }
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

  const GeneratedTrip({
    required this.tripId,
    required this.tripName,
    required this.profileId,
    required this.totalStops,
    required this.totalDurationMin,
    required this.anchorCount,
    required this.flavourCount,
    required this.stops,
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
      };
}
