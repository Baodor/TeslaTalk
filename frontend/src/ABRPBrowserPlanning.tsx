import { useState } from 'react';
import QRCode from 'qrcode';
import { t } from './i18n';
import { date } from './api';

type Vehicle={user_id:string;display_name:string;vehicle_name:string;battery_pct?:number|null;range_km?:number|null;updated_at?:number|null};
export type BrowserPlanningProps={userId:string;leader:boolean;finished:boolean;vehicles:Vehicle[];participants:any[];recommendations:{lowest_range_user_id?:string;lowest_battery_user_id?:string}};

// ABRP's published browser supports a destinations JSON query. Its current
// app processes car_model separately and returns before destinations; it has
// no documented compatible SoC query handler. Keep vehicle/account selection
// in ABRP and show the cached TeslaTalk snapshot explicitly, without claiming
// a login, a telemetry connection or an automatic battery synchronization.
export function routeURL(values:string[]) {
  if(values.length<2||values.length>25)throw new Error(t('Bitte Start und Ziel sowie höchstens 23 Zwischenstopps eingeben.'));
  const destinations=values.map(raw=>{
    const value=raw.trim();if(!value||value.length>300)throw new Error(t('Bitte alle Routenpunkte vollständig eingeben.'));
    const parts=value.split(',').map(part=>part.trim());
    if(parts.length===2&&parts.every(part=>part!==''&&!Number.isNaN(Number(part)))) {
      const [lat,lon]=parts.map(Number);
      if(!Number.isFinite(lat+lon)||Math.abs(lat)>90||Math.abs(lon)>180)throw new Error(t('Ungültige Planungskoordinaten.'));
      return {lat,lon};
    }
    return {address:value};
  });
  const url=new URL('https://abetterrouteplanner.com/');
  url.searchParams.set('destinations',JSON.stringify(destinations));
  if(url.href.length>8000)throw new Error(t('Der ABRP-Link ist zu lang. Bitte weniger oder kürzere Routenpunkte verwenden.'));
  return url.href;
}

export default function ABRPBrowserPlanning({userId,leader,finished,vehicles,participants,recommendations}:BrowserPlanningProps) {
  const recommended=recommendations.lowest_range_user_id||recommendations.lowest_battery_user_id||userId;
  const [chosen,setChosen]=useState(vehicles.some(car=>car.user_id===recommended)?recommended:vehicles[0]?.user_id||''),[soc,setSoc]=useState<string|null>(null);
  const [destinations,setDestinations]=useState(['','']),[consent,setConsent]=useState(false);
  const [handoff,setHandoff]=useState<{url:string;qr:string}|null>(null),[error,setError]=useState(''),[notice,setNotice]=useState(''),[busy,setBusy]=useState(false);
  const car=vehicles.find(row=>row.user_id===chosen);
  const charge=soc??(car?.battery_pct!=null?String(car.battery_pct):'');
  const stale=car?.updated_at!=null&&Date.now()/1000-car.updated_at>300;
  function clear(){setHandoff(null);setError('');setNotice('');}
  function point(index:number,value:string){clear();setDestinations(rows=>rows.map((row,i)=>i===index?value:row));}
  function start() {
    const data=participants.find(row=>row.id===chosen)?.data;
    if(!data||!Number.isFinite(data.latitude)||!Number.isFinite(data.longitude)||!Number.isFinite(data.position_updated_at)||Date.now()/1000-data.position_updated_at>300){setError(t('Für dieses Fahrzeug fehlt ein aktueller Browserstandort. Startadresse eingeben.'));return;}
    point(0,`${data.latitude}, ${data.longitude}`);
  }
  async function prepare() {
    if(busy||!car||!consent)return;setBusy(true);setError('');setNotice('');
    try {
      const url=routeURL(destinations);let qr='';
      try {qr=await QRCode.toDataURL(url,{width:300,margin:2,color:{dark:'#101a20',light:'#ffffff'}});}
      catch {setNotice(t('Für diesen langen Link ist kein QR-Code möglich. Den Direktlink verwenden.'));}
      setHandoff({url,qr});
    }catch(error){setError((error as Error).message);}finally{setBusy(false);}
  }
  async function copy(value:string) {
    try {await navigator.clipboard.writeText(value);setNotice(t('Kopiert.'));}
    catch {setNotice(t('Bitte den sichtbaren Wert manuell kopieren.'));}
  }
  if(!leader)return <p>{t('Der Fahrtleiter plant die gemeinsamen Ladehalte. Du kannst deinen eigenen Tesla für die Zielübernahme freigeben.')}</p>;
  if(finished)return null;
  return <section className="panel abrp-browser" aria-label={t('ABRP ohne Planning-Key')}>
    <h3>{t('Mit deinem ABRP-Konto planen')}</h3>
    <p>{t('ABRP im eigenen Konto öffnen und dort mit deinen Ladekarten und Wünschen berechnen. TeslaTalk benötigt dafür keinen Planning-Key.')}</p>
    <div className="abrp-recommendations">{[[t('Geringste Reichweite'),recommendations.lowest_range_user_id],[t('Niedrigster Akku'),recommendations.lowest_battery_user_id]].filter(row=>row[1]).map((row,index)=><p key={index}><strong>{row[0]}:</strong> {vehicles.find(car=>car.user_id===row[1])?.display_name}</p>)}</div>
    <form className="stack" onSubmit={event=>{event.preventDefault();void prepare();}}>
      <label className="field"><span>{t('Planungsfahrzeug aus TeslaTalk')}</span><select disabled={busy} value={chosen} onChange={event=>{clear();setChosen(event.target.value);setSoc(null);setConsent(false);}}>{vehicles.map(car=><option key={car.user_id} value={car.user_id}>{car.display_name} · {car.vehicle_name} · {car.battery_pct??'—'}% · {car.range_km??'—'} km</option>)}</select></label>
      <label className="field"><span>{t('Akku bei Abfahrt (%)')}</span><input type="number" min={0} max={100} step="0.1" disabled={busy} value={charge} onChange={event=>{clear();setSoc(event.target.value);}}/></label>
      {car?.updated_at&&<small>{t('Fahrzeugdaten vom ')}{date(car.updated_at)}</small>}
      {stale&&<p className="notice">{t('Die Fahrzeugdaten sind älter als fünf Minuten. Den aktuellen Akku prüfen; es erfolgt kein zusätzlicher Tesla-Abruf.')}</p>}
      <p className="hint">{t('In ABRP das passende gespeicherte Fahrzeug auswählen und den Abfahrtsakku aus TeslaTalk übernehmen. Der Öffnen-Link synchronisiert keine Fahrzeugdaten und meldet dich nicht in TeslaTalk bei ABRP an.')}</p>
      <button type="button" disabled={busy||charge===''} onClick={()=>void copy(charge)}>{t('Abfahrtsakku kopieren')}</button>
      {destinations.map((value,index)=><div className="abrp-destination" key={index}><label className="field"><span>{index===0?t('Start'):index===destinations.length-1?t('Ziel'):t('Zwischenstopp')}</span><input disabled={busy} required maxLength={300} value={value} placeholder={t('Adresse oder Breitengrad, Längengrad')} onChange={event=>point(index,event.target.value)}/></label>
        {index===0&&<button type="button" disabled={busy} onClick={start}>{t('Browserstandort als Start')}</button>}
        {index>0&&index<destinations.length-1&&<button type="button" disabled={busy} onClick={()=>{clear();setDestinations(rows=>rows.filter((_,i)=>i!==index));}}>{t('Entfernen')}</button>}
      </div>)}
      <button type="button" disabled={busy||destinations.length>=25} onClick={()=>{clear();setDestinations(rows=>[...rows.slice(0,-1),'',rows.at(-1)!]);}}>{t('Zwischenstopp hinzufügen')}</button>
      <label className="checkbox-field"><input type="checkbox" disabled={busy} checked={consent} onChange={event=>{clear();setConsent(event.target.checked);}}/><span>{t('Ich möchte diese Start-, Ziel- und Zwischenstoppdaten per Link oder QR-Code in ABRP öffnen.')}</span></label>
      <button className="primary" disabled={busy||!car||!consent}>{t('ABRP-Link und QR-Code vorbereiten')}</button>
    </form>
    {handoff&&<div className="abrp-handoff">
      {handoff.qr&&<img src={handoff.qr} alt={t('QR-Code zum Öffnen der Route in ABRP')}/>}
      <div className="stack"><a className="button primary" target="_blank" rel="noopener noreferrer" href={handoff.url}>{t('Route in ABRP öffnen')}</a><label className="field"><span>{t('Vorbereiteter ABRP-Link')}</span><input readOnly value={handoff.url}/></label><button onClick={()=>void copy(handoff.url)}>{t('ABRP-Link kopieren')}</button></div>
    </div>}
    <details className="abrp-account"><summary>{t('Mit der ABRP-App per QR anmelden')}</summary><ol>
      <li>{t('ABRP auf dem Gerät öffnen, auf dem du planen möchtest. Dort „Login mit ABRP-App“ wählen.')}</li>
      <li>{t('Auf dem angemeldeten Handy in ABRP die Kontoeinstellungen und „Login remote app“ öffnen. Den dort von ABRP angezeigten Login-QR-Code scannen.')}</li>
      <li>{t('Das passende Fahrzeug, den Abfahrtsakku sowie Ladekarten und Ladenetze in ABRP prüfen. Anschließend dort berechnen.')}</li>
    </ol><p className="hint">{t('Der TeslaTalk-QR-Code öffnet die Route. Der Anmelde-QR-Code wird von ABRP selbst erzeugt. Diese Anmeldung verbindet dein ABRP-Konto nicht mit dem TeslaTalk-Server.')}</p></details>
    <p>{t('Danach den Plan in ABRP nach Excel exportieren und unten als Routen-Datei hochladen. Die geprüften Ladehalte können anschließend an die freigegebenen Gruppenfahrzeuge gesendet werden.')}</p>
    <p className="hint">{t('Ein ABRP-Teilen-Link allein liefert ohne freigegebenen API-Zugang keine fertige Route an TeslaTalk. Ladenetze und Ladekarten werden in ABRP eingestellt; die hier angezeigten Fahrzeugwerte sind ein Datenstand.')}</p>
    {notice&&<p role="status">{t(notice)}</p>}{error&&<p className="error" role="alert">{t(error)}</p>}
  </section>;
}
