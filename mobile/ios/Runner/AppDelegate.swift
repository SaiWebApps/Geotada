import AVFoundation
import Flutter
import UIKit

@main
@objc class AppDelegate: FlutterAppDelegate, FlutterImplicitEngineDelegate,
  AVAudioPlayerDelegate
{
  // The production tour-playback file player (com.ondoway/native_audio) and the
  // channel it reports completion back over. Both are held strongly: the player
  // so it survives the play call, the channel so the delegate can invoke
  // `onComplete` on it long after registration returned.
  private var filePlayer: AVAudioPlayer?
  // AVAudioPlayer(data:) does not copy its data; hold it for the player's life.
  private var filePlayerData: Data?
  private var nativeAudioChannel: FlutterMethodChannel?

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
    registerAudioSessionChannel(messenger)
    registerNativeAudioChannel(messenger)
  }

  /// Foreground-only audio-session activation for the tour-playback path.
  /// `prepare` activates the .playback/.duckOthers session while the app is
  /// frontmost; it then survives lock, so a background geofence fire plays
  /// without re-activating — which returns CannotInterruptOthers (560557684),
  /// and is exactly what made the walk silent before this existed.
  ///
  /// A third channel, `com.ondoway/bg_audio`, stood beside this one until
  /// 2026-08-31. It was the Slice 0.3 spike's ancestor of these two: the same
  /// session activation, plus a `play` that took RAW CLIP BYTES from Dart. Its
  /// job was to find out whether anything could be heard through a locked
  /// screen. The answer it produced is now permanent — activation lives here,
  /// file playback lives in the native_audio channel below — so the channel was
  /// a third way to do what these two already do, and it is gone.
  private func registerAudioSessionChannel(_ messenger: FlutterBinaryMessenger) {
    let channel = FlutterMethodChannel(
      name: "com.ondoway/audio_session", binaryMessenger: messenger)
    channel.setMethodCallHandler { call, result in
      let session = AVAudioSession.sharedInstance()
      switch call.method {
      case "prepare":
        do {
          try session.setCategory(.playback, mode: .spokenAudio, options: [.duckOthers])
          try session.setActive(true)
          result(nil)
        } catch {
          result(FlutterError(code: "audio_session", message: "\(error)", details: nil))
        }
      case "deactivate":
        do {
          // Release the ducked session so the tourist's music/podcast returns to
          // full volume. notifyOthersOnDeactivation tells other apps to resume.
          try session.setActive(false, options: [.notifyOthersOnDeactivation])
          result(nil)
        } catch {
          result(FlutterError(code: "audio_session", message: "\(error)", details: nil))
        }
      default:
        result(FlutterMethodNotImplemented)
      }
    }
  }

  /// PRODUCTION tour-playback player. just_audio's AVPlayer emits no audible
  /// output while the screen is locked on iOS 26 (proven on-device — see the
  /// slice DIAGNOSIS), so cached tour narration plays through an `AVAudioPlayer`
  /// here instead, which DOES play locked on the same `.playback` session that
  /// the `prepare` calls activate. State the Dart side needs is bridged back:
  /// `play` returns the clip duration (seconds), `getPosition` reports the play
  /// head, and completion is pushed via `onComplete` from the delegate below —
  /// tour auto-advance depends on that completion signal.
  private func registerNativeAudioChannel(_ messenger: FlutterBinaryMessenger) {
    let channel = FlutterMethodChannel(
      name: "com.ondoway/native_audio", binaryMessenger: messenger)
    nativeAudioChannel = channel
    channel.setMethodCallHandler { [weak self] call, result in
      guard let self = self else { return }
      switch call.method {
      case "play":
        guard
          let args = call.arguments as? [String: Any],
          let path = args["path"] as? String
        else {
          result(FlutterError(code: "native_audio_play", message: "no path", details: nil))
          return
        }
        do {
          // Load the bytes and init from Data, NOT contentsOf(url): AVAudioPlayer's
          // URL initializer trusts the file EXTENSION to pick a decoder, so a clip
          // whose bytes are one format under a different extension (the app caches
          // everything as `.mp3`, and the debug proof caches a WAV as `.mp3`)
          // throws. The Data initializer content-sniffs the header instead — the
          // path proven to play locked in Slice 0.3.
          let data = try Data(contentsOf: URL(fileURLWithPath: path))
          let player = try AVAudioPlayer(data: data)
          player.delegate = self
          player.prepareToPlay()
          player.play()
          self.filePlayerData = data
          self.filePlayer = player
          result(player.duration)  // seconds
        } catch {
          result(FlutterError(code: "native_audio_play", message: "\(error)", details: nil))
        }
      case "pause":
        self.filePlayer?.pause()
        result(nil)
      case "resume":
        self.filePlayer?.play()
        result(nil)
      case "stop":
        self.filePlayer?.stop()
        self.filePlayer = nil
        self.filePlayerData = nil
        result(nil)
      case "seek":
        if let args = call.arguments as? [String: Any],
          let ms = args["positionMs"] as? Int
        {
          self.filePlayer?.currentTime = Double(ms) / 1000.0
        }
        result(nil)
      case "getPosition":
        result(Int((self.filePlayer?.currentTime ?? 0) * 1000))
      default:
        result(FlutterMethodNotImplemented)
      }
    }
  }

  // AVAudioPlayerDelegate: the clip finished on its own. Tell Dart so
  // AudioService flips `isPlaying` false and TourPlaybackService advances to the
  // next stop. (A `stop()` call nils the player before this fires, so it is only
  // reached on natural completion — exactly the auto-advance trigger.)
  func audioPlayerDidFinishPlaying(_ player: AVAudioPlayer, successfully flag: Bool) {
    nativeAudioChannel?.invokeMethod("onComplete", arguments: nil)
  }
}
