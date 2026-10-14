import UIKit
import WebKit

/// Sits in front of Capacitor's WKUIDelegate and adds real pop-up windows.
///
/// Razorpay opens bank and 3-D Secure pages with window.open() and waits for
/// that window to report back. Capacitor sends every such window to Safari,
/// where the result can never reach the app. Here the window opens inside the
/// app, keeps its link to the checkout that opened it, and closes itself when
/// the page calls window.close(). Everything else (alerts, file pickers,
/// microphone permission) is passed through to Capacitor unchanged.
final class ShellUIDelegate: NSObject, WKUIDelegate {
    private weak var fallback: WKUIDelegate?
    private weak var host: UIViewController?

    init(fallback: WKUIDelegate?, host: UIViewController) {
        self.fallback = fallback
        self.host = host
        super.init()
    }

    // MARK: - Pop-up windows

    func webView(_ webView: WKWebView,
                 createWebViewWith configuration: WKWebViewConfiguration,
                 for navigationAction: WKNavigationAction,
                 windowFeatures: WKWindowFeatures) -> WKWebView? {
        guard let host = host else { return nil }
        // WebKit requires the new window to be built from this configuration;
        // that is what keeps window.opener working for the payment page.
        let popup = PopupViewController(configuration: configuration)
        let nav = UINavigationController(rootViewController: popup)
        nav.modalPresentationStyle = .pageSheet
        // A half-finished payment must not vanish with a stray swipe.
        nav.isModalInPresentation = true
        (host.presentedViewController ?? host).present(nav, animated: true)
        return popup.webView
    }

    // MARK: - Everything else goes to Capacitor

    override func responds(to aSelector: Selector!) -> Bool {
        if super.responds(to: aSelector) { return true }
        return fallback?.responds(to: aSelector) ?? false
    }

    override func forwardingTarget(for aSelector: Selector!) -> Any? {
        if let fallback = fallback, fallback.responds(to: aSelector) { return fallback }
        return super.forwardingTarget(for: aSelector)
    }
}

/// An in-app window for a page opened by script (a bank page during payment).
final class PopupViewController: UIViewController, WKNavigationDelegate, WKUIDelegate {
    let webView: WKWebView
    private let progress = UIProgressView(progressViewStyle: .bar)
    private var progressObservation: NSKeyValueObservation?
    private var titleObservation: NSKeyValueObservation?

    init(configuration: WKWebViewConfiguration) {
        webView = WKWebView(frame: .zero, configuration: configuration)
        super.init(nibName: nil, bundle: nil)
    }

    required init?(coder: NSCoder) {
        fatalError("init(coder:) is not used")
    }

    override func viewDidLoad() {
        super.viewDidLoad()
        view.backgroundColor = .systemBackground
        title = "Secure page"
        navigationItem.leftBarButtonItem = UIBarButtonItem(barButtonSystemItem: .close,
                                                           target: self,
                                                           action: #selector(closeTapped))

        webView.navigationDelegate = self
        webView.uiDelegate = self
        webView.allowsBackForwardNavigationGestures = true
        webView.translatesAutoresizingMaskIntoConstraints = false
        progress.translatesAutoresizingMaskIntoConstraints = false
        view.addSubview(webView)
        view.addSubview(progress)
        NSLayoutConstraint.activate([
            progress.topAnchor.constraint(equalTo: view.safeAreaLayoutGuide.topAnchor),
            progress.leadingAnchor.constraint(equalTo: view.leadingAnchor),
            progress.trailingAnchor.constraint(equalTo: view.trailingAnchor),
            webView.topAnchor.constraint(equalTo: view.safeAreaLayoutGuide.topAnchor),
            webView.leadingAnchor.constraint(equalTo: view.leadingAnchor),
            webView.trailingAnchor.constraint(equalTo: view.trailingAnchor),
            webView.bottomAnchor.constraint(equalTo: view.bottomAnchor)
        ])

        progressObservation = webView.observe(\.estimatedProgress, options: [.new]) { [weak self] web, _ in
            self?.progress.setProgress(Float(web.estimatedProgress), animated: true)
            self?.progress.isHidden = web.estimatedProgress >= 1
        }
        titleObservation = webView.observe(\.title, options: [.new]) { [weak self] web, _ in
            if let t = web.title, !t.isEmpty, !t.hasPrefix("http") { self?.title = t }
        }
    }

    @objc private func closeTapped() {
        dismiss(animated: true)
    }

    // Bank pages live on any host, so web links stay here; UPI and other app
    // links go to their apps.
    func webView(_ webView: WKWebView,
                 decidePolicyFor navigationAction: WKNavigationAction,
                 decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        if let url = navigationAction.request.url, !PrapthiShellPlugin.isWebScheme(url.scheme) {
            PrapthiShellPlugin.openOutside(url, from: self)
            decisionHandler(.cancel)
            return
        }
        decisionHandler(.allow)
    }

    // The page finished and called window.close().
    func webViewDidClose(_ webView: WKWebView) {
        dismiss(animated: true)
    }

    // A pop-up's own pop-ups load in the same window.
    func webView(_ webView: WKWebView,
                 createWebViewWith configuration: WKWebViewConfiguration,
                 for navigationAction: WKNavigationAction,
                 windowFeatures: WKWindowFeatures) -> WKWebView? {
        webView.load(navigationAction.request)
        return nil
    }

    func webView(_ webView: WKWebView,
                 runJavaScriptAlertPanelWithMessage message: String,
                 initiatedByFrame frame: WKFrameInfo,
                 completionHandler: @escaping () -> Void) {
        let alert = UIAlertController(title: nil, message: message, preferredStyle: .alert)
        alert.addAction(UIAlertAction(title: "OK", style: .default) { _ in completionHandler() })
        present(alert, animated: true)
    }

    func webView(_ webView: WKWebView,
                 runJavaScriptConfirmPanelWithMessage message: String,
                 initiatedByFrame frame: WKFrameInfo,
                 completionHandler: @escaping (Bool) -> Void) {
        let alert = UIAlertController(title: nil, message: message, preferredStyle: .alert)
        alert.addAction(UIAlertAction(title: "Cancel", style: .cancel) { _ in completionHandler(false) })
        alert.addAction(UIAlertAction(title: "OK", style: .default) { _ in completionHandler(true) })
        present(alert, animated: true)
    }
}
