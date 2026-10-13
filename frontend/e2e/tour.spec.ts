import { test, expect, type Page, type WebSocketRoute } from '@playwright/test';
import { mockMapTiles } from './map-tiles';
test.beforeEach(async({context})=>{await mockMapTiles(context);});

async function fixture(page:Page,{leader=true,gps=false,guest=false}={}) {
  await page.addInitScript(({gps})=>{
    if(!gps)localStorage.setItem('teslatalk-gps-tour-test','off');
    (window as any).tones=0;
    class Audio {
      state='running';currentTime=0;destination={};
      resume(){return Promise.resolve();}
      createOscillator(){(window as any).tones++;return {frequency:{value:0},connect(){},start(){},stop(){}};}
      createGain(){return {gain:{setValueAtTime(){},linearRampToValueAtTime(){},exponentialRampToValueAtTime(){}},connect(){}};}
    }
    (window as any).AudioContext=Audio;
  },{gps});
  const user={id:leader?'tour-leader':'tour-friend',display_name:leader?'Max':'Anna',username:'TourTest',provider:guest?'guest':'demo',favorite_vehicle:guest?null:'tour-car'};
  const cars=[{user_id:'tour-leader',display_name:'Max',vehicle_id:'tour-car',vehicle_name:'Max Tesla',accepted:true,can_plan:true,is_planner:true,battery_pct:60,range_km:300,updated_at:Date.now()/1000,status:'unconfirmed',problem:null},
    {user_id:'tour-friend',display_name:'Anna',vehicle_id:'friend-car',vehicle_name:'Anna Tesla',accepted:true,can_plan:true,is_planner:false,battery_pct:45,range_km:220,updated_at:Date.now()/1000,status:'unconfirmed',problem:null}];
  const trip:any={id:'tour-test',title:'Tour feature test',leader_id:'tour-leader',starts_at:Date.now()/1000-60,ends_at:Date.now()/1000+3600,status:'active',finished_at:null,my_role:guest?'passenger':'driver',destination:'Hamburg',participants:2,navigation:null,vehicle_controls:null,album:{status:'planned',name:'Album',url:null},pause_requests:[],charging_plan:null,spectator_link_active:false,
    participants_detail:cars.map(car=>({id:car.user_id,display_name:car.display_name,vehicle_id:car.vehicle_id,vehicle_name:car.vehicle_name,model:'Model 3',role:'driver',left_at:null,online:true,data:{latitude:50.1,longitude:8.7,position_updated_at:Date.now()/1000,battery_pct:car.battery_pct},personal_location:null})),
    route_overview:{planner_user_id:'tour-leader',vehicles:cars,recommendations:{lowest_battery_user_id:'tour-friend',lowest_range_user_id:'tour-friend'},transfer_mode:'destination_only',charging_stops_confirmed:false}};
  if(guest)trip.participants_detail.push({...user,vehicle_id:null,role:'passenger',left_at:null,data:{},personal_location:null});
  for(const [path,value] of [['/api/config',{demo:false,tesla_ready:true,group_controls:false,voice_ready:false}],['/api/me',user],['/api/trips',[trip]],['/api/invites',[]],['/api/vehicles',[]],['/api/trips/tour-test/messages',[]]])
    await page.route('**'+path,route=>route.fulfill({json:value}));
  await page.route('**/api/trips/tour-test',route=>route.fulfill({json:trip}));
  const samples:any[]=[];const deletes:string[]=[];
  await page.route('**/api/trips/tour-test/samples',route=>{samples.push(route.request().postDataJSON());return route.fulfill({json:{ok:true}});});
  await page.route('**/api/trips/tour-test/location**',route=>{deletes.push(route.request().url());return route.fulfill({json:{ok:true}});});
  let socket:WebSocketRoute|undefined;
  await page.routeWebSocket('**/api/ws/trips/tour-test',ws=>{socket=ws;});
  return {trip,user,cars,samples,deletes,event:(value:any)=>socket?.send(JSON.stringify(value))};
}

test('driver browser GPS updates car position and can stop without paid vehicle reads',async({page,context})=>{
  await context.grantPermissions(['geolocation']);await context.setGeolocation({latitude:50.1,longitude:8.7});
  const data=await fixture(page,{gps:true});let paid=0;
  await page.route('**/api/vehicles/*/refresh',route=>{paid++;return route.fulfill({json:{}});});
  await page.goto('/trip/tour-test');
  await expect.poll(()=>data.samples.length).toBeGreaterThan(0);
  expect(data.samples[0].source).toBe('browser_vehicle');expect(data.samples[0].latitude).toBeCloseTo(50.1);expect(data.samples[0].device_id).toBeTruthy();
  expect(data.samples[0].battery_pct).toBeUndefined();expect(paid).toBe(0);
  await page.getByRole('button',{name:'Meinen Standort verfolgen',exact:true}).click();
  await expect(page.getByRole('button',{name:'Meinen Standort verfolgen',exact:true})).toHaveAttribute('aria-pressed','true');
  await page.getByRole('button',{name:'Kartenverfolgung pausieren',exact:true}).click();
  await expect(page.getByRole('button',{name:'Karte mitlaufen lassen',exact:true})).toHaveAttribute('aria-pressed','true');
  await page.getByRole('button',{name:'Standortfreigabe stoppen',exact:true}).click();
  await expect.poll(()=>data.deletes.length).toBe(1);expect(data.deletes[0]).toContain('source=browser_vehicle');expect(data.deletes[0]).toContain('device_id=');expect(paid).toBe(0);
});

test('pause request alerts leader, confirmation shows all participants a message and one tone',async({page,context})=>{
  const followerPage=await context.newPage();const leader=await fixture(page),follower=await fixture(followerPage,{leader:false,guest:true});
  const request={id:'pause-id',user_id:follower.user.id,display_name:'Anna',created_at:Date.now()/1000};
  await followerPage.route('**/api/trips/tour-test/toilet',route=>{
    leader.trip.pause_requests=[request];follower.trip.pause_requests=[request];
    leader.event({type:'pause',pause_requests:[request],alert:{id:request.id,recipient_id:leader.user.id,name:'Anna'}});
    follower.event({type:'pause',pause_requests:[request],alert:{id:request.id,recipient_id:leader.user.id,name:'Anna'}});
    return route.fulfill({json:{pause_requests:[request]}});
  });
  const message={id:'departure-id',user_id:leader.user.id,display_name:'Max',created_at:Date.now()/1000,kind:'toilet_departure',text:'Wir fahren jetzt zur Toilettenpause ab. Bitte der Gruppe folgen.'};
  await page.route('**/api/trips/tour-test/toilet/confirm',route=>{
    expect(route.request().postDataJSON().request_ids).toEqual(['pause-id']);leader.trip.pause_requests=[];follower.trip.pause_requests=[];
    for(const data of [leader,follower]){data.event({type:'pause',pause_requests:[]});data.event({type:'message',message,sound:true});}
    return route.fulfill({json:{pause_requests:[],message}});
  });
  await page.goto('/trip/tour-test');await followerPage.goto('/trip/tour-test');
  for(const target of [page,followerPage])await target.getByRole('button',{name:'Hinweistöne aktivieren',exact:true}).click();
  await followerPage.getByRole('button',{name:'Ich muss aufs Klo',exact:true}).click();
  await expect(page.getByRole('alert')).toContainText('Anna');
  await expect.poll(()=>page.evaluate(()=>(window as any).tones)).toBe(2);
  expect(await followerPage.evaluate(()=>(window as any).tones)).toBe(0);
  await expect(followerPage.getByRole('button',{name:'Wir fahren jetzt zur Toilettenpause ab',exact:true})).toHaveCount(0);
  await page.getByRole('button',{name:'Wir fahren jetzt zur Toilettenpause ab',exact:true}).click();
  for(const target of [page,followerPage])await expect(target.getByRole('status').filter({hasText:message.text})).toBeVisible();
  await expect.poll(()=>page.evaluate(()=>(window as any).tones)).toBe(4);
  await expect.poll(()=>followerPage.evaluate(()=>(window as any).tones)).toBe(2);
  await followerPage.getByRole('button',{name:'Chat',exact:true}).click();await expect(followerPage.locator('.message-list')).toContainText(message.text);
});

test('reviewed file plan keeps station references, sends next stop and requires in-car confirmation',async({page})=>{
  const data=await fixture(page);const stop={name:'IONITY Teststation',latitude:50.1,longitude:8.7,kind:'charging',operator:'IONITY',address:'Testadresse',google_place_id:'ChIJ_Test'};let sends=0;let previewBody:any;
  await page.route('**/api/trips/tour-test/charging-plan/preview',route=>{previewBody=route.request().postDataJSON();return route.fulfill({json:{title:'Imported trip',stops:[stop]}});});
  await page.route('**/api/trips/tour-test/charging-plan',route=>{const body=route.request().postDataJSON();data.trip.charging_plan={...body,version:'plan-version',current_stop:null,confirmations:[]};return route.fulfill({json:data.trip.charging_plan});});
  await page.route('**/api/trips/tour-test/charging-plan/send',route=>{sends++;expect(route.request().postDataJSON()).toMatchObject({version:'plan-version',stop_index:0});data.trip.charging_plan.current_stop=0;return route.fulfill({json:{request_id:'saved',status:'completed',vehicles:[{user_id:data.user.id,status:'accepted',message:'Navi-Befehl angenommen; Ladestation und Vorkonditionierung im Auto prüfen.'}]}});});
  await page.route('**/api/trips/tour-test/charging-plan/confirm',route=>{const body=route.request().postDataJSON();data.trip.charging_plan.confirmations=[{...body,user_id:data.user.id}];return route.fulfill({json:data.trip.charging_plan});});
  await page.goto('/trip/tour-test');const panel=page.getByRole('region',{name:'Gemeinsamer Ladeplan'});
  await panel.getByLabel('Routen-Datei hochladen').setInputFiles({name:'ABRP.xlsx',mimeType:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',buffer:Buffer.from('isolated Excel fixture')});
  await expect(panel.getByLabel('Google-Places-ID (optional)')).toHaveValue('ChIJ_Test');expect(previewBody.filename).toBe('ABRP.xlsx');expect(previewBody.encoding).toBe('base64');expect(Buffer.from(previewBody.content,'base64').toString()).toBe('isolated Excel fixture');expect(sends).toBe(0);
  await panel.getByRole('button',{name:'Geprüften Ladeplan speichern',exact:true}).click();expect(sends).toBe(0);
  await panel.getByRole('button',{name:'Diesen Halt an die freigegebenen Autos senden',exact:true}).click();
  await expect(panel.getByLabel('Vorkonditionierung wird im Auto angezeigt.')).toBeDisabled();
  await panel.getByLabel('Tesla zeigt diesen Halt als Ladestation.').click();
  await expect(panel.getByLabel('Tesla zeigt diesen Halt als Ladestation.')).toBeChecked();
  await panel.getByLabel('Vorkonditionierung wird im Auto angezeigt.').click();
  await expect(panel.getByLabel('Vorkonditionierung wird im Auto angezeigt.')).toBeChecked();
  await expect(panel).toContainText('Vorkonditionierung bestätigt');expect(sends).toBe(1);
  await expect(panel.getByRole('link',{name:'Ladeplan exportieren',exact:true})).toHaveAttribute('href','/api/trips/tour-test/charging-plan/export');
});

test('live viewer map has no participant actions and clears when link expires',async({page})=>{
  await page.clock.install();let valid=true;
  await page.route('**/api/config',route=>route.fulfill({json:{demo:false}}));
  await page.route('**/api/me',route=>route.fulfill({status:401,json:{detail:'Nicht angemeldet'}}));
  await page.route('**/api/spectator/watch-token',route=>route.fulfill(valid?{json:{title:'Watching trip',destination:'Hamburg',status:'active',participants:[{id:'pseudonym',vehicle_id:'watch-car',display_name:'Max',vehicle_name:'Tesla',model:'Model 3',role:'driver',left_at:null,data:{latitude:50.1,longitude:8.7,position_updated_at:Date.now()/1000}}]}}:{status:404,json:{detail:'Zuschauerlink ist nicht mehr aktiv.'}}));
  await page.goto('/watch/watch-token');await expect(page.locator('.car-marker')).toHaveCount(1);
  await expect(page.getByRole('button',{name:/Klo|Klima|senden|Standort teilen/i})).toHaveCount(0);await expect(page.getByRole('textbox')).toHaveCount(0);
  valid=false;await page.clock.fastForward(10000);await expect(page.getByRole('alert')).toHaveText('Zuschauerlink ist nicht mehr aktiv.');await expect(page.locator('.car-marker')).toHaveCount(0);
});
