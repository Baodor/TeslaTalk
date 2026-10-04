import { test, expect, type Page } from '@playwright/test';

async function login(page: Page, name: string) {
  await page.goto('/');
  await page.getByLabel('Dein Demo-Name').fill(name);
  await page.getByRole('button', { name: 'Demo öffnen', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Deine Fahrten.' })).toBeVisible();
}

test('two drivers chat live; named guest expires and public sharing stays private', async ({ page, browser }) => {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  await login(page, 'Fahrtleiter '+Date.now());
  const csrf={origin:'http://localhost:8780'};
  expect((await page.request.patch('/api/me',{headers:csrf,data:{display_name:'Luca',username:'luca-'+Date.now()}})).status()).toBe(200);
  await page.reload();
  await page.getByRole('button', { name: 'Fahrt erstellen', exact: true }).click();
  const dialog=page.getByRole('dialog');
  await dialog.getByLabel('Name der Fahrt').fill('Zusammen ans Meer');
  await dialog.getByLabel('Ziel', { exact: true }).fill('Hamburg · Wochenende mit Freunden');
  await dialog.getByRole('button', { name: 'Fahrt erstellen', exact: true }).click();
  const pin=await dialog.locator('code').textContent();
  await dialog.getByRole('button', { name: 'Fahrt öffnen', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Zusammen ans Meer', exact: true })).toBeVisible();
  const tripId=page.url().split('/').pop()!;
  const friendContext=await browser.newContext();
  const friend=await friendContext.newPage();
  await login(friend, 'Freund '+Date.now());
  expect((await friend.request.patch('/api/me',{headers:csrf,data:{display_name:'Jonas',username:'jonas-'+Date.now()}})).status()).toBe(200);
  await friend.reload();
  await friend.getByRole('button', { name: 'Mit PIN beitreten', exact: true }).click();
  await friend.getByRole('dialog').getByLabel('Fahrer-PIN').fill(pin!);
  await friend.getByRole('dialog').getByRole('button', { name: 'Fahrt beitreten', exact: true }).click();
  await friend.getByRole('button', { name: 'Chat', exact: true }).click();
  await page.getByRole('button', { name: 'Chat', exact: true }).click();
  await page.getByLabel('Nachricht', { exact: true }).fill('Alle bereit? Los geht’s ans Meer.');
  await page.getByRole('button', { name: 'Nachricht senden' }).click();
  await expect(friend.getByText('Alle bereit? Los geht’s ans Meer.', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Fotos & Mitfahrer', exact: true }).click();
  await page.getByLabel('Name des Mitfahrers').fill('Anna');
  await page.getByRole('button', { name: 'Mitfahrer hinzufügen', exact: true }).click();
  await expect(page.getByText('Anna: persönlicher PIN', { exact: true })).toBeVisible();
  const detail=await (await page.request.get(`/api/trips/${tripId}`)).json();
  const guestPin=await page.locator('.notice .copy-value code').textContent();
  const guestContext=await browser.newContext();
  const guest=await guestContext.newPage();
  await guest.goto(detail.guest_url);
  await guest.getByLabel('Dein hinterlegter Name').fill('Anna');
  await guest.getByLabel('Dein persönlicher PIN').fill(guestPin!);
  await guest.getByRole('button', { name: 'Als Mitfahrer anmelden', exact: true }).click();
  await expect(guest.getByRole('heading', { name: 'Zusammen ans Meer', exact: true })).toBeVisible();
  for(const client of [page,friend]) {
    const me=await (await client.request.get('/api/me')).json();
    await client.request.post(`/api/vehicles/${me.favorite_vehicle}/refresh`,{headers:csrf});
  }
  await page.request.post(`/api/trips/${tripId}/samples`,{headers:csrf,data:{source:'browser',latitude:49.8728,longitude:8.6512}});
  await friend.request.post(`/api/trips/${tripId}/samples`,{headers:csrf,data:{source:'browser',latitude:49.891,longitude:8.68}});
  await page.getByRole('button', { name: 'Karte', exact: true }).click();
  await expect(page.locator('.car-marker')).toHaveCount(2);
  await page.waitForTimeout(1000);
  if(process.env.TT_SCREENSHOTS==='true') await expect.poll(()=>page.locator('.leaflet-tile').first().evaluate(image=>(image as HTMLImageElement).naturalWidth),{timeout:15000}).toBe(256);
  await page.screenshot({path:'../docs/assets/desktop.png',fullPage:true});
  await page.getByRole('button', { name: 'Fotos & Mitfahrer', exact: true }).click();
  await page.screenshot({path:'../docs/assets/passengers.png',fullPage:true});
  await page.setViewportSize({width:390,height:844});
  await page.getByRole('button', { name: 'Karte', exact: true }).click();
  await page.screenshot({path:'../docs/assets/mobile.png',fullPage:true});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
  await page.request.post(`/api/trips/${tripId}/finish`,{headers:csrf});
  await expect.poll(async()=>(await guest.request.get(`/api/trips/${tripId}`)).status()).toBe(403);
  const share=await (await page.request.post(`/api/trips/${tripId}/share`,{headers:csrf})).json();
  const publicData=await (await guest.request.get('/api/public/'+share.url.split('/').pop())).json();
  expect(publicData.read_only).toBe(true);
  expect(JSON.stringify(publicData)).not.toContain('Alle bereit?');
  expect(publicData.participants).toBeUndefined();
  expect(errors).toEqual([]);
  await friendContext.close(); await guestContext.close();
});

test('PWA activates its service worker and keeps private trip data out of the offline cache', async ({ page, context }) => {
  await page.goto('/');
  const worker=await page.evaluate(async()=>{const registration=await navigator.serviceWorker.ready;return registration.active?.state;});
  expect(worker).toBe('activated');
  const manifest=await (await page.request.get('/manifest.webmanifest')).json();
  expect(manifest.display).toBe('standalone');
  expect(manifest.icons.some((icon:any)=>icon.purpose==='maskable')).toBeTruthy();
  await page.reload();
  const cached=await page.evaluate(async()=>{
    const keys=await caches.keys();const result:string[]=[];
    for(const key of keys) result.push(...(await (await caches.open(key)).keys()).map(request=>new URL(request.url).pathname));
    return result;
  });
  expect(cached.every(path=>!path.startsWith('/api/')&&!path.startsWith('/auth/'))).toBeTruthy();
  await context.setOffline(true);
  await page.goto('/');
  await expect(page.getByRole('heading',{name:'Die Verbindung fehlt.'})).toBeVisible();
  await context.setOffline(false);
});

test('notification consent subscribes this device and can be revoked', async ({page,context}) => {
  await context.grantPermissions(['notifications']);
  const requests:any[]=[];
  await page.route('**/api/config',route=>route.fulfill({json:{demo:true,tesla_ready:false,push_ready:true,vapid_public_key:'BAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA'}}));
  await page.route('**/api/push/subscribe',route=>{requests.push(route.request().postDataJSON());return route.fulfill({json:{ok:true}});});
  await page.route('**/api/push/unsubscribe',route=>route.fulfill({json:{ok:true}}));
  await page.addInitScript(()=>{
    let subscription:any=null;
    const data={endpoint:'https://fcm.googleapis.com/fcm/send/browser-test',keys:{p256dh:'browser-public-key',auth:'browser-auth-key'}};
    PushManager.prototype.getSubscription=async()=>subscription;
    PushManager.prototype.subscribe=async()=>{
      subscription={endpoint:data.endpoint,toJSON:()=>data,unsubscribe:async()=>{subscription=null;return true;}};
      return subscription;
    };
  });
  await login(page,'Push user '+Date.now());
  await page.getByRole('button',{name:'Benachrichtigungen',exact:true}).click();
  await expect(page.getByRole('button',{name:'Benachrichtigungen an',exact:true})).toHaveAttribute('aria-pressed','true');
  expect(requests).toHaveLength(1);
  expect(requests[0].endpoint).toBe('https://fcm.googleapis.com/fcm/send/browser-test');
  await page.getByRole('button',{name:'Benachrichtigungen an',exact:true}).click();
  await expect(page.getByRole('button',{name:'Benachrichtigungen',exact:true})).toHaveAttribute('aria-pressed','false');
});
