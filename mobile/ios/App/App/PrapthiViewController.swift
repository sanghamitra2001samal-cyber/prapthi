import UIKit
import WebKit
import Network
import Capacitor

/// Capacitor's view controller with the Prapthi app shell added.
class PrapthiViewController: CAPBridgeViewController {
    private var uiDelegateWrapper: ShellUIDelegate?
    private var bridgeFilter: BridgeMessageFilter?
    private let pathMonitor = NWPathMonitor()
    private var connectivityChecked = false

    override func capacitorDidLoad() {
        super.capacitorDidLoad()
        bridge?.registerPluginInstance(PrapthiShellPlugin())
        guard let webView = webView else { return }

        let content = webView.configuration.userContentController

        // Capacitor runs plugin calls from any page that shares this
        // configuration, with no check of where they came from. Payment
        // pop-ups must share it (WebKit requires it), so only calls from this
        // web view's main frame, on our own site or bundled pages, get through.
        if let original = webView.navigationDelegate as? WKScriptMessageHandler {
            let filter = BridgeMessageFilter(target: original, webView: webView)
            content.removeScriptMessageHandler(forName: "bridge")
            content.add(filter, name: "bridge")
            bridgeFilter = filter
        }

        // Download handling and the ready signal, shared with Android.
        if let path = Bundle.main.path(forResource: "native-shell", ofType: "js", inDirectory: "public"),
           let source = try? String(contentsOfFile: path, encoding: .utf8) {
            content.addUserScript(WKUserScript(source: source, injectionTime: .atDocumentStart, forMainFrameOnly: true))
        }

        // Payment pop-ups open in the app instead of Safari.
        let wrapper = ShellUIDelegate(fallback: webView.uiDelegate, host: self)
        webView.uiDelegate = wrapper
        uiDelegateWrapper = wrapper

        // Swipe from the edge to go back, the way iPhone users expect.
        webView.allowsBackForwardNavigationGestures = true

        watchConnectivityAtLaunch()
    }

    /// Offline, WebKit can serve the studio from its cache. The studio then
    /// cannot check the login, decides nobody is signed in and shows a
    /// sign-in form that cannot work. Show the offline page instead; it
    /// reconnects by itself once the network is back.
    private func watchConnectivityAtLaunch() {
        pathMonitor.pathUpdateHandler = { [weak self] path in
            let online = path.status == .satisfied
            DispatchQueue.main.async {
                guard let self = self, !self.connectivityChecked else { return }
                self.connectivityChecked = true
                self.pathMonitor.cancel()
                if !online, let offline = self.bridge?.config.errorPathURL {
                    self.webView?.load(URLRequest(url: offline))
                }
            }
        }
        pathMonitor.start(queue: DispatchQueue.global(qos: .userInitiated))
    }
}

/// Passes bridge messages to Capacitor only when they come from the app's own
/// web view, its main frame, and our site or the app's bundled pages.
final class BridgeMessageFilter: NSObject, WKScriptMessageHandler {
    private weak var target: WKScriptMessageHandler?
    private weak var webView: WKWebView?

    init(target: WKScriptMessageHandler, webView: WKWebView) {
        self.target = target
        self.webView = webView
        super.init()
    }

    func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
        guard let webView = webView, message.webView === webView, message.frameInfo.isMainFrame else { return }
        let origin = message.frameInfo.securityOrigin
        let scheme = origin.`protocol`
        let trusted = (scheme == "https" && PrapthiShellPlugin.isOwnHost(origin.host))
            || scheme == "capacitor"
        guard trusted else { return }
        target?.userContentController(userContentController, didReceive: message)
    }
}
