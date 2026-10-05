import { useEffect, useState } from 'react';
import { ArrowLeft, Copy, Check, Download, Search, X } from 'lucide-react';
import { api, ApiError } from './api';

type Endpoint = { method: string; path: string; group: string; description: string; access: string; returns: string;
  parameters: unknown[]; request_body: unknown; responses: unknown; operation_id: string | null };
type Catalog = { title: string; version: string; base_url: string; rules: string[]; endpoints: Endpoint[]; examples: unknown; openapi: any };
export function llmContext(catalog: Catalog) {
  return 'TeslaTalk API – vollständiger Integrationskontext\n'+
    'Nutze ausschließlich die dokumentierten Endpunkte und beachte Rechte und Zeitgrenzen. '+
    'Alle Zugangsdaten sind Platzhalter. Dieser Text enthält keine echten Schlüssel oder privaten Kontodaten. '+
    'Führe keine Aufrufe ohne ausdrücklichen Auftrag aus. JSON-Schema-Referenzen werden in openapi.components.schemas aufgelöst.\n\n'+JSON.stringify(catalog, null, 2);
}

export default function ApiDocs() {
  const [catalog, setCatalog] = useState<Catalog | null>(null), [error, setError] = useState(''), [login, setLogin] = useState(false);
  const [query, setQuery] = useState(''), [group, setGroup] = useState(''), [copied, setCopied] = useState(false), [fallback, setFallback] = useState(false);
  useEffect(() => {
    let stopped = false;
    void api<Catalog>('/api/docs').then(data => { if (!stopped) setCatalog(data); }).catch(error => {
      if (!stopped) { setError(error.message); setLogin(error instanceof ApiError && error.status === 401); }
    });
    return () => { stopped = true; };
  }, []);
  async function copyAll() {
    if (!catalog) return;
    try {
      if (!navigator.clipboard?.writeText) throw new Error('Clipboard unavailable');
      // The complete context is ready before the tap, including on iOS.
      await navigator.clipboard.writeText(llmContext(catalog));
      setCopied(true);
    } catch { setFallback(true); }
  }
  function download() {
    if (!catalog) return;
    const url = URL.createObjectURL(new Blob([llmContext(catalog)], { type: 'text/plain;charset=utf-8' }));
    const link = document.createElement('a'); link.href = url; link.download = 'teslatalk-api-llm.txt'; link.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  const groups = [...new Set(catalog?.endpoints.map(endpoint => endpoint.group))];
  const filtered = catalog?.endpoints.filter(endpoint => (!group || endpoint.group === group) &&
    `${endpoint.method} ${endpoint.path} ${endpoint.description} ${endpoint.returns}`.toLocaleLowerCase().includes(query.toLocaleLowerCase())) || [];
  return <main className="api-docs-layout">
    <a className="back-button" href="/"><ArrowLeft size={16} />Zurück zu TeslaTalk</a>
    <header className="page-header"><div><span className="eyebrow">INTEGRATIONEN</span><h1>API-Dokumentation<span className="accent">.</span></h1>
      <p>Alle Endpunkte mit Funktion, Zugriff, Parametern und Schemas. Der Kopierbutton enthält die gesamte Dokumentation – auch bei aktiven Filtern.</p></div></header>
    {error && <section className="panel"><p className="error" role="alert">{error}</p>{login ? <a className="button primary" href="/">Mit Fahrerkonto anmelden</a> : <button onClick={() => location.reload()}>Erneut versuchen</button>}</section>}
    {!catalog && !error && <p role="status">API-Dokumentation wird geladen …</p>}
    {catalog && <>
      <section className="panel api-docs-intro" aria-label="API-Informationen">
        <div><strong>{catalog.endpoints.length} Endpunkte · Version {catalog.version}</strong><p><code>{catalog.base_url}</code></p></div>
        <div className="header-actions"><button className="primary" onClick={() => void copyAll()}>{copied ? <Check size={17} /> : <Copy size={17} />}{copied ? 'Alle Informationen kopiert' : 'Alle Informationen für ein LLM kopieren'}</button>
          <button onClick={download}><Download size={17} />Text herunterladen</button><a className="button" href="/api/openapi.json" target="_blank" rel="noreferrer">OpenAPI JSON</a></div>
        <p className="hint" role="status">{copied ? 'Vollständiger Kontext mit allen Endpunkten, Regeln, Beispielen und Schemas ist in der Zwischenablage.' : 'Enthält keine persönlichen API-Schlüssel, Sitzungen oder Fahrzeugdaten.'}</p>
      </section>
      {fallback && <section className="panel" aria-label="LLM-Kontext manuell kopieren"><div className="panel-heading"><h3>Manuell kopieren</h3><button className="icon-button" aria-label="Kopiertext schließen" onClick={() => setFallback(false)}><X size={18} /></button></div>
        <p>Der Browser erlaubt hier keinen direkten Zugriff auf die Zwischenablage. Wähle den vollständigen Text aus und kopiere ihn; alternativ kannst du ihn herunterladen.</p>
        <textarea className="llm-copy-text" aria-label="Vollständiger LLM-Kontext" value={llmContext(catalog)} readOnly onFocus={event => event.currentTarget.select()} />
      </section>}
      <section className="panel"><h2>Aufrufregeln</h2><ul className="api-rules">{catalog.rules.map(rule => <li key={rule}>{rule}</li>)}</ul></section>
      <div className="api-docs-filter"><label className="field"><span><Search size={16} />Endpunkte suchen</span><input value={query} onChange={event => setQuery(event.target.value)} placeholder="z. B. navigation, GET, Push" /></label>
        <label className="field"><span>Bereich</span><select value={group} onChange={event => setGroup(event.target.value)}><option value="">Alle Bereiche</option>{groups.map(group => <option key={group}>{group}</option>)}</select></label></div>
      <p role="status">{filtered.length} von {catalog.endpoints.length} Endpunkten angezeigt</p>
      <div className="api-endpoints">{filtered.map(endpoint => <article className="panel api-endpoint" key={endpoint.method+endpoint.path}>
        <div className="api-endpoint-heading"><span className="badge accent-badge">{endpoint.method}</span><code>{endpoint.path}</code><small>{endpoint.group}</small></div>
        <h3>{endpoint.description}</h3><p><strong>Zugriff:</strong> {endpoint.access}</p><p><strong>Antwort und Verhalten:</strong> {endpoint.returns}</p>
        <details><summary>Parameter, Anfrage und Antwortschema</summary><pre>{JSON.stringify({ parameters: endpoint.parameters, request_body: endpoint.request_body, responses: endpoint.responses }, null, 2)}</pre></details>
      </article>)}</div>
      <section className="panel"><h2>Beispiele und Datentypen</h2><details><summary>Aufrufbeispiele mit Platzhaltern</summary><pre>{JSON.stringify(catalog.examples, null, 2)}</pre></details>
        <details><summary>Alle JSON-Schema-Definitionen</summary><pre>{JSON.stringify(catalog.openapi.components?.schemas || {}, null, 2)}</pre></details></section>
    </>}
  </main>;
}
