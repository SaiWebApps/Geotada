import Flutter
import MapKit

class GeocodingChannel {
  static func register(with messenger: FlutterBinaryMessenger) {
    let channel = FlutterMethodChannel(
      name: "com.ondoway/geocoding",
      binaryMessenger: messenger
    )
    channel.setMethodCallHandler { call, result in
      guard call.method == "search" else {
        result(FlutterMethodNotImplemented)
        return
      }
      guard let query = call.arguments as? String, !query.isEmpty else {
        result(FlutterError(code: "INVALID_ARG", message: "Query required", details: nil))
        return
      }
      let request = MKLocalSearch.Request()
      request.naturalLanguageQuery = query
      let search = MKLocalSearch(request: request)
      search.start { response, error in
        if let error = error {
          result(FlutterError(code: "SEARCH_FAILED", message: error.localizedDescription, details: nil))
          return
        }
        guard let item = response?.mapItems.first else {
          result(FlutterError(code: "NO_RESULTS", message: "No results for '\(query)'", details: nil))
          return
        }
        let coord = item.placemark.coordinate
        result([
          "lat": coord.latitude,
          "lng": coord.longitude,
          "name": item.name ?? query
        ])
      }
    }
  }
}
