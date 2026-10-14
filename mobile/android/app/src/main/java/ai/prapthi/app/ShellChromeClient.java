package ai.prapthi.app;

import android.annotation.SuppressLint;
import android.app.Activity;
import android.app.Dialog;
import android.graphics.Color;
import android.net.Uri;
import android.os.Message;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.KeyEvent;
import android.view.View;
import android.view.ViewGroup;
import android.view.Window;
import android.webkit.CookieManager;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.FrameLayout;
import android.widget.ImageButton;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.TextView;
import androidx.core.graphics.Insets;
import androidx.core.view.ViewCompat;
import androidx.core.view.WindowCompat;
import androidx.core.view.WindowInsetsCompat;
import androidx.core.view.WindowInsetsControllerCompat;
import com.getcapacitor.Bridge;
import com.getcapacitor.BridgeWebChromeClient;

/**
 * Capacitor's chrome client, plus real pop-up windows.
 *
 * Razorpay opens bank and 3-D Secure pages with window.open() and waits for
 * that window to report back to the checkout. Out of the box the WebView
 * either replaces the studio with the bank page or throws it out to Chrome,
 * where the result can never reach the app. Here a pop-up opens over the app
 * as its own window, keeps its link to the checkout that opened it, and
 * closes itself when the bank page calls window.close().
 *
 * Everything else (file pickers, microphone permission, alerts) is inherited
 * unchanged from BridgeWebChromeClient.
 */
public class ShellChromeClient extends BridgeWebChromeClient {

    private final Bridge bridge;

    public ShellChromeClient(Bridge bridge) {
        super(bridge);
        this.bridge = bridge;
    }

    @Override
    public void onProgressChanged(WebView view, int newProgress) {
        super.onProgressChanged(view, newProgress);
        if (newProgress >= 100) ShellPlugin.onPageDone(view);
    }

    @Override
    public boolean onCreateWindow(WebView view, boolean isDialog, boolean isUserGesture, Message resultMsg) {
        Activity activity = bridge.getActivity();
        if (activity == null || activity.isFinishing()) return false;

        // A tapped target="_blank" link to another website opens in the
        // browser like any external link; only our own pages and script
        // pop-ups (payments) stay inside the app.
        WebView.HitTestResult hit = view.getHitTestResult();
        if (isUserGesture && hit != null && hit.getType() == WebView.HitTestResult.SRC_ANCHOR_TYPE && hit.getExtra() != null) {
            Uri target = Uri.parse(hit.getExtra());
            if (ExternalLinks.open(activity, target)) return false;
            if (!ShellPlugin.isOwnHost(target.getHost())) {
                ExternalLinks.openInBrowser(activity, target);
                return false;
            }
        }

        WebView popup = buildPopup(activity, view);
        WebView.WebViewTransport transport = (WebView.WebViewTransport) resultMsg.obj;
        transport.setWebView(popup);
        resultMsg.sendToTarget();
        return true;
    }

    @SuppressLint("SetJavaScriptEnabled")
    private WebView buildPopup(Activity activity, WebView parent) {
        WebView popup = new WebView(activity);
        WebSettings s = popup.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setJavaScriptCanOpenWindowsAutomatically(true);
        s.setSupportMultipleWindows(false);   // a pop-up's own pop-ups load in place
        s.setMediaPlaybackRequiresUserGesture(false);
        s.setUserAgentString(parent.getSettings().getUserAgentString());
        CookieManager.getInstance().setAcceptThirdPartyCookies(popup, true);

        Dialog dialog = new Dialog(activity, android.R.style.Theme_DeviceDefault_Light_NoActionBar);
        dialog.requestWindowFeature(Window.FEATURE_NO_TITLE);

        LinearLayout root = new LinearLayout(activity);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setBackgroundColor(Color.WHITE);

        // Header: what this window is and a way out of it, so a bank page
        // that never closes itself cannot trap anyone.
        LinearLayout bar = new LinearLayout(activity);
        bar.setOrientation(LinearLayout.HORIZONTAL);
        bar.setGravity(Gravity.CENTER_VERTICAL);
        bar.setBackgroundColor(Color.WHITE);
        bar.setElevation(dp(activity, 2));
        int pad = dp(activity, 6);
        bar.setPadding(pad, pad, pad, pad);

        ImageButton close = new ImageButton(activity);
        close.setImageResource(R.drawable.ic_close);
        close.setBackgroundColor(Color.TRANSPARENT);
        close.setContentDescription(activity.getString(R.string.popup_close));
        close.setOnClickListener(v -> dialog.dismiss());
        bar.addView(close, new LinearLayout.LayoutParams(dp(activity, 44), dp(activity, 44)));

        TextView title = new TextView(activity);
        title.setText(R.string.popup_title);
        title.setTextColor(Color.parseColor("#0b1020"));
        title.setTextSize(TypedValue.COMPLEX_UNIT_SP, 16);
        title.setSingleLine(true);
        title.setPadding(dp(activity, 8), 0, dp(activity, 8), 0);
        bar.addView(title, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f));
        root.addView(bar, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));

        ProgressBar progress = new ProgressBar(activity, null, android.R.attr.progressBarStyleHorizontal);
        progress.setIndeterminate(false);
        progress.setMax(100);
        root.addView(progress, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(activity, 3)));

        FrameLayout body = new FrameLayout(activity);
        body.addView(popup, new FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));
        root.addView(body, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f));

        popup.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView v, WebResourceRequest request) {
                // http(s) stays in the window (bank pages live on any host);
                // UPI and other app links go to their apps.
                return ExternalLinks.open(activity, request.getUrl());
            }

            @Override
            public void onPageFinished(WebView v, String url) {
                CharSequence t = v.getTitle();
                if (t != null && t.length() > 0 && !t.toString().startsWith("http")) title.setText(t);
            }
        });
        popup.setWebChromeClient(new WebChromeClient() {
            @Override
            public void onCloseWindow(WebView window) {
                if (dialog.isShowing()) dialog.dismiss();
            }

            @Override
            public void onProgressChanged(WebView v, int p) {
                progress.setProgress(p);
                progress.setVisibility(p >= 100 ? View.INVISIBLE : View.VISIBLE);
            }
        });

        dialog.setOnKeyListener((d, keyCode, event) -> {
            if (keyCode == KeyEvent.KEYCODE_BACK && event.getAction() == KeyEvent.ACTION_UP) {
                if (popup.canGoBack()) popup.goBack();
                else dialog.dismiss();
                return true;
            }
            return keyCode == KeyEvent.KEYCODE_BACK;
        });
        dialog.setOnDismissListener(d -> {
            popup.stopLoading();
            popup.setWebChromeClient(null);
            popup.setWebViewClient(new WebViewClient());
            popup.destroy();
        });

        dialog.setContentView(root);
        Window w = dialog.getWindow();
        if (w != null) {
            w.setLayout(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT);
            WindowCompat.setDecorFitsSystemWindows(w, false);
            // The window is white: dark status and navigation icons, or they vanish.
            WindowInsetsControllerCompat bars = WindowCompat.getInsetsController(w, w.getDecorView());
            bars.setAppearanceLightStatusBars(true);
            bars.setAppearanceLightNavigationBars(true);
        }
        // Keep the header clear of the status bar and the page clear of the
        // navigation bar and keyboard, on phones that draw edge to edge.
        ViewCompat.setOnApplyWindowInsetsListener(root, (v, insets) -> {
            Insets bars = insets.getInsets(WindowInsetsCompat.Type.systemBars() | WindowInsetsCompat.Type.ime());
            v.setPadding(bars.left, bars.top, bars.right, bars.bottom);
            return WindowInsetsCompat.CONSUMED;
        });
        dialog.show();
        return popup;
    }

    private static int dp(Activity a, int v) {
        return Math.round(TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, v, a.getResources().getDisplayMetrics()));
    }
}
