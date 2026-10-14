import Foundation
import Capacitor
import WebKit

/// The native half of the app shell on iOS. Decides where each link goes:
/// the whole prapthi.ai site stays in the app, UPI and other app links go to
/// their apps, other websites open in Safari, and pages opened by script
/// (Razorpay's bank pages) get an in-app window from ShellUIDelegate.
@objc(PrapthiShellPlugin)
public class PrapthiShellPlugin: CAPPlugin, CAPBridgedPlugin {
    public let identifier = "PrapthiShellPlugin"
    public let jsName = "PrapthiShell"
    public let pluginMethods: [CAPPluginMethod] = [
        CAPPluginMethod(name: "ready", returnType: CAPPluginReturnPromise)
    ]

    static func isOwnHost(_ host: String?) -> Bool {
        guard let host = host?.lowercased() else { return false }
        return host == "prapthi.ai" || host.hasSuffix(".prapthi.ai")
    }

    static func isWebScheme(_ scheme: String?) -> Bool {
        switch scheme?.lowercased() {
        case nil, "http", "https", "about", "blob", "data", "javascript", "file", "capacitor":
            return true
        default:
            return false
        }
    }

    /// Opens a link in whichever app handles it, and says so when none does.
    static func openOutside(_ url: URL, from viewController: UIViewController?) {
        UIApplication.shared.open(url, options: [:]) { opened in
            guard !opened, let vc = viewController else { return }
            let alert = UIAlertController(title: nil,
                                          message: "No app on this phone can open that link.",
                                          preferredStyle: .alert)
            alert.addAction(UIAlertAction(title: "OK", style: .default))
            vc.present(alert, animated: true)
        }
    }

    /// The page script calls this when content is ready. iOS keeps its launch
    /// screen up by itself, so there is nothing to release here; the method
    /// exists so the shared script behaves the same on both platforms.
    @objc func ready(_ call: CAPPluginCall) {
        call.resolve()
    }

    /// Capacitor asks every plugin before deciding about a navigation.
    /// true = we handled it (cancel), false = load it here, nil = default rules.
    override public func shouldOverrideLoad(_ navigationAction: WKNavigationAction) -> NSNumber? {
        guard let url = navigationAction.request.url else { return nil }

        // upi://, tez://, phonepe://, tel:, mailto:, whatsapp: ... belong to other apps.
        if !PrapthiShellPlugin.isWebScheme(url.scheme) {
            PrapthiShellPlugin.openOutside(url, from: bridge?.viewController)
            return true
        }

        let isNewWindow = navigationAction.targetFrame == nil
        if PrapthiShellPlugin.isOwnHost(url.host) {
            // Capacitor only counts .../app/ as the app; the sign-in and
            // pricing pages live on the same site and must stay in it too.
            return false
        }
        if isNewWindow {
            if navigationAction.navigationType == .linkActivated {
                // A tapped target="_blank" link to another site: Safari.
                PrapthiShellPlugin.openOutside(url, from: bridge?.viewController)
                return true
            }
            // window.open() from script, e.g. a bank page during payment:
            // allow it, and ShellUIDelegate gives it an in-app window.
            return false
        }
        return nil
    }
}
