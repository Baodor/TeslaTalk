import { useState } from 'react';
import { BatteryCharging, Download, Upload } from 'lucide-react';
import { api } from './api';
import { t } from './i18n';

type Stop={name:string;latitude:number;longitude:number;kind:string;operator:string;address:string;google_place_id:string|null};
type Plan={title:string;stops:Stop[];version:string;current_stop:number|null;confirmations:{user_id:string;version:string;stop_index:number;recognized:boolean;preconditioning:boolean}[]};
export default function ChargingPlan({tripId,userId,leader,active,finished,driver,plan,vehicles,update,notify}: {
  tripId:string;userId:string;leader:boolean;active:boolean;finished:boolean;driver:boolean;plan:Plan|null;
  vehicles:{user_id:string;display_name:string;vehicle_name:string;accepted:boolean}[];
  update:(plan:Plan|null)=>void;notify:(message:string)=>void;
}) {
  const [preview,setPreview]=useState<{title:string;stops:Stop[]}|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState('');
  const [result,setResult]=useState<any>(null),[uncertain,setUncertain]=useState<string|null>(null);
  async function upload(file:File) {
    if(busy)return;setBusy(true);setError('');
    try {if(file.size>500000)throw new Error(t('Die Datei darf höchstens 500 KB groß sein.'));
      const binary=file.name.toLowerCase().endsWith('.xlsx');
      const content=binary?await new Promise<string>((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result).split(',')[1]);reader.onerror=()=>reject(new Error(t('Die Datei konnte nicht gelesen werden.')));reader.readAsDataURL(file);}):await file.text();
      setPreview(await api(`/api/trips/${tripId}/charging-plan/preview`,'POST',{filename:file.name,content,encoding:binary?'base64':'text'}));
    }catch(error){setError((error as Error).message);}finally{setBusy(false);}
  }
  async function save(remove=false) {
    if(busy)return;setBusy(true);setError('');
    try {const saved=await api(`/api/trips/${tripId}/charging-plan`,remove?'DELETE':'PUT',remove?undefined:preview);update(remove?null:saved);setPreview(null);setResult(null);setUncertain(null);}
    catch(error){setError((error as Error).message);}finally{setBusy(false);}
  }
  async function send(index:number) {
    if(!plan||busy||uncertain)return;setBusy(true);setError('');
    const requestId=crypto.randomUUID();setResult(null);
    try {setResult(await api(`/api/trips/${tripId}/charging-plan/send`,'POST',{request_id:requestId,version:plan.version,stop_index:index}));
      const detail=await api(`/api/trips/${tripId}`);update(detail.charging_plan);
    }catch(error){setError((error as Error).message);if(!(error as any).status||(error as any).status>=500)setUncertain(requestId);}
    finally{setBusy(false);}
  }
  async function check() {
    if(!uncertain||busy)return;setBusy(true);setError('');
    try {const value=await api(`/api/trips/${tripId}/charging-plan/requests/${uncertain}`);setResult(value);if(value.status==='completed')setUncertain(null);}
    catch(error){setError((error as Error).message);}finally{setBusy(false);}
  }
  async function confirm(recognized:boolean,preconditioning:boolean) {
    if(!plan||plan.current_stop===null||busy)return;setBusy(true);
    try {update(await api(`/api/trips/${tripId}/charging-plan/confirm`,'POST',{version:plan.version,stop_index:plan.current_stop,recognized,preconditioning}));}
    catch(error){notify((error as Error).message);}finally{setBusy(false);}
  }
  function edit(index:number,field:keyof Stop,value:string) {
    setPreview(current=>current?{...current,stops:current.stops.map((stop,i)=>i===index?{...stop,[field]:field==='google_place_id'?(value||null):value}:stop)}:current);
  }
  const current=plan?.current_stop===null?null:plan?.stops[plan?.current_stop??-1];
  const ownConfirmation=plan?.confirmations?.find(row=>row.user_id===userId&&row.version===plan.version&&row.stop_index===plan.current_stop);
  return <section className="panel charging-plan" aria-label={t('Gemeinsamer Ladeplan')}>
    <div className="panel-heading"><BatteryCharging size={21}/><h3>{t('Gemeinsamer Ladeplan')}</h3></div>
    <p>{t('ABRP-Excel-Export oder eine GPX-/CSV-Datei mit benannten Stopps und Stationskoordinaten hochladen. TeslaTalk-JSON kann ebenfalls eingelesen werden.')}</p>
    <p className="hint">{t('Die Gruppe erhält denselben nächsten Halt. Tesla berechnet den Abschnitt selbst. Koordinaten allein bestätigen keine Ladestation oder Vorkonditionierung.')}</p>
    {leader&&!finished&&<label className="field"><span><Upload size={16}/> {t('Routen-Datei hochladen')}</span><input type="file" accept=".gpx,.json,.xlsx,.csv" disabled={busy} onChange={event=>{const file=event.target.files?.[0];if(file)void upload(file);event.target.value='';}}/></label>}
    {preview&&<div className="plan-preview"><h4>{t('Import vor dem Speichern prüfen')}</h4><label className="field"><span>{t('Name des Ladeplans')}</span><input value={preview.title} maxLength={200} onChange={event=>setPreview({...preview,title:event.target.value})}/></label>
      {preview.stops.map((stop,index)=><div className="plan-stop" key={index}><strong>{index+1}.</strong><label className="field"><span>{t('Name des Stopps')}</span><input value={stop.name} maxLength={200} onChange={event=>edit(index,'name',event.target.value)}/></label>
        <label className="field"><span>{t('Art des Stopps')}</span><select value={stop.kind} onChange={event=>edit(index,'kind',event.target.value)}><option value="charging">{t('Ladestation')}</option><option value="waypoint">{t('Zwischenstopp')}</option><option value="destination">{t('Ziel')}</option></select></label>
        <label className="field"><span>{t('Stationsadresse')}</span><input value={stop.address} maxLength={300} onChange={event=>edit(index,'address',event.target.value)}/></label>
        <label className="field"><span>{t('Google-Places-ID (optional)')}</span><input value={stop.google_place_id||''} maxLength={256} onChange={event=>edit(index,'google_place_id',event.target.value)}/></label><small>{stop.latitude}, {stop.longitude}</small>
      </div>)}<div className="header-actions"><button className="primary" disabled={busy||!preview.title.trim()} onClick={()=>void save()}>{t('Geprüften Ladeplan speichern')}</button><button disabled={busy} onClick={()=>setPreview(null)}>{t('Abbrechen')}</button></div></div>}
    {plan&&<><h4>{plan.title}</h4><ol className="planned-stops">{plan.stops.map((stop,index)=><li className={plan.current_stop===index?'selected-stop':''} key={index}>
      <strong>{stop.name}</strong><small>{stop.kind==='charging'?t('Ladestation'):stop.kind==='destination'?t('Ziel'):t('Zwischenstopp')} · {stop.operator||stop.address}</small>
      {stop.kind==='charging'&&<small>{stop.google_place_id?t('Stationsreferenz vorhanden; Erkennung im Auto prüfen.'):t('Keine eindeutige Stationsreferenz. Zuordnung im Tesla prüfen.')}</small>}
      {leader&&active&&<button disabled={busy||!!uncertain} onClick={()=>void send(index)}>{t('Diesen Halt an die freigegebenen Autos senden')}</button>}
    </li>)}</ol><div className="header-actions"><a className="button" href={`/api/trips/${tripId}/charging-plan/export`}><Download size={16}/>{t('Ladeplan exportieren')}</a>{leader&&!finished&&<button disabled={busy} onClick={()=>void save(true)}>{t('Importierten Ladeplan löschen')}</button>}</div></>}
    {active&&driver&&current?.kind==='charging'&&<div className="charger-check"><strong>{t('Zuordnung im eigenen Tesla bestätigen')}</strong><p>{current.name}</p>
      <label className="checkbox-field"><input type="checkbox" disabled={busy} checked={!!ownConfirmation?.recognized} onChange={event=>void confirm(event.target.checked,false)}/><span>{t('Tesla zeigt diesen Halt als Ladestation.')}</span></label>
      <label className="checkbox-field"><input type="checkbox" disabled={busy||!ownConfirmation?.recognized} checked={!!ownConfirmation?.preconditioning} onChange={event=>void confirm(true,event.target.checked)}/><span>{t('Vorkonditionierung wird im Auto angezeigt.')}</span></label>
    </div>}
    {leader&&current?.kind==='charging'&&<ul>{vehicles.filter(car=>car.accepted||car.user_id===userId).map(car=>{const confirmation=plan?.confirmations?.find(row=>row.user_id===car.user_id&&row.version===plan.version&&row.stop_index===plan.current_stop);return <li key={car.user_id}>{car.display_name}: {confirmation?.recognized?t('Ladestation im Tesla bestätigt'):t('Stationszuordnung noch nicht bestätigt')} · {confirmation?.preconditioning?t('Vorkonditionierung bestätigt'):t('Vorkonditionierung nicht bestätigt')}</li>;})}</ul>}
    {result&&<div role="status" aria-label={t('Ergebnisse der Stoppübertragung')}><ul>{result.vehicles.map((row:any)=><li key={row.user_id}>{vehicles.find(car=>car.user_id===row.user_id)?.display_name||row.user_id}: {t(row.message)}</li>)}</ul>{result.status==='unknown'&&<p>{t('Ergebnis bitte am Auto prüfen. Der Befehl wird nicht automatisch wiederholt.')}</p>}</div>}
    {uncertain&&<button disabled={busy} onClick={()=>void check()}>{t('Auftragsstatus abrufen')}</button>}
    {error&&<p className="error" role="alert">{t(error)}</p>}
  </section>;
}
