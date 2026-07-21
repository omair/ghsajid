/** Urdu uses Extended Arabic-Indic digits; the archive should too. */
const DIGITS = ["۰", "۱", "۲", "۳", "۴", "۵", "۶", "۷", "۸", "۹"];

export function urduNumber(value: number | string): string {
  return String(value).replace(/\d/g, (d) => DIGITS[Number(d)]);
}
