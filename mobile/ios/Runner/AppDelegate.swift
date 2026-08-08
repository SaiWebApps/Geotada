import AVFoundation
import Flutter
import UIKit

@main
@objc class AppDelegate: FlutterAppDelegate, FlutterImplicitEngineDelegate {
  // Held strongly so the player is not deallocated before/while it plays.
  private var bgAudioPlayer: AVAudioPlayer?

  override func application(
    _ application: UIApplication,
    didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?
  ) -> Bool {
    // Configure (but do NOT activate) the audio session at launch. .playback is
    // not silenced on lock, and .duckOthers makes it a *mixable* (non-interrupting)
    // session — the tourist's music/podcast dips while narration plays, and, key
    // for the background path, a mixable session never triggers
    // CannotInterruptOthers on setActive. Activation happens in the FOREGROUND via
    // the `prepare` channel call (see below), never from the geofence callback.
    do {
      try AVAudioSession.sharedInstance().setCategory(
        .playback, mode: .spokenAudio, options: [.duckOthers])
    } catch {
      NSLog("AVAudioSession setCategory failed: \(error)")
    }
    return super.application(application, didFinishLaunchingWithOptions: launchOptions)
  }

  func didInitializeImplicitFlutterEngine(_ engineBridge: FlutterImplicitEngineBridge) {
    GeneratedPluginRegistrant.register(with: engineBridge.pluginRegistry)
    // Register app-level channels on the ENGINE's messenger. NOT via
    // window?.rootViewController: under the UIScene lifecycle the AppDelegate's
    // `window` is nil, so that path silently registered nothing and every call
    // failed with MissingPluginException (this also left GeocodingChannel dead).
    let messenger = engineBridge.applicationRegistrar.messenger()
    GeocodingChannel.register(with: messenger)
    registerBackgroundAudioChannel(messenger)
  }

  /// Native background-audio bridge with two calls:
  ///
  /// - `prepare`: called ONCE from the foreground at tour start. Activates the
  ///   .playback/.duckOthers session while the app is frontmost — the only state
  ///   in which iOS lets an app take the audio session. The session then stays
  ///   active as the app backgrounds and the screen locks.
  /// - `play`: called from the (possibly background, screen-locked) geofence
  ///   callback. It does NOT touch the session — it is already active — it only
  ///   builds a player and plays. This is what previously failed: activating from
  ///   the background returned CannotInterruptOthers (560557684). Activation was
  ///   moved to `prepare`; the background path now only plays.
  private func registerBackgroundAudioChannel(_ messenger: FlutterBinaryMessenger) {
    let channel = FlutterMethodChannel(
      name: "com.ondoway/bg_audio", binaryMessenger: messenger)
    channel.setMethodCallHandler { [weak self] call, result in
      let session = AVAudioSession.sharedInstance()
      switch call.method {
      case "prepare":
        do {
          try session.setCategory(.playback, mode: .spokenAudio, options: [.duckOthers])
          try session.setActive(true)
          result(nil)
        } catch {
          result(FlutterError(code: "bg_audio_prepare", message: "\(error)", details: nil))
        }
      case "play":
        guard let data = (call.arguments as? FlutterStandardTypedData)?.data else {
          result(FlutterError(code: "bg_audio_play", message: "no clip bytes", details: nil))
          return
        }
        do {
          self?.bgAudioPlayer = try AVAudioPlayer(data: data)
          self?.bgAudioPlayer?.prepareToPlay()
          self?.bgAudioPlayer?.play()
          result(nil)
        } catch {
          result(FlutterError(code: "bg_audio_play", message: "\(error)", details: nil))
        }
      default:
        result(FlutterMethodNotImplemented)
      }
    }
  }
}
