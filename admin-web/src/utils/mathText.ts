export type MathTextToken =
  | { type: 'text'; text: string }
  | { type: 'var'; base: string; subscript: string }
  | { type: 'operator'; text: string };

const SUBSCRIPT_DIGITS: Record<string, string> = {
  '₀': '0',
  '₁': '1',
  '₂': '2',
  '₃': '3',
  '₄': '4',
  '₅': '5',
  '₆': '6',
  '₇': '7',
  '₈': '8',
  '₉': '9',
};

const INTERNAL_PLACEHOLDERS = new Set(['undefined', 'null', '[object object]', 'question stem', 'stem']);
const COMPARISON_OPERATORS = new Set(['<', '>', '≤', '≥', '=', '≈']);

export function mathTextToString(value: unknown, fallback = '') {
  if (value === null || value === undefined) return fallback;
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  if (typeof value !== 'string') return fallback;
  const text = value.trim();
  if (!text || INTERNAL_PLACEHOLDERS.has(text.toLowerCase())) return fallback;
  return text;
}

export function normalizeMathNotation(value: unknown) {
  return tokenizeMathText(value)
    .map((token) => {
      if (token.type === 'var') return `${token.base}_{${token.subscript}}`;
      if (token.type === 'operator') return ` ${token.text} `;
      return token.text;
    })
    .join('')
    .replace(/\s+/g, ' ')
    .trim();
}

export function hasMathNotation(value: unknown) {
  return tokenizeMathText(value).some((token) => token.type !== 'text');
}

export function tokenizeMathText(value: unknown, fallback = ''): MathTextToken[] {
  const text = mathTextToString(value, fallback);
  if (!text) return [];

  const tokens: MathTextToken[] = [];
  let buffer = '';
  let index = 0;

  const flush = () => {
    if (!buffer) return;
    tokens.push({ type: 'text', text: buffer });
    buffer = '';
  };

  while (index < text.length) {
    const char = text[index];

    if (COMPARISON_OPERATORS.has(char)) {
      flush();
      tokens.push({ type: 'operator', text: char });
      index += 1;
      continue;
    }

    const variable = matchVariableAt(text, index);
    if (variable) {
      flush();
      tokens.push({ type: 'var', base: variable.base, subscript: variable.subscript });
      index = variable.end;
      continue;
    }

    buffer += char;
    index += 1;
  }

  flush();
  return tokens;
}

function matchVariableAt(text: string, index: number): { base: string; subscript: string; end: number } | null {
  if (!isBoundaryBefore(text, index)) return null;

  const explicitBraces = /^([A-Z])_\{([0-9]{1,3})\}/u.exec(text.slice(index));
  if (explicitBraces) {
    const end = index + explicitBraces[0].length;
    return isBoundaryAfter(text, end) ? { base: explicitBraces[1], subscript: explicitBraces[2], end } : null;
  }

  const explicitUnderscore = /^([A-Z])_([0-9]{1,3})/u.exec(text.slice(index));
  if (explicitUnderscore) {
    const end = index + explicitUnderscore[0].length;
    return isBoundaryAfter(text, end) ? { base: explicitUnderscore[1], subscript: explicitUnderscore[2], end } : null;
  }

  const unicodeSubscript = /^([A-Z])([₀₁₂₃₄₅₆₇₈₉]{1,3})/u.exec(text.slice(index));
  if (unicodeSubscript) {
    const end = index + unicodeSubscript[0].length;
    if (!isBoundaryAfter(text, end)) return null;
    return {
      base: unicodeSubscript[1],
      subscript: unicodeSubscript[2].split('').map((digit) => SUBSCRIPT_DIGITS[digit] || digit).join(''),
      end,
    };
  }

  const plain = /^([A-Z])([0-9]{1,3})(?![0-9])/u.exec(text.slice(index));
  if (!plain) return null;

  const end = index + plain[0].length;
  if (!isBoundaryAfter(text, end)) return null;
  if (!shouldRenderPlainVariable(text, index, plain[1], plain[2], end)) return null;

  return { base: plain[1], subscript: plain[2], end };
}

function shouldRenderPlainVariable(text: string, index: number, base: string, subscript: string, end: number) {
  if (base === 'R' && subscript.length >= 2) return true;

  const context = text.slice(Math.max(0, index - 8), Math.min(text.length, end + 8));
  if (/[<>≤≥=≈]/u.test(context)) return true;
  if (/[、,，]/u.test(context) && countPlainVariableLike(text) >= 2) return true;
  if (/分别以|表示|大小关系|关系式|排序/u.test(text) && countPlainVariableLike(text) >= 1) return true;

  return false;
}

function countPlainVariableLike(text: string) {
  return Array.from(text.matchAll(/(^|[^A-Za-z0-9_/])([A-Z])([0-9]{1,3})(?=$|[^A-Za-z0-9])/gu)).length;
}

function isBoundaryBefore(text: string, index: number) {
  if (index === 0) return true;
  return !/[A-Za-z0-9_/]/u.test(text[index - 1]);
}

function isBoundaryAfter(text: string, index: number) {
  if (index >= text.length) return true;
  return !/[A-Za-z0-9_}]/u.test(text[index]);
}
