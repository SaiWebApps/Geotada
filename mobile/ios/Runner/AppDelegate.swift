import AVFoundation
import Flutter
import UIKit

@main
@objc class AppDelegate: FlutterAppDelegate, FlutterImplicitEngineDelegate {
  override func application(
    _ application: UIApplication,
    didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?
  ) -> Bool {
    // Play audio through a locked screen: category .playback is not silenced on
    // lock (unlike the default), and with UIBackgroundModes:audio it continues
    // in the background. Native (no audio_session Dart FFI, which crashes here).
    do {
      try AVAudioSession.sharedInstance().setCategory(.playback, mode: .spokenAudio)
    } catch {
      NSLog("AVAudioSession setCategory failed: \(error)")
    }
    return super.application(application, didFinishLaunchingWithOptions: launchOptions)
  }

  func didInitializeImplicitFlutterEngine(_ engineBridge: FlutterImplicitEngineBridge) {
    GeneratedPluginRegistrant.register(with: engineBridge.pluginRegistry)
    if let controller = window?.rootViewController as? FlutterViewController {
      GeocodingChannel.register(with: controller.binaryMessenger)
    }
  }
}
