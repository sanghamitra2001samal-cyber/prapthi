import { useEffect, useRef, useState } from 'react';
import Hls from 'hls.js';

/* ------------------------------------------------------------------ */
/*  HlsVideo — a full-bleed autoplaying HLS (.m3u8) video background.  */
/*                                                                    */
/*  Safari plays HLS natively; every other browser needs Media Source */
/*  Extensions via hls.js. This component picks the right path,        */
/*  autoplays muted+looping (so it never needs a gesture), and calls   */
/*  onReady once frames are flowing / onError if the stream fails —    */
/*  so the caller can keep an animated gradient fallback underneath.   */
/* ------------------------------------------------------------------ */
export default function HlsVideo({
  src,
  className = '',
  onReady,
  onError,
}: {
  src: string;
  className?: string;
  onReady?: () => void;
  onError?: () => void;
}) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [, setLoaded] = useState(false);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;

    const ready = () => {
      setLoaded(true);
      onReady?.();
    };
    const fail = () => onError?.();

    // Safari / iOS: native HLS — just point src at the playlist.
    if (video.canPlayType('application/vnd.apple.mpegurl')) {
      video.src = src;
      video.addEventListener('loadeddata', ready);
      video.addEventListener('error', fail);
      video.play().catch(() => {});
      return () => {
        video.removeEventListener('loadeddata', ready);
        video.removeEventListener('error', fail);
      };
    }

    // Everyone else: hls.js over Media Source Extensions.
    if (Hls.isSupported()) {
      const hls = new Hls({ enableWorker: true, lowLatencyMode: false });
      hls.loadSource(src);
      hls.attachMedia(video);
      hls.on(Hls.Events.MANIFEST_PARSED, () => {
        video.play().catch(() => {});
      });
      video.addEventListener('loadeddata', ready);
      hls.on(Hls.Events.ERROR, (_e, data) => {
        if (data.fatal) fail();
      });
      return () => {
        video.removeEventListener('loadeddata', ready);
        hls.destroy();
      };
    }

    // No HLS support at all — signal the caller to keep its fallback.
    fail();
  }, [src, onReady, onError]);

  return (
    <video
      ref={videoRef}
      className={className}
      muted
      loop
      autoPlay
      playsInline
      preload="auto"
      aria-hidden
    />
  );
}
