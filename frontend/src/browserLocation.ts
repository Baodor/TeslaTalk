import { useEffect } from 'react';
import { api } from './api';
import { t } from './i18n';

let device:string=globalThis.crypto?.randomUUID?.()||'browser-'+Date.now()+'-'+Math.random().toString(36).slice(2);
try {device=localStorage.getItem('teslatalk-position-device')||device;localStorage.setItem('teslatalk-position-device',device);} catch {}

export function useBrowserLocation(tripId:string,enabled:boolean,active:boolean,vehicle:boolean,canShare:boolean,disable:()=>void,notify:(message:string)=>void) {
  useEffect(()=>{
    if(!enabled||!active||!canShare)return;
    if(!navigator.geolocation){notify(t('Dieser Browser unterstützt keine Standortfreigabe.'));disable();return;}
    let stopped=false,last=0,errorAt=0,inFlight=false,watch:number|null=null;
    let uploading=Promise.resolve(),wake:any=null;
    const source=vehicle?'browser_vehicle':'browser';
    const streamDevice=device.slice(0,32)+'-'+Math.random().toString(36).slice(2);
    // A closing tab must not delete a newer fix from another tab/session.
    function fail(error:GeolocationPositionError|Error) {
      if(stopped)return;
      if(Date.now()-errorAt>60000){errorAt=Date.now();notify(t('Standortfreigabe: ')+error.message);}
      if('code' in error&&error.code===1)disable();
    }
    function position(value:GeolocationPosition) {
      if(stopped||inFlight||Date.now()-last<10000||Date.now()-value.timestamp>60000)return;
      last=Date.now();inFlight=true;
      uploading=api(`/api/trips/${tripId}/samples`,'POST',{latitude:value.coords.latitude,longitude:value.coords.longitude,
        speed_kmh:value.coords.speed===null?null:Math.max(0,value.coords.speed*3.6),heading:value.coords.heading,
        source,captured_at:value.timestamp/1000,device_id:vehicle?streamDevice:undefined})
        .then(()=>{}).catch(error=>{if(!stopped)notify(error.message);}).finally(()=>{inFlight=false;});
    }
    async function keepAwake() {
      if(stopped||document.visibilityState!=='visible'||wake||!('wakeLock' in navigator))return;
      try {const lock=await (navigator as any).wakeLock.request('screen');if(stopped){void lock.release();return;}wake=lock;lock.addEventListener('release',()=>{wake=null;});}catch{}
    }
    try {watch=navigator.geolocation.watchPosition(position,fail,{enableHighAccuracy:true,maximumAge:5000,timeout:20000});}
    catch(error){fail(error as Error);disable();return;}
    // Stationary cars need fresh fixes too; never refresh the timestamp of a
    // saved location or let delayed uploads accumulate in a queue.
    const timer=setInterval(()=>{try{navigator.geolocation.getCurrentPosition(position,fail,{enableHighAccuracy:true,maximumAge:5000,timeout:20000});}catch(error){fail(error as Error);disable();}},15000);
    document.addEventListener('visibilitychange',keepAwake);void keepAwake();
    return()=>{
      stopped=true;if(watch!==null)navigator.geolocation.clearWatch(watch);clearInterval(timer);
      document.removeEventListener('visibilitychange',keepAwake);if(wake)void wake.release();
      void uploading.then(()=>api(`/api/trips/${tripId}/location?source=${source}${vehicle?'&device_id='+encodeURIComponent(streamDevice):''}`,'DELETE')).catch(()=>{});
    };
  },[tripId,enabled,active,vehicle,canShare]);
}
