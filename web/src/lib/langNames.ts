// Full, human-readable language names for every code the voices can return —
// so filters and badges never show cryptic shortcuts like "es-ES" or "ta".

const LANG_NAMES: Record<string, string> = {
  ar: 'Arabic', as: 'Assamese', bho: 'Bhojpuri', bn: 'Bengali', brx: 'Bodo',
  ca: 'Catalan', cs: 'Czech', da: 'Danish', de: 'German', doi: 'Dogri',
  el: 'Greek', en: 'English', es: 'Spanish', fa: 'Persian', fi: 'Finnish',
  fr: 'French', gu: 'Gujarati', he: 'Hebrew', hi: 'Hindi', hne: 'Chhattisgarhi',
  hu: 'Hungarian', is: 'Icelandic', it: 'Italian', ja: 'Japanese', ka: 'Georgian',
  kn: 'Kannada', ko: 'Korean', lv: 'Latvian', ml: 'Malayalam', mni: 'Manipuri',
  mr: 'Marathi', ms: 'Malay', nb: 'Norwegian', ne: 'Nepali', nl: 'Dutch',
  no: 'Norwegian', or: 'Odia', pa: 'Punjabi', pl: 'Polish', pt: 'Portuguese',
  ro: 'Romanian', ru: 'Russian', sa: 'Sanskrit', sk: 'Slovak', sl: 'Slovenian',
  sr: 'Serbian', sv: 'Swedish', sw: 'Swahili', ta: 'Tamil', te: 'Telugu',
  tr: 'Turkish', uk: 'Ukrainian', vi: 'Vietnamese', zh: 'Chinese',
};

// Country names for the few languages that ship in multiple regional accents.
const REGION_NAMES: Record<string, string> = {
  US: 'United States', GB: 'United Kingdom', IN: 'India', ES: 'Spain',
  MX: 'Mexico', AR: 'Argentina', BR: 'Brazil', PT: 'Portugal', CN: 'China',
};
const MULTI_REGION = new Set(['en', 'es', 'pt']);

/** "es-ES" -> "Spanish (Spain)", "hi-IN" -> "Hindi", "ta" -> "Tamil" */
export function langLabel(code: string): string {
  const [base, region] = String(code || '').split('-');
  const name = LANG_NAMES[base] ?? (base ? base.toUpperCase() : 'Unknown');
  const reg =
    region && MULTI_REGION.has(base) ? ` (${REGION_NAMES[region] ?? region})` : '';
  return name + reg;
}
