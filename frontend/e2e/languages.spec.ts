import { test, expect, type Page } from '@playwright/test';

async function signedOut(page: Page) {
  await page.route('**/api/config',route=>route.fulfill({json:{demo:true,tesla_ready:true}}));
  await page.route('**/api/me',route=>route.fulfill({status:401,json:{detail:'Bitte anmelden.'}}));
}
async function dashboard(page: Page, push=false) {
  await page.route('**/api/config',route=>route.fulfill({json:{demo:false,tesla_ready:true,push_ready:push}}));
  await page.route('**/api/me',route=>route.fulfill({json:{id:'language-driver',username:'Karte',display_name:'Karte',provider:'tesla',plate:null,favorite_vehicle:null}}));
  for(const path of ['/api/trips','/api/invites','/api/vehicles','/api/keys']) await page.route('**'+path,route=>route.fulfill({json:[]}));
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
    await expect(page.getByRole('combobox')).toHaveValue('auto');
    await page.setViewportSize({width:390,height:844});
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  } finally {await context.close();}
});

test('respects language priority, persists manual choice and restores automatic detection',async({page})=>{
  await page.addInitScript(()=>Object.defineProperty(navigator,'languages',{configurable:true,get:()=>['fr-FR','nl-BE','de-DE']}));
  await signedOut(page);await page.goto('/');
  await expect(page.locator('html')).toHaveAttribute('lang','nl');
  const choice=page.getByRole('combobox');await choice.selectOption('en');
  await expect(page.getByRole('heading',{name:'Ready for the next trip?'})).toBeVisible();
  await page.reload();await expect(choice).toHaveValue('en');await expect(page.locator('html')).toHaveAttribute('lang','en');
  await choice.selectOption('auto');await expect(page.locator('html')).toHaveAttribute('lang','nl');
  await page.evaluate(()=>{Object.defineProperty(navigator,'languages',{get:()=>['de-AT']});dispatchEvent(new Event('languagechange'));});
  await expect(page.locator('html')).toHaveAttribute('lang','de');
  await choice.selectOption('en');
  await page.evaluate(()=>{Object.defineProperty(navigator,'languages',{get:()=>['nl-NL']});dispatchEvent(new Event('languagechange'));});
  await expect(page.locator('html')).toHaveAttribute('lang','en');
});

test('manual switching works without localStorage and invalid saved values use detection',async({page})=>{
  await page.addInitScript(()=>{
    localStorage.setItem('teslatalk-language','invalid');
    Storage.prototype.setItem=()=>{throw new DOMException('Storage disabled','SecurityError');};
  });
  await signedOut(page);await page.goto('/');
  await expect(page.locator('html')).toHaveAttribute('lang','de');
  await page.getByRole('combobox').selectOption('nl');
  await expect(page.getByRole('heading',{name:'Klaar voor de volgende rit?'})).toBeVisible();
});

test('switching preserves open forms and user text without submitting or reloading',async({page})=>{
  await dashboard(page);const writes:string[]=[];
  page.on('request',request=>{if(request.url().includes('/api/')&&request.method()!=='GET')writes.push(request.url());});
  await page.goto('/');await page.getByRole('button',{name:'Fahrt erstellen',exact:true}).click();
  const dialog=page.getByRole('dialog');
  await dialog.getByLabel('Name der Fahrt').fill('Karte');await dialog.getByLabel('Ziel',{exact:true}).fill('Verlauf');
  await dialog.getByRole('combobox').selectOption('nl');
  await expect(dialog.getByRole('heading',{name:'Nieuwe rit aanmaken'})).toBeVisible();
  await expect(dialog.getByLabel('Naam van de rit')).toHaveValue('Karte');
  await expect(dialog.getByLabel('Bestemming',{exact:true})).toHaveValue('Verlauf');
  await expect(page.locator('.user-block strong')).toHaveText('Karte');
  expect(writes).toEqual([]);
  await dialog.getByRole('button',{name:'Sluiten',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Je ritten.'})).toBeVisible();
});

test('server errors already on screen change language with the form',async({page})=>{
  await signedOut(page);
  await page.route('**/api/demo/login',route=>route.fulfill({status:429,json:{detail:'Zu viele Versuche. Bitte kurz warten.'}}));
  await page.goto('/');await page.getByRole('button',{name:'Demo öffnen',exact:true}).click();
  await expect(page.getByRole('alert')).toHaveText('Zu viele Versuche. Bitte kurz warten.');
  await page.getByRole('combobox').selectOption('nl');
  await expect(page.getByRole('alert')).toHaveText('Te veel pogingen. Wacht even.');
  await page.getByRole('combobox').selectOption('en');
  await expect(page.getByRole('alert')).toHaveText('Too many attempts. Please wait a moment.');
});

test('other tabs follow the saved preference',async({page,context})=>{
  await signedOut(page);await page.goto('/');
  const second=await context.newPage();await signedOut(second);await second.goto('/');
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
  await page.getByRole('combobox').selectOption('nl');
  await expect.poll(()=>subscriptions.at(-1)?.language).toBe('nl');
  expect(await page.evaluate(()=>(window as any).languagePushCalls)).toEqual({permissions:0,subscriptions:0});
  await page.getByRole('button',{name:'Mijn profiel',exact:true}).click();
  await expect(page.getByRole('region',{name:'Meldingen en webapp'})).toContainText('Ingeschakeld op dit apparaat.');
});

test('QR passenger registration and admin deletion are translated while retaining typed confirmation',async({page})=>{
  await page.route('**/api/config',route=>route.fulfill({json:{admin_ready:true}}));
  await page.route('**/api/guest/language-qr',route=>route.fulfill({json:{title:'Karte',active:true,starts_at:Date.now()/1000-60,ends_at:Date.now()/1000+3600}}));
  await page.goto('/guest/language-qr');await page.getByRole('combobox').selectOption('nl');
  await expect(page.getByRole('button',{name:'Registreren en meerijden',exact:true})).toBeVisible();
  await expect(page.getByLabel('Kies je eigen pincode (6 cijfers)')).toBeVisible();
  await expect(page.getByRole('heading',{name:'Karte',exact:true})).toBeVisible();
  await page.route('**/api/admin',route=>route.fulfill({json:{users:1,trips:0,samples:0,push_ready:false}}));
  await page.route('**/api/admin/users',route=>route.fulfill({json:[{id:'language-user',provider:'tesla',display_name:'Karte',username:'Karte',email:null,plate:null,avatar_url:null,last_login_at:null}]}));
  await page.goto('/admin');await page.getByRole('button',{name:'Karte verwijderen',exact:true}).click();
  const dialog=page.getByRole('dialog');await dialog.getByLabel('Gebruikersnaam ter bevestiging').fill('Karte');
  await dialog.getByRole('combobox').selectOption('en');
  await expect(dialog.getByLabel('Username to confirm')).toHaveValue('Karte');
  await expect(dialog.getByRole('button',{name:'Delete permanently',exact:true})).toBeEnabled();
});

test('offline recovery uses the saved language and allows switching without a connection',async({page})=>{
  await page.addInitScript(()=>localStorage.setItem('teslatalk-language','nl'));
  await page.route('**/api/health',route=>route.abort('internetdisconnected'));
  await page.goto('/offline.html');
  await expect(page.getByRole('heading',{name:'Geen verbinding.'})).toBeVisible();
  await expect(page.getByRole('status')).toContainText('nog steeds niet bereikbaar');
  await page.getByRole('combobox').selectOption('en');
  await expect(page.getByRole('heading',{name:'No connection.'})).toBeVisible();
  await expect(page.getByRole('status')).toContainText('still unreachable');
  await expect(page.locator('html')).toHaveAttribute('lang','en');
});
