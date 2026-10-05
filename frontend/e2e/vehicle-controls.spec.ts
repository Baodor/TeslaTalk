import { test, expect, type Page } from '@playwright/test';
import { mapTile, mockMapTiles } from './map-tiles';
test.beforeEach(async({context})=>{await mockMapTiles(context);});

async function mockTrip(page:Page,options:{leader?:boolean;guest?:boolean}={}) {
  const user={id:'control-driver',username:'ControlDriver',display_name:'Max',provider:options.guest?'guest':'demo',favorite_vehicle:options.guest?null:'car-max',plate:null};
  const vehicles=[{user_id:user.id,vehicle_id:'car-max',display_name:'Max',vehicle_name:'Max Tesla',allowed:false,available:true,demo:true},{user_id:'control-friend',vehicle_id:'car-anna',display_name:'Anna',vehicle_name:'Anna Tesla',allowed:true,available:true,demo:true}];
  const trip={id:'control-trip',title:'Controls trip',status:'active',leader_id:options.leader===false?'control-friend':user.id,starts_at:Date.now()/1000-60,ends_at:Date.now()/1000+3600,finished_at:null,participants:2,destination:'',my_role:options.guest?'passenger':'driver',navigation:null,
    vehicle_controls:options.guest?null:{vehicles,configured:true,actions:['frunk_open','rear_trunk_toggle','windows_vent','windows_close','climate_on','climate_off']},
    participants_detail:[{...user,role:options.guest?'passenger':'driver',vehicle_id:options.guest?null:'car-max',vehicle_name:'Max Tesla',model:'Model 3',online:true,left_at:null,data:{latitude:49.872,longitude:8.65,battery_pct:60,range_km:280},personal_location:null}],album:{status:'planned',name:'Test album',url:null}};
  await page.route('**/api/config',route=>route.fulfill({json:{demo:false,tesla_ready:true,group_controls:true}}));
  await page.route('**/api/me',route=>route.fulfill({json:user}));
  await page.route('**/api/trips',route=>route.fulfill({json:[trip]}));
  for(const path of ['/api/invites','/api/vehicles']) await page.route('**'+path,route=>route.fulfill({json:[]}));
  await page.route('**/api/trips/control-trip',route=>route.fulfill({json:trip}));
  await page.route('**/api/trips/control-trip/messages',route=>route.fulfill({json:[]}));
  await page.route('**/api/trips/control-trip/controls/consent',route=>{vehicles[0].allowed=route.request().method()==='POST';return route.fulfill({json:trip.vehicle_controls});});
  return {trip,user};
}

test('leader confirms separate comfort buttons and only sends the displayed consenting cars',async({page})=>{
  await mockTrip(page);const sent:any[]=[];
  await page.route('**/api/trips/control-trip/controls',route=>{const body=route.request().postDataJSON();sent.push(body);return route.fulfill({json:{request_id:body.request_id,action:body.action,status:'completed',vehicles:body.vehicle_ids.map((id:string)=>({vehicle_id:id,display_name:id==='car-max'?'Max':'Anna',vehicle_name:id==='car-max'?'Max Tesla':'Anna Tesla',status:id==='car-max'?'demo':'error',message:id==='car-max'?'Nur Demo, kein Fahrzeugbefehl.':'Test: Fahrzeug schläft.'}))}});});
  await page.goto('/trip/control-trip');
  const panel=page.getByRole('region',{name:'Komfortsteuerung der Gruppe'});
  await panel.getByRole('button',{name:'Fahrzeuge steuern',exact:true}).click();
  await expect(panel).toContainText('1 von 2 Fahrzeugen freigegeben');
  await expect(panel.getByRole('button',{name:'Klima an',exact:true})).toBeVisible();await expect(panel.getByRole('button',{name:'Klima aus',exact:true})).toBeVisible();
  await expect(panel.getByRole('button',{name:/verriegeln|entriegeln/i})).toHaveCount(0);
  await panel.getByRole('button',{name:'Klima an',exact:true}).click();
  let confirm=page.getByRole('dialog',{name:'Klima an für die Gruppe?'});
  await expect(confirm).toContainText('Anna · Anna Tesla');await expect(confirm).not.toContainText('Max · Max Tesla');
  await confirm.getByRole('button',{name:'Abbrechen',exact:true}).click();expect(sent).toEqual([]);
  await panel.getByRole('button',{name:'Komfortsteuerung für mein Auto erlauben',exact:true}).click();
  await expect(panel).toContainText('2 von 2 Fahrzeugen freigegeben');
  for(const [label,action] of [['Klima an','climate_on'],['Klima aus','climate_off']]) {
    await panel.getByRole('button',{name:label,exact:true}).click();confirm=page.getByRole('dialog',{name:label+' für die Gruppe?'});
    await confirm.getByRole('button',{name:'Jetzt an diese Fahrzeuge senden',exact:true}).click();
    await expect(panel.getByRole('status')).toContainText('Max · Max Tesla: Demo');await expect(panel.getByRole('status')).toContainText('Anna · Anna Tesla: Fehlgeschlagen');
    expect(sent.at(-1).action).toBe(action);expect(sent.at(-1).vehicle_ids).toEqual(['car-max','car-anna']);expect(sent.at(-1).request_id).toMatch(/^[0-9a-f-]{36}$/);
  }
  await panel.getByRole('button',{name:'Komfortsteuerung für mein Auto widerrufen',exact:true}).click();await expect(panel).toContainText('1 von 2 Fahrzeugen freigegeben');
  expect(sent).toHaveLength(2);
  await page.setViewportSize({width:390,height:844});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
});

test('a driver sees own consent without leader buttons and a passenger sees no controls',async({page})=>{
  await mockTrip(page,{leader:false});await page.goto('/trip/control-trip');
  await expect(page.getByRole('button',{name:'Komfortsteuerung für mein Auto erlauben',exact:true})).toBeVisible();
  await expect(page.getByRole('button',{name:'Fahrzeuge steuern',exact:true})).toHaveCount(0);
  await mockTrip(page,{leader:false,guest:true});await page.reload();
  await expect(page.getByRole('heading',{name:'Controls trip',exact:true})).toBeVisible();
  await expect(page.getByRole('region',{name:'Komfortsteuerung der Gruppe'})).toHaveCount(0);
});

test('interrupted comfort request offers read-only status without posting another command',async({page})=>{
  await mockTrip(page);let posts=0,reads=0;
  await page.route('**/api/trips/control-trip/controls',route=>{posts++;return route.abort('connectionreset');});
  await page.route('**/api/trips/control-trip/controls/*',route=>{reads++;return route.fulfill({json:{request_id:'test',action:'climate_on',status:'completed',vehicles:[{vehicle_id:'car-anna',display_name:'Anna',vehicle_name:'Anna Tesla',status:'unknown',message:'Ergebnis am Auto prüfen.'}]}});});
  await page.goto('/trip/control-trip');await page.getByRole('button',{name:'Fahrzeuge steuern',exact:true}).click();await page.getByRole('button',{name:'Klima an',exact:true}).click();
  await page.getByRole('dialog').getByRole('button',{name:'Jetzt an diese Fahrzeuge senden',exact:true}).click();
  await expect(page.getByRole('button',{name:'Klima an',exact:true})).toBeDisabled();
  await page.getByRole('button',{name:'Auftragsstatus abrufen',exact:true}).click();
  await expect(page.getByRole('status',{name:'Ergebnisse der Fahrzeugsteuerung'})).toContainText('Ergebnis unklar');expect(posts).toBe(1);expect(reads).toBe(1);
});

test('OSM tiles receive only the origin Referer; failed tiles can be reloaded and logo goes home',async({page})=>{
  await mockTrip(page);const headers:string[]=[];let fail=true;
  await page.route('https://tile.openstreetmap.org/**',async route=>{headers.push((await route.request().allHeaders()).referer||'');return route.fulfill({status:fail?403:200,contentType:'image/png',body:fail?'':mapTile});});
  await page.goto('/trip/control-trip');
  await expect(page.getByText('Kartenkacheln konnten nicht geladen werden.',{exact:true})).toBeVisible();
  expect(headers.length).toBeGreaterThan(0);expect(new Set(headers)).toEqual(new Set(['http://localhost:8780/']));
  const before=headers.length;fail=false;await page.getByRole('button',{name:'Karte erneut laden',exact:true}).click();
  await expect(page.getByText('Kartenkacheln konnten nicht geladen werden.',{exact:true})).toHaveCount(0);await expect.poll(()=>headers.length).toBeGreaterThan(before);
  await expect(page.locator('.leaflet-control-attribution')).toContainText('OpenStreetMap');
  await page.getByRole('link',{name:'TeslaTalk – Startseite',exact:true}).click();await expect(page).toHaveURL('http://localhost:8780/');await expect(page.getByRole('heading',{name:'Deine Fahrten.'})).toBeVisible();
  await expect(page.locator('link[rel="icon"][href="/favicon.ico?v=6"]')).toHaveCount(1);
  for(const asset of ['/favicon.ico?v=6','/favicon-32-v6.png','/favicon-64-v6.png']) {
    const response=await page.request.get(asset);expect(response.ok()).toBe(true);expect(response.headers()['content-type']).not.toContain('text/html');expect((await response.body()).length).toBeGreaterThan(100);
  }
});
