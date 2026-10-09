import { useSyncExternalStore } from 'react';
import translations from './translations.json';

export type Language = 'de' | 'en' | 'nl';
export type LanguageMode = Language | 'auto';
const storageKey = 'teslatalk-language';
const catalog: Record<string, { en: string; nl: string }> = translations;
const valid = (value: unknown): value is LanguageMode => ['auto', 'de', 'en', 'nl'].includes(String(value));
export function detectLanguage(languages: readonly string[]): Language {
  for (const language of languages) {
    const base = language.toLowerCase().split(/[-_]/)[0];
    if (base === 'de' || base === 'en' || base === 'nl') return base;
  }
  return 'en';
}
function readMode(): LanguageMode {
  try { const value = localStorage.getItem(storageKey); return valid(value) ? value : 'auto'; } catch { return 'auto'; }
}
let mode = readMode();
let detectedLanguage = detectLanguage(navigator.languages?.length ? navigator.languages : [navigator.language]);
let language = resolveLanguage();
const listeners = new Set<() => void>();
const reverse = new Map<string, string>();
for (const [key, values] of Object.entries(catalog)) {
  if (!key.includes('{')) for (const value of Object.values(values)) reverse.set(value, key);
}
const patterns: { key: string; names: string[]; expression: RegExp }[] = [];
for (const [key, values] of Object.entries(catalog)) {
  if (!key.includes('{')) continue;
  for (const template of [key, values.en, values.nl]) {
    const names: string[] = [];
    let cursor = 0, expression = '^';
    for (const match of template.matchAll(/\{(\w+)\}/g)) {
      expression += template.slice(cursor, match.index).replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '(.*?)';
      names.push(match[1]); cursor = match.index! + match[0].length;
    }
    expression += template.slice(cursor).replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '$';
    patterns.push({ key, names, expression: new RegExp(expression) });
  }
}
function resolveLanguage(): Language { return mode === 'auto' ? detectedLanguage : mode; }
export const getLanguage = () => language;
export const getDetectedLanguage = () => detectedLanguage;
export const getLanguageMode = () => mode;
export const getLocale = () => ({ de: 'de-DE', en: 'en-GB', nl: 'nl-NL' })[language];
function update() {
  detectedLanguage = detectLanguage(navigator.languages?.length ? navigator.languages : [navigator.language]);
  language = resolveLanguage();
  document.documentElement.lang = language;
  document.title = t('TeslaTalk – Gemeinsam unterwegs');
  const description = document.querySelector('meta[name="description"]');
  description?.setAttribute('content', t('Sprechfunk, Live-Karte und Gruppenfahrten mit deinen Freunden.'));
  listeners.forEach(listener => listener());
}
export function setLanguageMode(value: LanguageMode) {
  if (!valid(value)) return;
  mode = value;
  try { localStorage.setItem(storageKey, value); } catch { /* The choice still works for this session. */ }
  update();
}
window.addEventListener('languagechange', update);
window.addEventListener('storage', event => { if (event.key === storageKey || event.key === null) { mode = readMode(); update(); } });
const subscribe = (listener: () => void) => { listeners.add(listener); return () => { listeners.delete(listener); }; };
export const useLanguage = () => useSyncExternalStore(subscribe, () => `${mode}:${language}:${detectedLanguage}`);

/** Only translate application messages. Never pass names, chat messages or API identifiers here. */
export function t(source: string | null | undefined, params?: Record<string, string | number | null | undefined>): string {
  if (source == null) return '';
  const key = source.replace(/\s+/g, ' ').trim();
  let canonical = catalog[key] ? key : reverse.get(key) || key;
  if (!catalog[canonical] && !params && key.length <= 2000) {
    for (const pattern of patterns) {
      const match = pattern.expression.exec(key);
      if (!match) continue;
      canonical = pattern.key;
      params = Object.fromEntries(pattern.names.map((name, index) => [name, match[index + 1]]));
      // The proxy appends an application status message; other placeholders
      // contain names, addresses or measurements and must stay untouched.
      if (canonical === 'Tesla/Proxy HTTP {0}: {1}') params['1'] = t(String(params['1']));
      break;
    }
  }
  const entry = catalog[canonical];
  let value = entry ? (language === 'de' ? canonical : entry[language]) : source;
  if (params) value = value.replace(/\{(\w+)\}/g, (token, name: string) => params[name] === undefined ? token : String(params[name] ?? ''));
  if (entry) value = (source.match(/^\s*/)?.[0] || '') + value + (source.match(/\s*$/)?.[0] || '');
  return value;
}
update();
