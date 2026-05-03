import Flutter
import UIKit
import app_links

class SceneDelegate: FlutterSceneDelegate {
  override func scene(_ scene: UIScene, willConnectTo session: UISceneSession, options connectionOptions: UIScene.ConnectionOptions) {
    super.scene(scene, willConnectTo: session, options: connectionOptions)

    if let urlContext = connectionOptions.urlContexts.first {
      AppLinks.shared.handleLink(url: urlContext.url)
    }
  }
}
