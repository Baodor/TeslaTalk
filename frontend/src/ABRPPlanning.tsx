import { useEffect, useState } from 'react';
import { api, ApiError } from './api';
import { t } from './i18n';
import ABRPBrowserPlanning from './ABRPBrowserPlanning';

type Destination={value:string;stay_minutes:number;charger_id?:number|null};
type Vehicle={user_id:string;display_name:string;vehicle_name:string;battery_pct?:number|null;range_km?:number|null};
function IternioPlanning({tripId,userId,leader,finished,vehicles,participants,recommendations,preview}: {
  tripId:string;userId:string;leader:boolean;finished:boolean;vehicles:Vehicle[];participants:any[];
  recommendations:{lowest_range_user_id?:string;lowest_battery_user_id?:string};preview:(value:any)=>void;
}) {
  const [catalog,setCatalog]=useState<any>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false),[link,setLink]=useState('');
  const [username,setUsername]=useState(''),[password,setPassword]=useState(''),[model,setModel]=useState(''),[filter,setFilter]=useState('');
  const [chosen,setChosen]=useState(recommendations.lowest_range_user_id||recommendations.lowest_battery_user_id||userId);
  const [soc,setSoc]=useState(''),[reserve,setReserve]=useState('10'),[networks,setNetworks]=useState<number[]>([]),[exclusive,setExclusive]=useState(false);
  const [destinations,setDestinations]=useState<Destination[]>([{value:'',stay_minutes:0},{value:'',stay_minutes:0}]);
  const [costs,setCosts]=useState(false),[requestId,setRequestId]=useState<string|null>(null),[uncertain,setUncertain]=useState(false),[notice,setNotice]=useState('');
  useEffect(()=>{if(leader)void api('/api/me/abrp').then(async info=>{setCatalog(info);if(info.configured&&info.connected)await loadCatalog();}).catch(error=>setError(error.message));},[leader]);
  useEffect(()=>{const car=vehicles.find(car=>car.user_id===chosen);if(car?.battery_pct!=null)setSoc(String(Math.round(car.battery_pct)));},[chosen]);
  async function loadCatalog(){const data=await api('/api/abrp/catalog');setCatalog(data);return data;}
  async function account(remove=false) {
    if(busy)return;setBusy(true);setError('');
    try {const info=await api('/api/me/abrp',remove?'DELETE':'POST',remove?undefined:{username,password});setPassword('');setCatalog(info);
      if(!remove)await loadCatalog();}
    catch(error){setPassword('');setError((error as Error).message);}finally{setBusy(false);}
  }
  async function importLink() {
    if(busy)return;setBusy(true);setError('');
    try {const result=await api(`/api/trips/${tripId}/abrp/link`,'POST',{url:link});setDestinations(result.destinations);setModel(result.typecode||'');setSoc(String(result.departure_soc));setReserve(String(result.arrival_soc));setNetworks(result.network_ids);setExclusive(result.exclusive);setNotice(result.notice);}
    catch(error){setError((error as Error).message);}finally{setBusy(false);}
  }
  async function calculate(check=false) {
    if(busy||(!check&&uncertain))return;setBusy(true);setError('');
    const id=check?requestId:crypto.randomUUID();setRequestId(id);
    try {const result=await api(`/api/trips/${tripId}/abrp/${check?'requests/'+id:'plan'}`,check?'GET':'POST',check?undefined:{request_id:id,planner_user_id:chosen,typecode:model,departure_soc:Number(soc),arrival_soc:Number(reserve),network_ids:networks,exclusive,destinations,costs_confirmed:costs});
      if(result.status==='completed'){setUncertain(false);setCosts(false);preview(result.plan);setNotice(t('ABRP-Route berechnet. Ladehalte prüfen und anschließend speichern; es wurden keine Fahrzeugbefehle gesendet.'));}
      else {setUncertain(result.status==='unknown');setError(result.message||t('Berechnung nicht bestätigt. Status abrufen; es wird nicht automatisch erneut berechnet.'));}}
    catch(error){setError((error as Error).message);if(!(error instanceof ApiError)||error.status>=500)setUncertain(true);}
    finally{setBusy(false);}
  }
  function edit(index:number,value:string){setDestinations(rows=>rows.map((row,i)=>i===index?{value,stay_minutes:row.stay_minutes}:row));}
  if(!leader)return <p>{t('Der Fahrtleiter plant die gemeinsamen Ladehalte. Du kannst deinen eigenen Tesla für die Zielübernahme freigeben.')}</p>;
  if(finished)return null;
  return <section className="panel abrp-planning" aria-label={t('ABRP-Ladeplanung')}>
    <h3>{t('ABRP-Ladeplanung')}</h3>
    <p>{t('Fahrzeug und Ladenetze auswählen, Route in TeslaTalk berechnen und die gemeinsamen Stopps an freigegebene Autos senden.')}</p>
    {!catalog?.configured?<p className="notice">{t('Der Betreiber muss zuerst den Iternio-Planning-Zugang einrichten.')}</p>:<>
      <details className="abrp-account" open={!catalog.connected}><summary>{t('ABRP-Konto und Fahrzeugkatalog')}</summary>
        {catalog.connected?<><p>{t('ABRP verbunden: ')}{catalog.username}</p><button disabled={busy} onClick={()=>void account(true)}>{t('ABRP-Verbindung entfernen')}</button><button disabled={busy} onClick={()=>{setBusy(true);void loadCatalog().catch(error=>setError(error.message)).finally(()=>setBusy(false));}}>{t('Fahrzeugkatalog und Ladenetze laden')}</button></>:<form className="stack" onSubmit={event=>{event.preventDefault();void account();}}>
          <p>{t('Die Anmeldung wird über Iternios veröffentlichte Schnittstelle gesendet. TeslaTalk speichert die Sitzung verschlüsselt und speichert kein ABRP-Passwort. Bei Ablauf erneut verbinden.')}</p>
          <label className="field"><span>{t('ABRP-E-Mail oder Benutzername')}</span><input required value={username} maxLength={200} autoComplete="username" onChange={event=>setUsername(event.target.value)}/></label>
          <label className="field"><span>{t('ABRP-Passwort')}</span><input type="password" required value={password} maxLength={1000} autoComplete="current-password" onChange={event=>setPassword(event.target.value)}/></label>
          <button className="primary" disabled={busy}>{t('ABRP-Konto verbinden')}</button>
        </form>}
      </details>
      <div className="two-fields"><label className="field"><span>{t('ABRP-Teilen-Link')}</span><input type="url" value={link} maxLength={2000} placeholder="https://abetterrouteplanner.com/?plan_uuid=…" onChange={event=>setLink(event.target.value)}/></label><button disabled={busy||!link||!catalog.connected} onClick={()=>void importLink()}>{t('Planungsparameter aus Link übernehmen')}</button></div>
      <p className="hint">{t('Der Linkabruf berechnet nichts. Eine anschließende Neuberechnung kann vom gespeicherten ABRP-Plan abweichen.')}</p>
      <div className="abrp-recommendations">{[recommendations.lowest_range_user_id&&[t('Geringste Reichweite'),recommendations.lowest_range_user_id],recommendations.lowest_battery_user_id&&[t('Niedrigster Akku'),recommendations.lowest_battery_user_id]].filter(Boolean).map((row:any,index)=><p key={index}><strong>{row[0]}:</strong> {vehicles.find(car=>car.user_id===row[1])?.display_name}</p>)}</div>
      <form className="stack" onSubmit={event=>{event.preventDefault();void calculate();}}>
        <label className="field"><span>{t('Fahrzeug für die Berechnung')}</span><select value={chosen} onChange={event=>setChosen(event.target.value)}>{vehicles.map(car=><option key={car.user_id} value={car.user_id}>{car.display_name} · {car.vehicle_name} · {car.battery_pct??'—'}% · {car.range_km??'—'} km</option>)}</select></label>
        <label className="field"><span>{t('Modell suchen')}</span><input type="search" value={filter} placeholder={t('Modell suchen')} onChange={event=>setFilter(event.target.value)}/></label><label className="field"><span>{t('Fahrzeugmodell in ABRP')}</span><select value={model} required onChange={event=>setModel(event.target.value)}><option value="">{t('Genaue Fahrzeugvariante auswählen')}</option>{(catalog.models||[]).filter((row:any)=>`${row.title} ${row.manufacturer}`.toLowerCase().includes(filter.toLowerCase())||row.typecode===model).map((row:any)=><option key={row.typecode} value={row.typecode}>{row.manufacturer} · {row.title}</option>)}</select></label>
        <p className="hint">{t('Tesla-Modellnamen allein bestimmen keine Batterie- oder Antriebsvariante. Die passende ABRP-Variante bewusst auswählen.')}</p>
        <div className="two-fields"><label className="field"><span>{t('Akku bei Abfahrt (%)')}</span><input type="number" step="0.1" min={1} max={100} required value={soc} onChange={event=>setSoc(event.target.value)}/></label><label className="field"><span>{t('Reserve am Ziel (%)')}</span><input type="number" step="0.1" min={1} max={80} required value={reserve} onChange={event=>setReserve(event.target.value)}/></label></div>
        {destinations.map((row,index)=><div className="abrp-destination" key={index}><label className="field"><span>{index===0?t('Start'):index===destinations.length-1?t('Ziel'):t('Zwischenstopp')}</span><input required value={row.value} maxLength={300} onChange={event=>edit(index,event.target.value)}/></label>
          {index===0?<button type="button" onClick={()=>{const data=participants.find(row=>row.id===chosen)?.data;if(data?.latitude!=null&&data?.longitude!=null)edit(0,`${data.latitude}, ${data.longitude}`);else setError(t('Für dieses Fahrzeug fehlt ein aktueller Browserstandort. Startadresse eingeben.'));}}>{t('Browserstandort als Start')}</button>:<label className="field"><span>{t('Aufenthalt (Minuten)')}</span><input type="number" min={0} max={1440} value={row.stay_minutes} onChange={event=>setDestinations(rows=>rows.map((item,i)=>i===index?{...item,stay_minutes:Number(event.target.value)}:item))}/></label>}
          {index>0&&index<destinations.length-1&&<button type="button" onClick={()=>setDestinations(rows=>rows.filter((_,i)=>i!==index))}>{t('Entfernen')}</button>}
        </div>)}
        <button type="button" disabled={destinations.length>=25} onClick={()=>setDestinations(rows=>[...rows.slice(0,-1),{value:'',stay_minutes:0},rows.at(-1)!])}>{t('Zwischenstopp hinzufügen')}</button>
        <fieldset className="abrp-networks"><legend>{t('Ladenetze')}</legend>{(catalog.networks||[]).map((network:any)=><label className="checkbox-field" key={network.id}><input type="checkbox" checked={networks.includes(network.id)} onChange={event=>setNetworks(rows=>event.target.checked?[...rows,network.id]:rows.filter(id=>id!==network.id))}/><span>{network.name}</span></label>)}</fieldset>
        <label className="checkbox-field"><input type="checkbox" checked={exclusive} onChange={event=>setExclusive(event.target.checked)}/><span>{t('Ausschließlich bei den ausgewählten Ladenetzen laden')}</span></label>
        <p className="hint">{t('Ohne Auswahl sind alle passenden Ladenetze erlaubt. Mit Auswahl werden Netze bevorzugt oder ausdrücklich ausschließlich verwendet.')}</p>
        <label className="checkbox-field"><input type="checkbox" checked={costs} onChange={event=>setCosts(event.target.checked)}/><span>{t('Ich bestätige die mögliche kostenpflichtige Iternio-Berechnung. Standort und Planungsdaten werden an Iternio gesendet.')}</span></label>
        <button className="primary" disabled={busy||uncertain||!costs||!model||!vehicles.length}>{t('Laderoute berechnen')}</button>
      </form>
      {uncertain&&requestId&&<><button disabled={busy} onClick={()=>void calculate(true)}>{t('Berechnungsstatus abrufen')}</button><p className="hint">{t('Eine neue Berechnung kann erneut Kosten verursachen. Den bisherigen Auftrag zuerst prüfen.')}</p><button disabled={busy} onClick={()=>{setUncertain(false);setRequestId(null);setCosts(false);}}>{t('Neue Berechnung bewusst starten')}</button></>}
    </>}
    {notice&&<p role="status">{t(notice)}</p>}{error&&<p className="error" role="alert">{t(error)}</p>}
  </section>;
}


export default function ABRPPlanning(props:Parameters<typeof IternioPlanning>[0]) {
  const [apiOpened,setAPIOpened]=useState(false),[apiVisible,setAPIVisible]=useState(false);
  return <><ABRPBrowserPlanning {...props}/>{props.leader&&!props.finished&&<>
    <button aria-expanded={apiVisible} onClick={()=>{setAPIOpened(true);setAPIVisible(value=>!value);}}>{t(apiVisible?'Optionale kostenpflichtige API ausblenden':'Optionale kostenpflichtige API anzeigen')}</button>
    {apiOpened&&<div hidden={!apiVisible}><IternioPlanning {...props}/></div>}
  </>}</>;
}
