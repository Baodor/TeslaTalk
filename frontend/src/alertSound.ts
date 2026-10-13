import { useSyncExternalStore } from 'react';

let enabled=true;
try { enabled=localStorage.getItem('teslatalk-alert-sound')!=='off'; } catch {}
let context: AudioContext | null=null;
const played=new Set<string>(), listeners=new Set<()=>void>();
const notify=()=>listeners.forEach(listener=>listener());
export function unlockSounds() {
  if(!enabled||context?.state==='running')return;
  try {
    const Constructor=window.AudioContext||(window as any).webkitAudioContext;
    if(!Constructor)return;
    context??=new Constructor();
    void context!.resume().then(notify).catch(notify);
  } catch {notify();}
}
const unlockFromGesture=(event:Event)=>{
  // The explicit sound button manages its own activation. Unlocking before
  // its click can change the displayed toggle and accidentally turn it off.
  if(event.target instanceof Element&&event.target.closest('[data-alert-sound-control]'))return;
  unlockSounds();
};
document.addEventListener('pointerdown',unlockFromGesture,{capture:true});
document.addEventListener('keydown',unlockFromGesture,{capture:true});
export function setSounds(value:boolean) {
  enabled=value;
  try {localStorage.setItem('teslatalk-alert-sound',value?'on':'off');} catch {}
  if(value)unlockSounds();notify();
}
export function playAlert(id:string) {
  if(!enabled||!context||context.state!=='running'||played.has(id))return false;
  played.add(id);if(played.size>200)played.delete(played.values().next().value!);
  for(const [delay,frequency] of [[0,660],[.2,880]]) {
    const oscillator=context.createOscillator(),gain=context.createGain(),start=context.currentTime+delay;
    oscillator.frequency.value=frequency;gain.gain.setValueAtTime(0,start);gain.gain.linearRampToValueAtTime(.12,start+.015);
    gain.gain.exponentialRampToValueAtTime(.001,start+.16);oscillator.connect(gain);gain.connect(context.destination);
    oscillator.start(start);oscillator.stop(start+.18);
  }
  return true;
}
const subscribe=(listener:()=>void)=>{listeners.add(listener);return()=>{listeners.delete(listener);};};
export const useSounds=()=>useSyncExternalStore(subscribe,()=>`${enabled}:${context?.state==='running'}`);
