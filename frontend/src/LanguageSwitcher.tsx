import { Globe } from 'lucide-react';
import { useId } from 'react';
import { getDetectedLanguage, getLanguageMode, setLanguageMode, t, useLanguage, type LanguageMode } from './i18n';

export default function LanguageSwitcher() {
  useLanguage();
  const id = useId();
  const names = { de: 'Deutsch', en: 'English', nl: 'Nederlands' };
  return <section className="panel language-settings" aria-label={t('Sprache')}>
    <div className="panel-heading"><Globe size={21} aria-hidden="true" /><h3>{t('Sprache')}</h3></div>
    <p>{t('Automatisch verwendet die Sprache deines Handys oder Browsers. Deine Auswahl wird auf diesem Gerät gespeichert.')}</p>
    <label className="field" htmlFor={id}><span>{t('Anzeigesprache')}</span>
    <select id={id} value={getLanguageMode()} onChange={event => setLanguageMode(event.target.value as LanguageMode)}>
      <option value="auto">{t('Automatisch')} · {names[getDetectedLanguage()]}</option>
      <option value="de">Deutsch</option><option value="en">English</option><option value="nl">Nederlands</option>
    </select>
    </label>
  </section>;
}
