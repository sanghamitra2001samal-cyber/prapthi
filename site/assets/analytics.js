/* Google Analytics 4 for prapthi.ai. Put the property's Measurement ID
   ("G-…") in ID; while it is empty nothing is loaded and nothing is sent.
   Cookies and analytics are described in /privacy section 6, so change
   both together. */
(function () {
  var ID = "G-58J4V19PS9";
  // The Android app opens these pages too. Its Play data-safety answers declare
  // no analytics, so it stays out ("PrapthiApp", mobile/capacitor.config.json).
  if (!ID || /PrapthiApp\//.test(navigator.userAgent)) return;
  window.dataLayer = window.dataLayer || [];
  window.gtag = function () { window.dataLayer.push(arguments); };
  // Analytics only. /privacy says we use no advertising cookies; without this
  // the tag also sets Google Ads cookies (_gcl_au) and calls doubleclick.net.
  window.gtag("consent", "default", {
    analytics_storage: "granted",
    ad_storage: "denied",
    ad_user_data: "denied",
    ad_personalization: "denied"
  });
  window.gtag("js", new Date());
  window.gtag("config", ID, {
    allow_google_signals: false,
    allow_ad_personalization_signals: false
  });
  var s = document.createElement("script");
  s.async = true;
  s.src = "https://www.googletagmanager.com/gtag/js?id=" + ID;
  document.head.appendChild(s);
})();
