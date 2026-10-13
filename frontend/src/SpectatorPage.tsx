import { useEffect, useState } from 'react';
import TripMap from './TripMap';
import { api, date } from './api';
import { t } from './i18n';
export default function SpectatorPage({token}:{token:string}) {
  const [data,setData]=useState<any>(null),[error,setError]=useState('');
  useEffect(()=>{
    let stopped=false,invalid=false;
    async function load(){try {const result=await api('/api/spectator/'+encodeURIComponent(token));if(!stopped){setData(result);setError('');}}
      catch(error){if(!stopped){setError((error as Error).message);setData(null);if((error as any).status===404)invalid=true;}}}
    void load();const timer=setInterval(()=>{if(!invalid)void load();},10000);
    return()=>{stopped=true;clearInterval(timer);};
  },[token]);
  return <main className="spectator-page"><a href="/" className="brand" aria-label={t('TeslaTalk – Startseite')}><img className="brand-symbol" src="/favicon.svg" alt=""/>TeslaTalk</a>
    <header className="page-header"><div><span className="eyebrow">{t('LIVE ZUSCHAUEN')}</span><h1>{data?.title||t('Zuschaueransicht')}</h1><p>{data?.destination}</p></div></header>
    <p>{t('Nur ansehen. Der Link endet mit der Fahrt und kann jederzeit widerrufen werden.')}</p>
    {error?<p className="error" role="alert">{t(error)}</p>:data?<>{data.status==='planned'?<p>{t('Fahrt beginnt am {0}.',{0:date(data.starts_at)})}</p>:<><TripMap participants={data.participants}/>{!data.participants.length&&<p>{t('Noch keine Fahrer-Browserpositionen freigegeben.')}</p>}</>}</>:<p>{t('Fahrt wird geladen …')}</p>}
  </main>;
}
