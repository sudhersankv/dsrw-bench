/** Reads design tokens from the stylesheet so canvas drawing and CSS share one palette. */
export function token(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(`--${name}`).trim();
}

export const FONT_BODY = '"Sofia Sans Variable", "Trebuchet MS", sans-serif';
export const FONT_DISPLAY = '"Sofia Sans Extra Condensed Variable", "Arial Narrow", sans-serif';
export const FONT_NAMES = '"Old Standard TT", Georgia, serif';

/** Loads every face the canvas needs before any drawing, so text never falls back mid-render. */
export async function loadCanvasFonts(): Promise<void> {
  await Promise.all([
    document.fonts.load(`700 40px ${FONT_DISPLAY}`),
    document.fonts.load(`800 40px ${FONT_DISPLAY}`),
    document.fonts.load(`400 20px ${FONT_BODY}`),
    document.fonts.load(`600 20px ${FONT_BODY}`),
    document.fonts.load(`italic 400 20px ${FONT_NAMES}`),
  ]);
  await document.fonts.ready;
}

export function escapeHtml(text: string): string {
  return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}
