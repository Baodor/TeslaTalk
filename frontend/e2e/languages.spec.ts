import { test, expect, type Page, type BrowserContext } from '@playwright/test';
import { mockMapTiles } from './map-tiles';

async function signedOut(page: Page) {
  await page.route('**/api/config',route=>route.fulfill({json:{demo:true,tesla_ready:true}}));
  await page.route('**/api/me',route=>route.fulfill({status:401,json:{detail:'Bitte anmelden.'}}));
}
async function dashboard(page: Page, push=false, guest=false) {
  await page.route('**/api/config',route=>route.fulfill({json:{demo:false,tesla_ready:true,push_ready:push}}));
  await page.route('**/api/me',route=>route.fulfill({json:{id:'language-driver',username:'Karte',display_name:'Karte',provider:guest?'guest':'tesla',plate:null,favorite_vehicle:null}}));
  for(const path of ['/api/trips','/api/invites','/api/vehicles','/api/keys']) await page.route('**'+path,route=>route.fulfill({json:[]}));
}
async function openSettings(page: Page) {
  await page.getByRole('button',{name:/^(Mein Profil|My profile|Mijn profiel)$/}).click();
  await expect(page.getByRole('combobox')).toBeVisible();
}
async function settingsTab(context: BrowserContext) {
  const page=await context.newPage();await dashboard(page);await page.goto('/');await openSettings(page);return page;
}

for(const [locale,language,heading] of [
  ['de-CH','de','Bereit für die nächste Fahrt?'],
  ['en-US','en','Ready for the next trip?'],
  ['nl-BE','nl','Klaar voor de volgende rit?'],
  ['fr-FR','en','Ready for the next trip?'],
]) test(`automatically detects ${locale} as ${language}`,async({browser})=>{
  const context=await browser.newContext({locale});
  try {
    const page=await context.newPage();await signedOut(page);await page.goto('/');
    await expect(page.locator('html')).toHaveAttribute('lang',language);
    await expect(page.getByRole('heading',{name:heading})).toBeVisible();
    await expect(page.getByRole('combobox')).toHaveCount(0);
    await dashboard(page);await page.reload();
    await expect(page.getByRole('combobox')).toHaveCount(0);
    await openSettings(page);await expect(page.getByRole('combobox')).toHaveValue('auto');
    await page.setViewportSize({width:390,height:844});
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  } finally {await context.close();}
});

test('respects language priority, persists manual choice and restores automatic detection',async({page})=>{
  await page.addInitScript(()=>Object.defineProperty(navigator,'languages',{configurable:true,get:()=>['fr-FR','nl-BE','de-DE']}));
  await dashboard(page);await page.goto('/');await openSettings(page);
  await expect(page.locator('html')).toHaveAttribute('lang','nl');
  const choice=page.getByRole('combobox');await choice.selectOption('en');
  await expect(page.locator('html')).toHaveAttribute('lang','en');
  await page.reload();await openSettings(page);await expect(choice).toHaveValue('en');await expect(page.locator('html')).toHaveAttribute('lang','en');
  await choice.selectOption('auto');await expect(page.locator('html')).toHaveAttribute('lang','nl');
  await page.evaluate(()=>{Object.defineProperty(navigator,'languages',{get:()=>['de-AT']});dispatchEvent(new Event('languagechange'));});
  await expect(page.locator('html')).toHaveAttribute('lang','de');
  await choice.selectOption('en');
  await expect(choice.locator('option[value="auto"]')).toContainText('Deutsch');
  await page.evaluate(()=>{Object.defineProperty(navigator,'languages',{get:()=>['nl-NL']});dispatchEvent(new Event('languagechange'));});
  await expect(page.locator('html')).toHaveAttribute('lang','en');
  await expect(choice.locator('option[value="auto"]')).toContainText('Nederlands');
});

test('manual switching works without localStorage and invalid saved values use detection',async({page})=>{
  await page.addInitScript(()=>{
    localStorage.setItem('teslatalk-language','invalid');
    Storage.prototype.setItem=()=>{throw new DOMException('Storage disabled','SecurityError');};
  });
  await dashboard(page,false,true);await page.goto('/');await openSettings(page);
  await expect(page.locator('html')).toHaveAttribute('lang','de');
  await page.getByRole('combobox').selectOption('nl');
  await expect(page.locator('html')).toHaveAttribute('lang','nl');
  await expect(page.getByRole('region',{name:'Taal',exact:true})).toContainText('Je keuze wordt op dit apparaat opgeslagen.');
});

test('switching from settings preserves open forms in another tab without submitting or reloading',async({page,context})=>{
  await dashboard(page);const writes:string[]=[];
  page.on('request',request=>{if(request.url().includes('/api/')&&request.method()!=='GET')writes.push(request.url());});
  await page.goto('/');await page.getByRole('button',{name:'Fahrt erstellen',exact:true}).click();
  const dialog=page.getByRole('dialog');
  await dialog.getByLabel('Name der Fahrt').fill('Karte');await dialog.getByLabel('Ziel',{exact:true}).fill('Verlauf');
  await expect(dialog.getByRole('combobox')).toHaveCount(0);
  const settings=await settingsTab(context);await settings.getByRole('combobox').selectOption('nl');
  await expect(dialog.getByRole('heading',{name:'Nieuwe rit aanmaken'})).toBeVisible();
  await expect(dialog.getByLabel('Naam van de rit')).toHaveValue('Karte');
  await expect(dialog.getByLabel('Bestemming',{exact:true})).toHaveValue('Verlauf');
  await expect(page.locator('.user-block strong')).toHaveText('Karte');
  expect(writes).toEqual([]);
  await dialog.getByRole('button',{name:'Sluiten',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Je ritten.'})).toBeVisible();
});

test('server errors already on screen change language with the form',async({page,context})=>{
  await signedOut(page);
  await page.route('**/api/demo/login',route=>route.fulfill({status:429,json:{detail:'Zu viele Versuche. Bitte kurz warten.'}}));
  await page.goto('/');await page.getByRole('button',{name:'Demo öffnen',exact:true}).click();
  await expect(page.getByRole('alert')).toHaveText('Zu viele Versuche. Bitte kurz warten.');
  const settings=await settingsTab(context);await settings.getByRole('combobox').selectOption('nl');
  await expect(page.getByRole('alert')).toHaveText('Te veel pogingen. Wacht even.');
  await settings.getByRole('combobox').selectOption('en');
  await expect(page.getByRole('alert')).toHaveText('Too many attempts. Please wait a moment.');
});

test('other tabs follow the saved preference',async({page,context})=>{
  await dashboard(page);await page.goto('/');await openSettings(page);
  const second=await settingsTab(context);
  await page.getByRole('combobox').selectOption('nl');
  await expect(second.locator('html')).toHaveAttribute('lang','nl');
  await expect(second.getByRole('combobox')).toHaveValue('nl');
});

test('changing language rebinds existing push consent without requesting permission or a new subscription',async({page})=>{
  const subscriptions:any[]=[];
  await page.addInitScript(()=>{
    const calls={permissions:0,subscriptions:0};(window as any).languagePushCalls=calls;
    Object.defineProperty(Notification,'permission',{get:()=> 'granted'});
    Notification.requestPermission=async()=>{calls.permissions++;return 'granted';};
    const subscription={endpoint:'https://web.push.apple.com/language-test',toJSON:()=>({endpoint:'https://web.push.apple.com/language-test',keys:{p256dh:'test',auth:'test'}}),unsubscribe:async()=>true};
    Object.defineProperty(navigator.serviceWorker,'ready',{value:Promise.resolve({pushManager:{getSubscription:async()=>subscription,subscribe:async()=>{calls.subscriptions++;return subscription;}}})});
  });
  await dashboard(page,true);
  await page.route('**/api/push/subscribe',route=>{subscriptions.push(route.request().postDataJSON());return route.fulfill({json:{ok:true}});});
  await page.goto('/');await expect.poll(()=>subscriptions.at(-1)?.language).toBe('de');
  await openSettings(page);
  await page.getByRole('combobox').selectOption('nl');
  await expect.poll(()=>subscriptions.at(-1)?.language).toBe('nl');
  expect(await page.evaluate(()=>(window as any).languagePushCalls)).toEqual({permissions:0,subscriptions:0});
  await expect(page.getByRole('region',{name:'Meldingen en webapp'})).toContainText('Ingeschakeld op dit apparaat.');
});

test('QR passenger registration and admin deletion are translated while retaining typed confirmation',async({page,context})=>{
  await page.route('**/api/config',route=>route.fulfill({json:{admin_ready:true}}));
  await page.route('**/api/guest/language-qr',route=>route.fulfill({json:{title:'Karte',active:true,starts_at:Date.now()/1000-60,ends_at:Date.now()/1000+3600}}));
  const settings=await settingsTab(context);await settings.getByRole('combobox').selectOption('nl');
  await page.goto('/guest/language-qr');await expect(page.getByRole('combobox')).toHaveCount(0);
  await expect(page.getByRole('button',{name:'Registreren en meerijden',exact:true})).toBeVisible();
  await expect(page.getByLabel('Kies je eigen pincode (6 cijfers)')).toBeVisible();
  await expect(page.getByRole('heading',{name:'Karte',exact:true})).toBeVisible();
  await page.route('**/api/admin',route=>route.fulfill({json:{users:1,trips:0,samples:0,push_ready:false}}));
  await page.route('**/api/admin/users',route=>route.fulfill({json:[{id:'language-user',provider:'tesla',display_name:'Karte',username:'Karte',email:null,plate:null,avatar_url:null,last_login_at:null}]}));
  await page.goto('/admin');await page.getByRole('button',{name:'Karte verwijderen',exact:true}).click();
  const dialog=page.getByRole('dialog');await dialog.getByLabel('Gebruikersnaam ter bevestiging').fill('Karte');
  await expect(dialog.getByRole('combobox')).toHaveCount(0);
  await settings.getByRole('combobox').selectOption('en');
  await expect(dialog.getByLabel('Username to confirm')).toHaveValue('Karte');
  await expect(dialog.getByRole('button',{name:'Delete permanently',exact:true})).toBeEnabled();
});

test('offline recovery uses the saved language and allows switching without a connection',async({page})=>{
  await page.addInitScript(()=>localStorage.setItem('teslatalk-language','nl'));
  await page.route('**/api/health',route=>route.abort('internetdisconnected'));
  await page.goto('/offline.html');
  await expect(page.getByRole('heading',{name:'Geen verbinding.'})).toBeVisible();
  await expect(page.getByRole('status')).toContainText('nog steeds niet bereikbaar');
  await expect(page.getByRole('combobox')).toBeHidden();
  await page.getByText('Instellingen',{exact:true}).click();
  await page.getByRole('combobox').selectOption('en');
  await expect(page.getByRole('heading',{name:'No connection.'})).toBeVisible();
  await expect(page.getByRole('status')).toContainText('still unreachable');
  await expect(page.locator('html')).toHaveAttribute('lang','en');
});

test('trip route and control labels update while chat drafts and explicit command confirmation stay intact',async({page,context})=>{
  await mockMapTiles(context);await dashboard(page);
  const car={user_id:'language-driver',vehicle_id:'language-car',display_name:'Karte',vehicle_name:'Verlauf',allowed:true,available:true,demo:false};
  const trip={id:'language-trip',title:'Karte',destination:'Verlauf',status:'active',my_role:'driver',leader_id:'language-driver',starts_at:Date.now()/1000-60,ends_at:Date.now()/1000+3600,finished_at:null,
    participants_detail:[],navigation:null,album:{status:'planned',name:'Karte'},
    vehicle_controls:{configured:true,vehicles:[car]},
    route_overview:{planner_user_id:null,vehicles:[{...car,battery_pct:31,range_km:120,accepted:true,can_plan:true,status:'waiting'}],recommendations:{lowest_battery_user_id:'language-driver',lowest_range_user_id:'language-driver'}}};
  await page.route('**/api/trips/language-trip',route=>route.fulfill({json:trip}));
  await page.route('**/api/trips/language-trip/messages',route=>route.fulfill({json:[]}));
  let commands=0;
  await page.route('**/api/trips/language-trip/controls',route=>{
    commands++;const data=route.request().postDataJSON();
    expect(data.action).toBe('climate_on');expect(data.vehicle_ids).toEqual(['language-car']);
    return route.fulfill({json:{status:'completed',vehicles:[{...car,status:'unknown',message:'Tesla/Proxy HTTP 500: Tesla hat den Befehl nicht bestätigt; Ergebnis bitte am Auto prüfen.'}]}});
  });
  const settings=await settingsTab(context);await settings.getByRole('combobox').selectOption('nl');
  await page.goto('/trip/language-trip');await expect(page.getByRole('combobox')).toHaveCount(0);
  await expect(page.getByRole('heading',{name:'Welke auto bepaalt de route?'})).toBeVisible();
  await expect(page.getByText('KLEINSTE BEREIK',{exact:true})).toBeVisible();
  await page.getByRole('button',{name:'Voertuigbediening',exact:true}).click();
  await page.getByRole('button',{name:'Klimaat aan',exact:true}).click();
  const dialog=page.getByRole('dialog');await expect(dialog.getByRole('combobox')).toHaveCount(0);
  await settings.getByRole('combobox').selectOption('en');
  await expect(dialog.getByRole('heading',{name:'Climate on for the group?'})).toBeVisible();expect(commands).toBe(0);
  await dialog.getByRole('button',{name:'Send to these vehicles now',exact:true}).click();
  await expect(page.getByRole('status',{name:'Vehicle control results'})).toContainText('Tesla did not confirm the command');
  await settings.getByRole('combobox').selectOption('nl');
  await expect(page.getByRole('status',{name:'Resultaten van voertuigbediening'})).toContainText('Tesla heeft het commando niet bevestigd');expect(commands).toBe(1);
  await page.getByRole('button',{name:'Chat',exact:true}).click();
  await page.getByLabel('Bericht',{exact:true}).fill('Karte und Verlauf');
  await settings.getByRole('combobox').selectOption('en');
  await expect(page.getByLabel('Message',{exact:true})).toHaveValue('Karte und Verlauf');
  await expect(page.getByRole('heading',{name:'Karte',exact:true})).toBeVisible();expect(commands).toBe(1);
});
