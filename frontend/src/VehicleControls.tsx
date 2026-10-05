import { useEffect, useRef, useState } from 'react';
import { Car, SlidersHorizontal, Wind, X } from 'lucide-react';
import { api, ApiError } from './api';

type Action = 'frunk_open' | 'rear_trunk_toggle' | 'windows_vent' | 'windows_close' | 'climate_on' | 'climate_off';
type CarControl = {user_id:string;vehicle_id:string;display_name:string;vehicle_name:string;allowed:boolean;available:boolean;demo:boolean};
export type ControlOverview = {vehicles:CarControl[];configured:boolean;actions:Action[]};
type Result = {request_id:string;status:string;vehicles:(CarControl & {status:string;message:string})[]};
const labels:Record<Action,string> = {frunk_open:'Frunk öffnen',rear_trunk_toggle:'Heckklappe betätigen',windows_vent:'Fenster lüften',windows_close:'Fenster schließen',climate_on:'Klima an',climate_off:'Klima aus'};
const statuses:Record<string,string> = {accepted:'Bestätigt',demo:'Demo',skipped:'Übersprungen',error:'Fehlgeschlagen',unknown:'Ergebnis unklar',pending:'Noch offen'};

export default function VehicleControls({tripId,userId,leader,active,driver,overview,update}: {
  tripId:string;userId:string;leader:boolean;active:boolean;driver:boolean;overview:ControlOverview|null|undefined;update:(value:ControlOverview)=>void;
}) {
  const [open,setOpen] = useState(false),[busy,setBusy] = useState(false),[error,setError] = useState('');
  const [pending,setPending] = useState<{action:Action;cars:CarControl[];requestId:string}|null>(null);
  const [result,setResult] = useState<Result|null>(null),[uncertain,setUncertain] = useState<string|null>(null);
  const working = useRef(false), dialog = useRef<HTMLDialogElement>(null);
  useEffect(()=>{if(pending)dialog.current?.showModal();},[pending]);
  const cars=overview?.vehicles||[],mine=cars.find(car=>car.user_id===userId),allowed=cars.filter(car=>car.allowed&&car.available);
  if(!driver||!active||!overview)return null;
  async function consent() {
    if(working.current||!mine)return;working.current=true;setBusy(true);setError('');
    try {update(await api(`/api/trips/${tripId}/controls/consent`,mine.allowed?'DELETE':'POST'));}
    catch(error) {setError((error as Error).message);} finally {working.current=false;setBusy(false);}
  }
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
  return <section className="panel vehicle-controls" aria-label="Komfortsteuerung der Gruppe">
    <div className="panel-heading"><Car size={21}/><h3>Gemeinsame Fahrzeugsteuerung</h3>{leader&&<button aria-expanded={open} onClick={()=>setOpen(!open)}><SlidersHorizontal size={17}/>Fahrzeuge steuern</button>}</div>
    {mine&&<div className="control-consent"><p>Du bestimmst, ob der Fahrtleiter Frunk, Heckklappe, Fenster und Klima deines Autos während dieser Fahrt steuern darf. Die Freigabe gilt nur für <strong>{mine.vehicle_name}</strong>.</p>
      <button disabled={busy||!mine.available&&!mine.allowed} aria-pressed={mine.allowed} className={mine.allowed?'selected':''} onClick={()=>void consent()}>{mine.allowed?'Komfortsteuerung für mein Auto widerrufen':'Komfortsteuerung für mein Auto erlauben'}</button>
      {!mine.available&&<small>Die Fahrzeugsteuerung ist vom Betreiber noch nicht aktiviert.</small>}
    </div>}
    {leader&&open&&<div className="stack"><p><strong>{allowed.length} von {cars.length} Fahrzeugen freigegeben.</strong> Jede Aktion betrifft die unten angezeigten freigegebenen Autos.</p>
      <ul className="control-cars">{cars.map(car=><li key={car.vehicle_id}><strong>{car.display_name} · {car.vehicle_name}</strong><span>{car.demo?'Demo · ':''}{car.allowed?'Freigegeben':'Keine Freigabe'}</span></li>)}</ul>
      <div className="control-buttons">{Object.entries(labels).map(([action,label])=><button key={action} disabled={busy||allowed.length===0||uncertain!==null} onClick={()=>{setPending({action:action as Action,cars:[...allowed],requestId:crypto.randomUUID()});setError('');}}>{action.startsWith('climate')&&<Wind size={17}/>} {label}</button>)}</div>
      <p className="hint">Frunk, Heckklappe und Fenster nur bei aktuell bestätigter Parkstellung. „Heckklappe betätigen“ öffnet oder schließt entsprechend der aktuellen Position; Unterstützung hängt vom Fahrzeug ab. Der Frunk wird von Hand geschlossen. Fenster können gelüftet werden. Klima nutzt die im Auto eingestellte Temperatur.</p>
    </div>}
    {error&&<p className="error" role="alert">{error}</p>}
    {uncertain&&<div className="notice"><span>Ergebnis bitte am Auto prüfen. Der Befehl wird nicht automatisch wiederholt.</span><button disabled={busy} onClick={()=>void checkResult()}>Auftragsstatus abrufen</button></div>}
    {result&&<div role="status" aria-label="Ergebnisse der Fahrzeugsteuerung"><ul>{result.vehicles.map(car=><li key={car.vehicle_id}><strong>{car.display_name} · {car.vehicle_name}: {statuses[car.status]||car.status}</strong><p>{car.message}</p></li>)}</ul></div>}
    {pending&&<dialog ref={dialog} className="modal" aria-labelledby="comfort-confirm-title" onCancel={event=>{if(busy)event.preventDefault();else setPending(null);}}>
      <header><h2 id="comfort-confirm-title">{labels[pending.action]} für die Gruppe?</h2><button className="icon-button" aria-label="Schließen" disabled={busy} onClick={()=>setPending(null)}><X size={21}/></button></header>
      <p>Diese Aktion wird an {pending.cars.length} freigegebene Fahrzeuge gesendet:</p><ul>{pending.cars.map(car=><li key={car.vehicle_id}>{car.display_name} · {car.vehicle_name}{car.demo?' (nur Demo)':''}</li>)}</ul>
      <p>Prüfe, dass die Aktion bei allen aufgeführten Autos jetzt gewünscht ist und die beweglichen Teile frei sind.</p>
      <div className="header-actions"><button disabled={busy} onClick={()=>setPending(null)}>Abbrechen</button><button className="primary" disabled={busy} onClick={()=>void send()}>{busy?'Wird gesendet …':'Jetzt an diese Fahrzeuge senden'}</button></div>
    </dialog>}
  </section>;
}
