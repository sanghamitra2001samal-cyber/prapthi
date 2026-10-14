package ai.prapthi.app;

import android.content.ActivityNotFoundException;
import android.content.Context;
import android.content.Intent;
import android.net.Uri;
import android.widget.Toast;
import java.util.Locale;

/**
 * Hands links the WebView cannot show to the app that can: UPI apps during
 * a Razorpay payment (upi://, intent://, tez://, phonepe://...), the phone
 * dialler, the mail app, WhatsApp and so on.
 */
final class ExternalLinks {

    private ExternalLinks() {}

    /** Schemes the WebView loads itself. Everything else belongs to another app. */
    static boolean isWebScheme(String scheme) {
        if (scheme == null) return true;
        switch (scheme.toLowerCase(Locale.ROOT)) {
            case "http":
            case "https":
            case "about":
            case "blob":
            case "data":
            case "javascript":
            case "file":
                return true;
            default:
                return false;
        }
    }

    /** Opens a non-web link in the app that handles it. Returns true when it was dealt with. */
    static boolean open(Context context, Uri uri) {
        if (uri == null || isWebScheme(uri.getScheme())) return false;
        if ("intent".equalsIgnoreCase(uri.getScheme())) {
            openIntentUri(context, uri.toString());
        } else {
            start(context, new Intent(Intent.ACTION_VIEW, uri), null);
        }
        return true;
    }

    /** Opens a web address in the phone's browser, outside the app. */
    static void openInBrowser(Context context, Uri uri) {
        start(context, new Intent(Intent.ACTION_VIEW, uri).addCategory(Intent.CATEGORY_BROWSABLE), null);
    }

    private static void openIntentUri(Context context, String url) {
        Intent intent;
        try {
            intent = Intent.parseUri(url, Intent.URI_INTENT_SCHEME);
        } catch (Exception e) {
            notice(context);
            return;
        }
        // A web page must only reach what a browser could: never a specific
        // internal component of this or another app.
        intent.addCategory(Intent.CATEGORY_BROWSABLE);
        intent.setComponent(null);
        intent.setSelector(null);

        String fallback = intent.getStringExtra("browser_fallback_url");
        String pkg = intent.getPackage();
        Intent backup = null;
        if (fallback != null && (fallback.startsWith("https://") || fallback.startsWith("http://"))) {
            backup = new Intent(Intent.ACTION_VIEW, Uri.parse(fallback));
        } else if (pkg != null) {
            backup = new Intent(Intent.ACTION_VIEW, Uri.parse("market://details?id=" + pkg));
        }
        start(context, intent, backup);
    }

    private static void start(Context context, Intent intent, Intent backup) {
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        try {
            context.startActivity(intent);
        } catch (ActivityNotFoundException e) {
            if (backup != null) {
                start(context, backup, null);
            } else {
                notice(context);
            }
        } catch (SecurityException e) {
            notice(context);
        }
    }

    private static void notice(Context context) {
        Toast.makeText(context, R.string.no_app_for_link, Toast.LENGTH_SHORT).show();
    }
}
