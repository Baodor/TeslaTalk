import { test, expect, type Page } from '@playwright/test';
import { mockMapTiles } from './map-tiles';
test.beforeEach(async({context})=>{await mockMapTiles(context);});
const typecode='tesla:test:variant';
const status={configured:true,connected:true,username:'Benny',expires_at:Date.now()/1000+300,daily_limit:20};
const catalog={...status,models:[{typecode,title:'Model 3 exact variant',manufacturer:'Tesla'}],networks:[{id:85,name:'IONITY'},{id:86,name:'EnBW'}]};
async function fixture(page:Page,leader=true,paid=true) {
  await page.addInitScript(()=>localStorage.setItem('teslatalk-gps-abrp-trip','off'));
  const uid=leader?'abrp-leader':'abrp-friend';const user={id:uid,provider:'demo',username:'ABRPTest',display_name:'Benny',favorite_vehicle:'car',plate:null};
  const cars=[{user_id:'abrp-leader',display_name:'Benny',vehicle_name:'Model 3',vehicle_id:'car',battery_pct:70,range_km:300,accepted:true,can_plan:true,updated_at:Date.now()/1000,status:'waiting'},
    {user_id:'abrp-friend',display_name:'Anna',vehicle_name:'Model Y',vehicle_id:'friend-car',battery_pct:45,range_km:200,accepted:true,can_plan:true,updated_at:Date.now()/1000,status:'waiting'}];
  const trip:any={id:'abrp-trip',title:'ABRP group',destination:'Hamburg',leader_id:'abrp-leader',status:'active',my_role:'driver',starts_at:Date.now()/1000-60,ends_at:Date.now()/1000+3600,finished_at:null,pause_requests:[],vehicle_controls:null,charging_plan:null,navigation:null,album:{status:'planned'},
    participants_detail:cars.map(car=>({id:car.user_id,vehicle_id:car.vehicle_id,display_name:car.display_name,vehicle_name:car.vehicle_name,model:'Model 3',role:'driver',left_at:null,data:{latitude:49.87,longitude:8.65,position_updated_at:Date.now()/1000,battery_pct:car.battery_pct},personal_location:null})),
    route_overview:{vehicles:cars,planner_user_id:null,recommendations:{lowest_range_user_id:'abrp-friend',lowest_battery_user_id:'abrp-friend'}}};
  for(const [url,data] of [['/api/config',{demo:false,tesla_ready:true}],['/api/me',user],['/api/trips',[trip]],['/api/vehicles',[]],['/api/invites',[]],['/api/trips/abrp-trip/messages',[]],['/api/me/abrp',status],['/api/abrp/catalog',catalog]])await page.route('**'+url,route=>route.fulfill({json:data}));
  await page.route('**/api/trips/abrp-trip',route=>route.fulfill({json:trip}));
  await page.routeWebSocket('**/api/ws/trips/abrp-trip',()=>{});
  await page.goto('/trip/abrp-trip');await page.getByRole('button',{name:'Ladeplanung',exact:true}).click();
  if(leader&&paid)await page.getByRole('button',{name:'Optionale kostenpflichtige API anzeigen',exact:true}).click();
  return trip;
}
const plan={title:'Computed plan',source:'abrp',origin:{name:'Start',latitude:49.87,longitude:8.65,kind:'waypoint'},route_points:[[49.87,8.65],[51,9],[53.55,10]],distance_km:500,duration_minutes:300,
  stops:[{name:'IONITY station',latitude:51,longitude:9,kind:'charging',operator:'IONITY',address:'',google_place_id:'ChIJ_Verified',charger_id:42,arrival_soc:25,departure_soc:80,charge_minutes:20},
  {name:'Hamburg',latitude:53.55,longitude:10,kind:'destination',operator:'',address:'',google_place_id:null}]};
async function fill(page:Page){const panel=page.getByRole('region',{name:'ABRP-Ladeplanung'});await panel.getByRole('combobox',{name:'Fahrzeugmodell in ABRP',exact:true}).selectOption(typecode);await panel.getByLabel('Start',{exact:true}).fill('Darmstadt');await panel.getByLabel('Ziel',{exact:true}).fill('Hamburg');return panel;}

test('ABRP tab selects limiting car, exact model, multiple networks and preserves real station references',async({page})=>{
  const trip=await fixture(page);let posts=0,saves=0,commands=0;let submitted:any;
  await page.route('**/api/trips/abrp-trip/abrp/plan',route=>{posts++;submitted=route.request().postDataJSON();return route.fulfill({json:{status:'completed',request_id:submitted.request_id,plan}});});
  await page.route('**/api/trips/abrp-trip/charging-plan',route=>{saves++;const data=route.request().postDataJSON();trip.charging_plan={...data,version:'v1',current_stop:null,confirmations:[]};return route.fulfill({json:trip.charging_plan});});
  await page.route('**/api/trips/abrp-trip/charging-plan/send',route=>{commands++;return route.fulfill({json:{status:'completed',vehicles:[]}});});
  const panel=await fill(page);
  await expect(panel.getByLabel('Fahrzeug für die Berechnung')).toHaveValue('abrp-friend');await expect(panel.getByLabel('Akku bei Abfahrt (%)')).toHaveValue('45');
  await panel.getByLabel('IONITY',{exact:true}).check();await panel.getByLabel('EnBW',{exact:true}).check();await panel.getByLabel('Ausschließlich bei den ausgewählten Ladenetzen laden').check();
  await panel.getByRole('button',{name:'Zwischenstopp hinzufügen',exact:true}).click();await panel.getByLabel('Zwischenstopp',{exact:true}).fill('Kassel');
  await expect(panel.getByRole('button',{name:'Laderoute berechnen',exact:true})).toBeDisabled();
  await panel.getByLabel(/Ich bestätige die mögliche kostenpflichtige/).check();await panel.getByRole('button',{name:'Laderoute berechnen',exact:true}).click();
  const preview=page.getByRole('region',{name:'Gemeinsamer Ladeplan'});await expect(preview.getByLabel('Google-Places-ID (optional)').first()).toHaveValue('ChIJ_Verified');
  expect(submitted).toMatchObject({planner_user_id:'abrp-friend',typecode,departure_soc:45,network_ids:[85,86],exclusive:true,costs_confirmed:true});expect(submitted.destinations.map((row:any)=>row.value)).toEqual(['Darmstadt','Kassel','Hamburg']);
  expect(posts).toBe(1);expect(saves).toBe(0);expect(commands).toBe(0);await expect(preview.locator('.leaflet-container')).toBeVisible();
  await preview.getByRole('button',{name:'Geprüften Ladeplan speichern',exact:true}).click();await expect(preview.getByRole('heading',{name:'Computed plan',exact:true})).toBeVisible();expect(saves).toBe(1);expect(commands).toBe(0);
  await expect(preview).toContainText('Ankunftsakku 25%');await preview.getByRole('button',{name:'Diesen Halt an die freigegebenen Autos senden',exact:true}).first().click();await expect.poll(()=>commands).toBe(1);
});

test('ABRP link loads parameters without creating a charged plan',async({page})=>{
  let posts=0;await fixture(page);
  await page.route('**/api/trips/abrp-trip/abrp/plan',route=>{posts++;return route.abort();});
  await page.route('**/api/trips/abrp-trip/abrp/link',route=>route.fulfill({json:{destinations:[{value:'Lund',stay_minutes:0},{value:'Berlin',stay_minutes:20}],typecode,departure_soc:60,arrival_soc:15,network_ids:[86],exclusive:true,kind:'parameters_only',notice:'Start, Ziele, Fahrzeug, Akku und ausgewählte Ladenetze wurden übernommen. Weitere ABRP-Einstellungen bleiben in ABRP. Eine neue Berechnung kann vom gespeicherten Plan abweichen.'}}));
  const panel=page.getByRole('region',{name:'ABRP-Ladeplanung'});await panel.getByLabel('ABRP-Teilen-Link').fill('https://abetterrouteplanner.com/?plan_uuid=123e4567-e89b-12d3-a456-426614174000');
  await panel.getByRole('button',{name:'Planungsparameter aus Link übernehmen',exact:true}).click();await expect(panel.getByLabel('Start',{exact:true})).toHaveValue('Lund');await expect(panel.getByLabel('Ziel',{exact:true})).toHaveValue('Berlin');await expect(panel.getByRole('status')).toContainText('Eine neue Berechnung kann');expect(posts).toBe(0);
});

test('an interrupted ABRP calculation preserves status across tab changes and never reposts automatically',async({page})=>{
  await fixture(page);let posts=0,reads=0;
  await page.route('**/api/trips/abrp-trip/abrp/plan',route=>{posts++;return route.abort('connectionreset');});
  await page.route('**/api/trips/abrp-trip/abrp/requests/*',route=>{reads++;return route.fulfill({json:{status:'completed',plan}});});
  const panel=await fill(page);await panel.getByLabel(/Ich bestätige die mögliche kostenpflichtige/).check();await panel.getByRole('button',{name:'Laderoute berechnen',exact:true}).click();await expect(panel.getByRole('button',{name:'Laderoute berechnen',exact:true})).toBeDisabled();
  await page.getByRole('button',{name:'Karte',exact:true}).click();await page.getByRole('button',{name:'Ladeplanung',exact:true}).click();
  await panel.getByRole('button',{name:'Berechnungsstatus abrufen',exact:true}).click();await expect(page.getByRole('region',{name:'Gemeinsamer Ladeplan'}).getByLabel('Name des Ladeplans')).toHaveValue('Computed plan');expect(posts).toBe(1);expect(reads).toBe(1);
});

test('other drivers can view charging planning but have no account or calculate controls',async({page})=>{
  await fixture(page,false);await expect(page.getByRole('button',{name:'Laderoute berechnen',exact:true})).toHaveCount(0);await expect(page.getByRole('button',{name:'ABRP-Konto verbinden',exact:true})).toHaveCount(0);
  await expect(page.getByText('Der Fahrtleiter plant die gemeinsamen Ladehalte.',{exact:false})).toBeVisible();
});


test('free ABRP handoff uses cached group car data, opens only destinations and never contacts paid services',async({page})=>{
  let paid=0,account=0,commands=0;
  page.on('request',request=>{
    const path=new URL(request.url()).pathname;
    if(path==='/api/me/abrp')account++;
    if(path==='/api/abrp/catalog'||path==='/api/trips/abrp-trip/abrp/plan')paid++;
    if(path.endsWith('/charging-plan/send'))commands++;
  });
  await fixture(page,true,false);
  const panel=page.getByRole('region',{name:'ABRP ohne Planning-Key'});
  await expect(panel.getByRole('combobox',{name:'Planungsfahrzeug aus TeslaTalk',exact:true})).toHaveValue('abrp-friend');
  await expect(panel.getByLabel('Akku bei Abfahrt (%)')).toHaveValue('45');
  await panel.getByRole('button',{name:'Browserstandort als Start',exact:true}).click();
  await panel.getByLabel('Ziel',{exact:true}).fill('Hamburg');
  await panel.getByRole('button',{name:'Zwischenstopp hinzufügen',exact:true}).click();
  await panel.getByLabel('Zwischenstopp',{exact:true}).fill('Kassel');
  await expect(panel.getByRole('button',{name:'ABRP-Link und QR-Code vorbereiten',exact:true})).toBeDisabled();
  await panel.getByLabel(/Ich möchte diese Start-/).check();
  await panel.getByRole('button',{name:'ABRP-Link und QR-Code vorbereiten',exact:true}).click();
  const url=new URL((await panel.getByRole('link',{name:'Route in ABRP öffnen',exact:true}).getAttribute('href'))!);
  expect(url.origin).toBe('https://abetterrouteplanner.com');
  expect(JSON.parse(url.searchParams.get('destinations')!)).toEqual([{lat:49.87,lon:8.65},{address:'Kassel'},{address:'Hamburg'}]);
  expect([...url.searchParams.keys()]).toEqual(['destinations']);
  await expect(panel.getByRole('img',{name:'QR-Code zum Öffnen der Route in ABRP'})).toBeVisible();
  await expect(panel).toContainText('Der Öffnen-Link synchronisiert keine Fahrzeugdaten');
  await panel.getByRole('combobox',{name:'Planungsfahrzeug aus TeslaTalk',exact:true}).selectOption('abrp-leader');
  await expect(panel.getByLabel('Akku bei Abfahrt (%)')).toHaveValue('70');
  await expect(panel.getByRole('link',{name:'Route in ABRP öffnen',exact:true})).toHaveCount(0);
  expect(paid).toBe(0);expect(commands).toBe(0);expect(account).toBe(0);
});

test('free handoff rejects invalid coordinates and explains where the actual login QR is generated',async({page})=>{
  await fixture(page,true,false);
  const panel=page.getByRole('region',{name:'ABRP ohne Planning-Key'});
  await panel.getByLabel('Start',{exact:true}).fill('95, 8');await panel.getByLabel('Ziel',{exact:true}).fill('Berlin');
  await panel.getByLabel(/Ich möchte diese Start-/).check();await panel.getByRole('button',{name:'ABRP-Link und QR-Code vorbereiten',exact:true}).click();
  await expect(panel.getByRole('alert')).toContainText('Ungültige Planungskoordinaten.');
  await expect(panel.getByRole('link',{name:'Route in ABRP öffnen',exact:true})).toHaveCount(0);
  await panel.locator('summary').click();await expect(panel).toContainText('Der Anmelde-QR-Code wird von ABRP selbst erzeugt.');
  await expect(panel.getByLabel('ABRP-Passwort')).toHaveCount(0);
});
