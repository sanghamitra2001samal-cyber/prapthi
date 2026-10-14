package ai.prapthi.app;

import android.net.Uri;
import android.webkit.CookieManager;
import android.webkit.URLUtil;
import android.webkit.WebSettings;
import android.webkit.WebView;
import androidx.webkit.WebViewCompat;
import androidx.webkit.WebViewFeature;
import com.getcapacitor.Logger;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.HashSet;
import java.util.Set;
import org.json.JSONObject;
import java.util.Locale;

/**
 * The native half of the app shell. Sets the WebView up to behave like a
 * browser where the studio needs it to: pop-up windows for payments, links
 * to UPI and other apps, downloads saved through the share sheet, and a
 * login that survives the app being closed.
 */
@CapacitorPlugin(name = "PrapthiShell")
public class ShellPlugin extends Plugin {

    /** Set once the first page is ready to show, so the splash can go. */
    static volatile boolean firstPageLoaded = false;

    /** Pages the shell script is allowed to run in. */
    private static final Set<String> OWN_ORIGINS = new HashSet<>();

    static {
        OWN_ORIGINS.add("https://prapthi.ai");
        OWN_ORIGINS.add("https://www.prapthi.ai");
    }

    private static String shellScript = "";
    /** Old WebViews without document-start scripts get it once loading ends. */
    private static boolean injectLate = false;

    static boolean isOwnHost(String host) {
        if (host == null) return false;
        String h = host.toLowerCase(Locale.ROOT);
        return h.equals("prapthi.ai") || h.endsWith(".prapthi.ai");
    }

    @Override
    public void load() {
        shellScript = readAsset("public/native-shell.js");
        WebView webView = bridge.getWebView();

        WebSettings settings = webView.getSettings();
        settings.setSupportMultipleWindows(true);
        settings.setJavaScriptCanOpenWindowsAutomatically(true);
        settings.setMediaPlaybackRequiresUserGesture(false);
        // Razorpay's checkout is a third-party frame on our page.
        CookieManager.getInstance().setAcceptCookie(true);
        CookieManager.getInstance().setAcceptThirdPartyCookies(webView, true);

        // A response sent as an attachment never passes a link click, so the
        // page script never sees it: route it to the same save sheet.
        webView.setDownloadListener((url, userAgent, contentDisposition, mimeType, length) -> {
            String name = URLUtil.guessFileName(url, contentDisposition, mimeType);
            String js = "window.__prapthiSave ? window.__prapthiSave(" + JSONObject.quote(url) + ", "
                + JSONObject.quote(name) + ") : void 0;";
            webView.post(() -> webView.evaluateJavascript(js, null));
        });

        // Capacitor's own "page loaded" event only fires if the progress bar
        // happens to read exactly 100 at that moment, which a page still
        // fetching images never does. A document-start script runs on every
        // page of our own site, every time, before the page's own code.
        if (!shellScript.isEmpty()) {
            if (WebViewFeature.isFeatureSupported(WebViewFeature.DOCUMENT_START_SCRIPT)) {
                WebViewCompat.addDocumentStartJavaScript(webView, shellScript, OWN_ORIGINS);
            } else {
                injectLate = true;
            }
        }
    }

    /** Called by ShellChromeClient as each page finishes loading. */
    static void onPageDone(WebView view) {
        firstPageLoaded = true;
        if (injectLate && view.getUrl() != null && isOwnHost(Uri.parse(view.getUrl()).getHost())) {
            view.evaluateJavascript(shellScript, null);   // the script guards against running twice
        }
    }

    /** The shell script calls this as soon as a page's content is ready. */
    @PluginMethod
    public void ready(PluginCall call) {
        firstPageLoaded = true;
        call.resolve();
    }

    /** Capacitor asks every plugin first before deciding where a link goes. */
    @Override
    public Boolean shouldOverrideLoad(Uri url) {
        if (url == null) return null;
        if (ExternalLinks.open(getContext(), url)) return true;   // upi://, intent://, tel:, mailto: ...
        return null;                                               // web links: Capacitor's normal rules
    }

    @Override
    protected void handleOnPause() {
        // The WebView writes cookies to disk on its own schedule; a login made
        // moments before the app is swiped away would otherwise be lost.
        CookieManager.getInstance().flush();
    }

    private String readAsset(String path) {
        try (InputStream in = getContext().getAssets().open(path); ByteArrayOutputStream out = new ByteArrayOutputStream()) {
            byte[] buf = new byte[8192];
            int n;
            while ((n = in.read(buf)) != -1) out.write(buf, 0, n);
            return out.toString(StandardCharsets.UTF_8.name());
        } catch (Exception e) {
            Logger.error("PrapthiShell", "Could not read " + path, e);
            return "";
        }
    }
}
