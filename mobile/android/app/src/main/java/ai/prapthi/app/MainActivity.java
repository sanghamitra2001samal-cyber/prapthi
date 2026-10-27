package ai.prapthi.app;

import android.content.Context;
import android.net.ConnectivityManager;
import android.net.Network;
import android.net.NetworkCapabilities;
import android.os.Bundle;
import android.os.SystemClock;
import android.webkit.WebView;
import androidx.activity.OnBackPressedCallback;
import androidx.core.splashscreen.SplashScreen;
import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {

    /** Never hold the splash longer than this, even on a very slow network. */
    private static final long SPLASH_MAX_MS = 8000;

    @Override
    public void onCreate(Bundle savedInstanceState) {
        // Keep the logo up until the studio has actually loaded, instead of
        // swapping it for a blank white page while the network catches up.
        ShellPlugin.firstPageLoaded = false;   // the process can outlive an activity
        SplashScreen splash = SplashScreen.installSplashScreen(this);
        long shownAt = SystemClock.uptimeMillis();
        splash.setKeepOnScreenCondition(
            () -> !ShellPlugin.firstPageLoaded && SystemClock.uptimeMillis() - shownAt < SPLASH_MAX_MS
        );

        registerPlugin(ShellPlugin.class);
        super.onCreate(savedInstanceState);

        // Capacitor installs its own chrome client after plugins have loaded,
        // so ours (which adds payment pop-up windows) has to go in afterwards.
        bridge.getWebView().setWebChromeClient(new ShellChromeClient(bridge));

        // Back first closes whatever is open on the page (the site menu, a studio
        // dialog or drawer), then walks back through the pages, and on the first
        // page leaves the app the way every Android app does. (Capacitor's
        // default swallows it there, so the app could never be left with back.)
        getOnBackPressedDispatcher().addCallback(this, new OnBackPressedCallback(true) {
            @Override
            public void handleOnBackPressed() {
                WebView web = bridge.getWebView();
                web.evaluateJavascript(
                    "(function(){try{return !!(window.__prapthiBack && window.__prapthiBack());}catch(e){return false;}})()",
                    closedSomething -> {
                        if ("true".equals(closedSomething)) return;
                        if (web.canGoBack()) {
                            web.goBack();
                        } else {
                            moveTaskToBack(true);   // keep the studio warm for next time
                        }
                    }
                );
            }
        });

        // Offline, the WebView quietly serves the studio from its cache. The
        // studio cannot reach the server to check the login, decides nobody
        // is signed in, and shows a sign-in form that cannot work. Say plainly
        // that the phone is offline instead; that page reconnects by itself.
        if (!isOnline() && bridge.getErrorUrl() != null) {
            String offline = bridge.getErrorUrl();
            bridge.getWebView().post(() -> bridge.getWebView().loadUrl(offline));
        }
    }

    private boolean isOnline() {
        ConnectivityManager cm = (ConnectivityManager) getSystemService(Context.CONNECTIVITY_SERVICE);
        if (cm == null) return true;   // cannot tell: try the network rather than refuse
        Network net = cm.getActiveNetwork();
        NetworkCapabilities caps = net == null ? null : cm.getNetworkCapabilities(net);
        return caps != null && caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET);
    }
}
