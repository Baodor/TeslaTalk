import { t } from './i18n';
import { useEffect, useRef, useState } from 'react';
import { Car, Wind, X } from 'lucide-react';
import { api, ApiError } from './api';
import LanguageSwitcher from './LanguageSwitcher';

type Action = 'frunk_open' | 'rear_trunk_toggle' | 'windows_vent' | 'windows_close' | 'climate_on' | 'climate_off';
type CarControl = {user_id:string;vehicle_id:string;display_name:string;vehicle_name:string;allowed:boolean;available:boolean;demo:boolean};
export type ControlOverview = {vehicles:CarControl[];configured:boolean;actions:Action[]};
type Result = {request_id:string;status:string;vehicles:(CarControl & {status:string;message:string})[]};
const labels:Record<Action,string> = {frunk_open:'Frunk öffnen',rear_trunk_toggle:'Heckklappe betätigen',windows_vent:'Fenster lüften',windows_close:'Fenster schließen',climate_on:'Klima an',climate_off:'Klima aus'};
const statuses:Record<string,string> = {accepted:'Bestätigt',demo:'Demo',skipped:'Übersprungen',error:'Fehlgeschlagen',unknown:'Ergebnis unklar',pending:'Noch offen'};

export function VehicleControlConsent({tripId,userId,active,driver,overview,update}: {
  tripId:string;userId:string;active:boolean;driver:boolean;overview:ControlOverview|null|undefined;update:(value:ControlOverview)=>void;
}) {
  const [busy,setBusy] = useState(false),[error,setError] = useState('');
  const working = useRef(false), mine = overview?.vehicles.find(car=>car.user_id===userId);
  if(!driver||!active||!mine)return null;
  async function consent() {
    if(working.current||!mine)return;working.current=true;setBusy(true);setError('');
    try {update(await api(`/api/trips/${tripId}/controls/consent`,mine.allowed?'DELETE':'POST'));}
    catch(error) {setError((error as Error).message);} finally {working.current=false;setBusy(false);}
  }
  return <section className="control-consent" aria-label={t("Freigabe meines Fahrzeugs")}>
    <p>{t("Du bestimmst, ob der Fahrtleiter Frunk, Heckklappe, Fenster und Klima deines Autos während dieser Fahrt steuern darf. Die Freigabe gilt nur für ")}<strong>{mine.vehicle_name}</strong>.</p>
    <button disabled={busy||!mine.available&&!mine.allowed} aria-pressed={mine.allowed} className={mine.allowed?'selected':''} onClick={()=>void consent()}>{mine.allowed?t("Komfortsteuerung für mein Auto widerrufen"):t("Komfortsteuerung für mein Auto erlauben")}</button>
    {!mine.available&&<small>{t("Die Fahrzeugsteuerung ist vom Betreiber noch nicht aktiviert.")}</small>}
    {error&&<p className="error" role="alert">{t(error)}</p>}
  </section>;
}

export default function VehicleControls({tripId,userId,leader,active,driver,overview,update}: {
  tripId:string;userId:string;leader:boolean;active:boolean;driver:boolean;overview:ControlOverview|null|undefined;update:(value:ControlOverview)=>void;
}) {
  const [busy,setBusy] = useState(false),[error,setError] = useState('');
  const [pending,setPending] = useState<{action:Action;cars:CarControl[];requestId:string}|null>(null);
  const [result,setResult] = useState<Result|null>(null),[uncertain,setUncertain] = useState<string|null>(null);
  const working = useRef(false), dialog = useRef<HTMLDialogElement>(null);
  useEffect(()=>{if(pending)dialog.current?.showModal();},[pending]);
  const cars=overview?.vehicles||[],allowed=cars.filter(car=>car.allowed&&car.available);
  if(!leader||!driver)return null;
  if(!active||!overview)return <section className="panel vehicle-controls" aria-label={t("Komfortsteuerung der Gruppe")}><div className="panel-heading"><Car size={21}/><h3>{t("Fahrzeugsteuerung")}</h3></div><p>{t("Die Fahrzeugsteuerung ist nur während einer aktiven Fahrt verfügbar.")}</p></section>;
  async function send() {
    if(!pending||working.current)return;working.current=true;setBusy(true);setError('');setResult(null);
    const command=pending;
    try {
      setResult(await api(`/api/trips/${tripId}/controls`,'POST',{request_id:command.requestId,action:command.action,vehicle_ids:command.cars.map(car=>car.vehicle_id)}));
      setUncertain(null);
    } catch(error) {
      setError((error as Error).message);
      setUncertain(!(error instanceof ApiError)||error.status>=500?command.requestId:null);
      try {const detail=await api(`/api/trips/${tripId}`);if(detail.vehicle_controls)update(detail.vehicle_controls);}catch{}
    }
    finally {setPending(null);working.current=false;setBusy(false);}
  }
  async function checkResult() {
    if(!uncertain||working.current)return;working.current=true;setBusy(true);setError('');
    try {const data=await api<Result>(`/api/trips/${tripId}/controls/${uncertain}`);setResult(data);if(data.status==='completed')setUncertain(null);}
    catch(error) {setError((error as Error).message);} finally {working.current=false;setBusy(false);}
  }
  return <section className="panel vehicle-controls" aria-label={t("Komfortsteuerung der Gruppe")}>
    <div className="panel-heading"><Car size={21}/><h3>{t("Fahrzeugsteuerung")}</h3></div>
    <VehicleControlConsent tripId={tripId} userId={userId} active={active} driver={driver} overview={overview} update={update}/>
    <div className="stack"><p><strong>{allowed.length} {t(" von ")}{cars.length} {t(" Fahrzeugen freigegeben.")}</strong> {t(" Jede Aktion betrifft die unten angezeigten freigegebenen Autos.")}</p>
      <ul className="control-cars">{cars.map(car=><li key={car.vehicle_id}><strong>{car.display_name} · {car.vehicle_name}</strong><span>{car.demo?t("Demo · "):''}{car.allowed?t("Freigegeben"):t("Keine Freigabe")}</span></li>)}</ul>
      <div className="control-buttons">{Object.entries(labels).map(([action,label])=><button key={action} disabled={busy||allowed.length===0||uncertain!==null} onClick={()=>{setPending({action:action as Action,cars:[...allowed],requestId:crypto.randomUUID()});setError('');}}>{action.startsWith('climate')&&<Wind size={17}/>} {t(label)}</button>)}</div>
      <p className="hint">{t("Frunk, Heckklappe und Fenster nur bei aktuell bestätigter Parkstellung. „Heckklappe betätigen“ öffnet oder schließt entsprechend der aktuellen Position; Unterstützung hängt vom Fahrzeug ab. Der Frunk wird von Hand geschlossen. Fenster können gelüftet werden. Klima nutzt die im Auto eingestellte Temperatur.")}</p>
    </div>
    {error&&<p className="error" role="alert">{t(error)}</p>}
    {uncertain&&<div className="notice"><span>{t("Ergebnis bitte am Auto prüfen. Der Befehl wird nicht automatisch wiederholt.")}</span><button disabled={busy} onClick={()=>void checkResult()}>{t("Auftragsstatus abrufen")}</button></div>}
    {result&&<div role="status" aria-label={t("Ergebnisse der Fahrzeugsteuerung")}><ul>{result.vehicles.map(car=><li key={car.vehicle_id}><strong>{car.display_name} · {car.vehicle_name}: {t(statuses[car.status]||car.status)}</strong><p>{t(car.message)}</p></li>)}</ul></div>}
    {pending&&<dialog ref={dialog} className="modal" aria-labelledby="comfort-confirm-title" onCancel={event=>{if(busy)event.preventDefault();else setPending(null);}}>
      <LanguageSwitcher inline />
      <header><h2 id="comfort-confirm-title">{t(labels[pending.action])} {t(" für die Gruppe?")}</h2><button className="icon-button" aria-label={t("Schließen")} disabled={busy} onClick={()=>setPending(null)}><X size={21}/></button></header>
      <p>{t("Diese Aktion wird an ")}{pending.cars.length} {t(" freigegebene Fahrzeuge gesendet:")}</p><ul>{pending.cars.map(car=><li key={car.vehicle_id}>{car.display_name} · {car.vehicle_name}{car.demo?t(" (nur Demo)"):''}</li>)}</ul>
      <p>{t("Prüfe, dass die Aktion bei allen aufgeführten Autos jetzt gewünscht ist und die beweglichen Teile frei sind.")}</p>
      <div className="header-actions"><button disabled={busy} onClick={()=>setPending(null)}>{t("Abbrechen")}</button><button className="primary" disabled={busy} onClick={()=>void send()}>{busy?t("Wird gesendet …"):t("Jetzt an diese Fahrzeuge senden")}</button></div>
    </dialog>}
  </section>;
}
