import { Globe } from 'lucide-react';
import { useId } from 'react';
import { getDetectedLanguage, getLanguageMode, setLanguageMode, t, useLanguage, type LanguageMode } from './i18n';

export default function LanguageSwitcher({ inline = false }: { inline?: boolean }) {
  useLanguage();
  const id = useId();
  const names = { de: 'Deutsch', en: 'English', nl: 'Nederlands' };
  return <div className={`language-bar${inline ? ' language-inline' : ''}`}><Globe size={15} aria-hidden="true" />
    <label htmlFor={id}>{t('Sprache')}</label>
    <select id={id} value={getLanguageMode()} onChange={event => setLanguageMode(event.target.value as LanguageMode)}>
      <option value="auto">{t('Automatisch')} · {names[getDetectedLanguage()]}</option>
      <option value="de">Deutsch</option><option value="en">English</option><option value="nl">Nederlands</option>
    </select>
  </div>;
}
