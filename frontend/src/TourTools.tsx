import { useEffect, useState } from 'react';
import { Bell, BellOff, Link, Toilet } from 'lucide-react';
import QRCode from 'qrcode';
import { api } from './api';
import { t } from './i18n';
import { setSounds, useSounds } from './alertSound';

export type PauseRequest={id:string;user_id:string;display_name:string;created_at:number};
export default function TourTools({tripId,userId,leader,active,canShare,requests,linkActive,update,notify}: {
  tripId:string;userId:string;leader:boolean;active:boolean;canShare:boolean;requests:PauseRequest[];linkActive:boolean;
  update:(rows:PauseRequest[],message?:any)=>void;notify:(value:string)=>void;
}) {
  const [busy,setBusy]=useState(false),[url,setUrl]=useState(''),[qr,setQr]=useState(''),[shared,setShared]=useState(linkActive);
  const sound=useSounds(),enabled=sound.startsWith('true'),ready=sound.endsWith('true');
  useEffect(()=>{setShared(linkActive);if(!linkActive){setUrl('');setQr('');}},[linkActive]);
  const pending=requests.some(row=>row.user_id===userId);
  async function request(confirm=false) {
    if(busy)return;setBusy(true);
    try {const result=await api(`/api/trips/${tripId}/toilet${confirm?'/confirm':''}`,'POST',confirm?{request_ids:requests.map(row=>row.id)}:undefined);update(result.pause_requests,result.message);}
    catch(error){notify((error as Error).message);}finally{setBusy(false);}
  }
  async function share(remove=false) {
    if(busy)return;setBusy(true);
    try {
      const result=await api(`/api/trips/${tripId}/spectator-link`,remove?'DELETE':'POST');
      setShared(!remove);setUrl(result.url||'');setQr(result.url?await QRCode.toDataURL(result.url,{width:200,margin:2}):'');
    }catch(error){notify((error as Error).message);}finally{setBusy(false);}
  }
  return <section className="panel tour-tools" aria-label={t('Fahrt und Pausen')}>
    <div className="header-actions">
      <button disabled={!active||busy||pending} onClick={()=>void request()}><Toilet size={18}/>{pending?t('Toilettenpause angefragt'):t('Ich muss aufs Klo')}</button>
      <button aria-pressed={enabled&&ready} onClick={()=>setSounds(!enabled||!ready)}>{enabled&&ready?<Bell size={17}/>:<BellOff size={17}/>} {enabled&&ready?t('Hinweistöne an'):t('Hinweistöne aktivieren')}</button>
    </div>
    {active&&requests.length>0&&<div className="pause-notice" role={leader?'alert':'status'}>
      <strong>{t('Toilettenpause angefragt')}</strong><p>{requests.map(row=>row.display_name).join(', ')}</p>
      {leader?<button className="primary" disabled={busy} onClick={()=>void request(true)}>{t('Wir fahren jetzt zur Toilettenpause ab')}</button>:<small>{t('Der Fahrtleiter wurde informiert.')}</small>}
    </div>}
    <p className="hint">{t('Hinweistöne funktionieren im geöffneten Browser nach einer Interaktion. Bei gesperrtem Handy gelten deine Push- und Mitteilungseinstellungen.')}</p>
    {leader&&<details><summary><Link size={15}/> {t('Zuschauerlink')}</summary>
      <p>{t('Der Link zeigt während der Fahrt die freigegebenen Fahrer-Browserpositionen. Zuschauer können nichts steuern und sehen keine Chats, Kennzeichen oder Mitfahrer-Standorte.')}</p>
      <div className="header-actions"><button disabled={busy||!canShare} onClick={()=>void share()}>{shared?t('Zuschauerlink erneuern'):t('Zuschauerlink erstellen')}</button>{shared&&<button disabled={busy} onClick={()=>void share(true)}>{t('Zuschauerlink widerrufen')}</button>}</div>
      {url&&<div className="spectator-share"><img src={qr} alt={t('QR-Code für Zuschauer')}/><div><input readOnly value={url} aria-label={t('Zuschauerlink')}/><button onClick={()=>void navigator.clipboard?.writeText(url).catch(()=>notify(t('Bitte den Link manuell kopieren.')))}>{t('Kopieren')}</button></div></div>}
    </details>}
  </section>;
}
