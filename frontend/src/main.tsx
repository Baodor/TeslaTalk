import { t, useLanguage } from './i18n';
import React from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
import LanguageSwitcher from './LanguageSwitcher';
import './styles.css';
class Boundary extends React.Component<{ children: React.ReactNode; language: string }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() { return this.state.failed ? <main className="center"><h1>{t("Anzeige konnte nicht geladen werden.")}</h1><button onClick={() => location.reload()}>{t("Neu laden")}</button></main> : this.props.children; }
}
function Root() {
  const language = useLanguage();
  return <><LanguageSwitcher /><Boundary language={language}><App /></Boundary></>;
}
createRoot(document.getElementById('root')!).render(<Root />);
if ('serviceWorker' in navigator && import.meta.env.PROD) {
  window.addEventListener('load', () => { void navigator.serviceWorker.register('/sw.js', { updateViaCache: 'none' }).catch(() => {}); });
}
