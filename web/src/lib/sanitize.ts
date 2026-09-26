// Strip styles/markup from pasted rich text (FR-3) and treat text as data.

// Invisible / zero-width control characters to remove (built via codepoints
// so no literal invisible glyphs live in the source).
const INVISIBLE = new RegExp(
  '[' +
    [0x00, 0x08, 0x0b, 0x0c, 0x0e, 0x1f, 0x200b, 0x200d, 0xfeff]
      .map((c) => '\\u' + c.toString(16).padStart(4, '0'))
      .join('') +
    ']',
  'g'
);

export function sanitizePaste(input: string): string {
  // Collapse excessive whitespace but preserve paragraph breaks, and drop
  // zero-width / invisible control characters.
  return input
    .replace(/\r\n/g, '\n')
    .replace(/[ \t]+\n/g, '\n')
    .replace(/\n{3,}/g, '\n\n')
    .replace(INVISIBLE, '');
}

export const CHAR_CAP = 5000;

export function wordCount(text: string): number {
  const t = text.trim();
  return t ? t.split(/\s+/).length : 0;
}
