// Best-effort export for browser voices (FR-21, TRD §7).
//
// The Web Speech API never exposes an audio stream, so there is no clean way
// to record it. The only browser-portable workaround is to capture the tab's
// audio via getDisplayMedia while the utterance plays. This is imperfect and
// browser-dependent (Chrome/Edge support tab-audio capture; Safari does not),
// which is exactly why the PRD recommends the self-hosted voice for real files.

export interface CaptureResult {
  blob: Blob;
  mime: string;
}

export function captureSupported(): boolean {
  return (
    typeof navigator !== 'undefined' &&
    !!navigator.mediaDevices?.getDisplayMedia &&
    typeof MediaRecorder !== 'undefined'
  );
}

/**
 * Records tab audio while `speakFn` runs (which should kick off the
 * SpeechSynthesis utterance). Resolves when speech ends.
 */
export async function captureBrowserSpeech(
  speakFn: () => Promise<void>
): Promise<CaptureResult> {
  if (!captureSupported()) {
    throw new Error('This browser cannot capture browser-voice audio.');
  }

  const stream = await navigator.mediaDevices.getDisplayMedia({
    video: true,
    audio: true,
  });

  const audioTracks = stream.getAudioTracks();
  if (audioTracks.length === 0) {
    stream.getTracks().forEach((t) => t.stop());
    throw new Error(
      'No audio was shared. When prompted, pick the tab and enable "Share tab audio".'
    );
  }

  // Keep only the audio so the recording is small.
  const audioStream = new MediaStream(audioTracks);
  const mime = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
    ? 'audio/webm;codecs=opus'
    : 'audio/webm';
  const recorder = new MediaRecorder(audioStream, { mimeType: mime });
  const chunks: BlobPart[] = [];
  recorder.ondataavailable = (e) => e.data.size && chunks.push(e.data);

  const done = new Promise<CaptureResult>((resolve) => {
    recorder.onstop = () => {
      stream.getTracks().forEach((t) => t.stop());
      resolve({ blob: new Blob(chunks, { type: mime }), mime });
    };
  });

  recorder.start();
  try {
    await speakFn();
  } finally {
    // Small tail so the end of the last word isn't clipped.
    setTimeout(() => recorder.state !== 'inactive' && recorder.stop(), 250);
  }
  return done;
}
