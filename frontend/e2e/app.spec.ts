import { test, expect, type Page } from '@playwright/test';

async function login(page: Page, name: string) {
  await page.goto('/');
  await page.getByLabel('Dein Demo-Name').fill(name);
  await page.getByRole('button', { name: 'Demo öffnen', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Deine Fahrten.' })).toBeVisible();
}

async function waitForMapTiles(page: Page) {
  if (process.env.TT_SCREENSHOTS !== 'true') return;
  await expect.poll(() => page.locator('.leaflet-container').evaluate(map => {
    const bounds = map.getBoundingClientRect();
    const visible = Array.from(map.querySelectorAll<HTMLImageElement>('.leaflet-tile')).filter(image => {
      const tile = image.getBoundingClientRect();
      return tile.right > bounds.left && tile.left < bounds.right && tile.bottom > bounds.top && tile.top < bounds.bottom;
    });
    return visible.length > 0 && visible.every(image => image.complete && image.naturalWidth === 256);
  }), { timeout: 45000 }).toBe(true);
}

test('two drivers chat live; named guest expires and public sharing stays private', async ({ page, browser, context }) => {
  if (process.env.TT_SCREENSHOTS === 'true') test.setTimeout(90000);
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
  const guestContext=await browser.newContext({geolocation:{latitude:49.88,longitude:8.66},permissions:['geolocation']});
  const guest=await guestContext.newPage();
  await guest.goto(detail.guest_url);
  await guest.getByLabel('Dein hinterlegter Name').fill('Anna');
  await guest.getByLabel('Dein persönlicher PIN').fill(guestPin!);
  await guest.getByRole('button', { name: 'Als Mitfahrer anmelden', exact: true }).click();
  await expect(guest.getByRole('heading', { name: 'Zusammen ans Meer', exact: true })).toBeVisible();
  await guest.getByRole('button', { name: 'Standort teilen', exact: true }).click();
  await expect(guest.locator('.person-marker')).toHaveCount(1);
  for(const client of [page,friend]) {
    const me=await (await client.request.get('/api/me')).json();
    await client.request.post(`/api/vehicles/${me.favorite_vehicle}/refresh`,{headers:csrf});
  }
  await page.request.post(`/api/trips/${tripId}/samples`,{headers:csrf,data:{source:'browser',latitude:49.8728,longitude:8.6512}});
  await friend.request.post(`/api/trips/${tripId}/samples`,{headers:csrf,data:{source:'browser',latitude:49.891,longitude:8.68}});
  await page.getByRole('button', { name: 'Karte', exact: true }).click();
  await expect(page.locator('.car-marker')).toHaveCount(2);
  await expect(page.locator('.person-marker')).toHaveCount(3);
  await page.locator('[title="Person: Anna"]').click();
  await expect(page.locator('.leaflet-popup')).toContainText('Person · Anna');
  await page.locator('.leaflet-popup-close-button').click();
  await guest.getByRole('button', { name: 'Standortfreigabe stoppen', exact: true }).click();
  await expect(page.locator('.person-marker')).toHaveCount(2);
  await page.waitForTimeout(1000);
  await waitForMapTiles(page);
  await page.screenshot({path:'../docs/assets/desktop.png',fullPage:true});
  await page.getByRole('button', { name: 'Fotos & Mitfahrer', exact: true }).click();
  await page.screenshot({path:'../docs/assets/passengers.png',fullPage:true});
  await page.setViewportSize({width:390,height:844});
  await page.getByRole('button', { name: 'Karte', exact: true }).click();
  await waitForMapTiles(page);
  await page.screenshot({path:'../docs/assets/mobile.png',fullPage:true});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
  expect(await page.evaluate(()=>{const gesture=new Event('gesturestart',{bubbles:true,cancelable:true});return document.body.dispatchEvent(gesture);})).toBe(false);
  expect(await page.locator('.leaflet-container').evaluate(map=>map.dispatchEvent(new Event('gesturestart',{bubbles:true,cancelable:true})))).toBe(true);
  await page.getByRole('button',{name:'Chat',exact:true}).click();
  expect(await page.getByLabel('Nachricht',{exact:true}).evaluate(input=>Number.parseFloat(getComputedStyle(input).fontSize))).toBeGreaterThanOrEqual(16);
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
  const appleIcon = page.locator('link[rel="apple-touch-icon"]');
  await expect(appleIcon).toHaveAttribute('sizes','180x180');
  await expect(appleIcon).toHaveAttribute('href','/apple-touch-icon-v4.png');
  const icon = await page.request.get('/apple-touch-icon.png');
  expect(icon.headers()['content-type']).toContain('image/png');
  const png = await icon.body();
  expect(png.readUInt32BE(16)).toBe(180);
  expect(png.readUInt32BE(20)).toBe(180);
  expect(png[25]).toBe(2); // Opaque RGB, rather than a transparent icon.
  const versioned=await (await page.request.get('/apple-touch-icon-v4.png')).body();
  expect(versioned.equals(png)).toBe(true);
  await page.reload();
  const cached=await page.evaluate(async()=>{
    const keys=await caches.keys();const result:string[]=[];
    for(const key of keys) result.push(...(await (await caches.open(key)).keys()).map(request=>new URL(request.url).pathname));
    return result;
  });
  expect(cached.every(path=>!path.startsWith('/api/')&&!path.startsWith('/auth/'))).toBeTruthy();
  let healthy=false;
  await page.route('**/api/health',route=>route.fulfill({status:healthy?200:503,json:{status:healthy?'ok':'unavailable'}}));
  await context.setOffline(true);
  const offline=await page.goto('/');
  expect(offline?.headers()['cache-control']).toBe('no-store');
  await expect(page.getByRole('heading',{name:'Die Verbindung fehlt.'})).toBeVisible();
  await expect(page.locator('body')).toHaveCSS('background-color','rgb(16, 26, 32)');
  expect(await page.locator('img').evaluate(image=>(image as HTMLImageElement).naturalWidth)).toBeGreaterThan(0);
  await context.setOffline(false);
  await expect(page.getByRole('status')).toContainText('HTTP 503');
  healthy=true;
  await page.getByRole('link',{name:'Erneut verbinden',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Bereit für die nächste Fahrt?'})).toBeVisible();
});

test('notification consent subscribes this device and can be revoked', async ({page,context}) => {
  await context.grantPermissions(['notifications']);
  const requests:any[]=[],testMessages:any[]=[];
  let syncFails=false;
  await page.route('**/api/config',route=>route.fulfill({json:{demo:true,tesla_ready:false,push_ready:true,vapid_public_key:'BAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA'}}));
  await page.route('**/api/push/subscribe',route=>{requests.push(route.request().postDataJSON());return route.fulfill({status:syncFails?503:200,json:syncFails?{detail:'Temporarily unavailable'}:{ok:true}});});
  await page.route('**/api/push/test',route=>{testMessages.push(route.request().postDataJSON());return route.fulfill({json:{ok:true,accepted_by_provider:true}});});
  await page.route('**/api/push/unsubscribe',route=>route.fulfill({json:{ok:true}}));
  await page.addInitScript(()=>{
    // Browser push delivery is mocked; keep consent deterministic across reloads,
    // and explicitly simulate an operating-system permission revocation below.
    Object.defineProperty(Notification,'permission',{get:()=>localStorage.getItem('test-notification-permission') || 'granted'});
    Notification.requestPermission=async()=>Notification.permission;
    let subscription:any=null;
    const data={endpoint:'https://fcm.googleapis.com/fcm/send/browser-test',keys:{p256dh:'browser-public-key',auth:'browser-auth-key'}};
    const restore=()=>({endpoint:data.endpoint,toJSON:()=>data,unsubscribe:async()=>{subscription=null;localStorage.removeItem('test-push-subscription');return true;}});
    if(localStorage.getItem('test-push-subscription')) subscription=restore();
    PushManager.prototype.getSubscription=async()=>subscription;
    PushManager.prototype.subscribe=async()=>{
      subscription=restore();localStorage.setItem('test-push-subscription','on');
      return subscription;
    };
  });
  await login(page,'Push user '+Date.now());
  await expect(page.getByRole('button',{name:'Benachrichtigungen',exact:true})).toHaveCount(0);
  await page.getByRole('button',{name:'Mein Profil',exact:true}).click();
  await page.getByRole('button',{name:'Benachrichtigungen',exact:true}).click();
  await expect(page.getByRole('button',{name:'Benachrichtigungen an',exact:true})).toHaveAttribute('aria-pressed','true');
  expect(requests).toHaveLength(1);
  expect(requests[0].endpoint).toBe('https://fcm.googleapis.com/fcm/send/browser-test');
  await page.getByRole('button',{name:'Testnachricht senden',exact:true}).click();
  await expect(page.locator('.notification-status')).toContainText('Testnachricht an den Push-Dienst übergeben');
  expect(testMessages).toEqual([{endpoint:requests[0].endpoint}]);
  syncFails=true;
  await page.reload();
  await page.getByRole('button',{name:'Mein Profil',exact:true}).click();
  await expect(page.getByRole('button',{name:'Benachrichtigungen an',exact:true})).toHaveAttribute('aria-pressed','true');
  await expect(page.locator('.notification-status')).toContainText('Serverabgleich steht aus');
  syncFails=false;
  await page.getByRole('button',{name:'Erneut abgleichen',exact:true}).click();
  await expect(page.locator('.notification-status')).toHaveText('Auf diesem Gerät aktiviert.');
  await page.evaluate(()=>localStorage.setItem('test-notification-permission','denied'));
  await page.reload();
  await page.getByRole('button',{name:'Mein Profil',exact:true}).click();
  await expect(page.getByRole('button',{name:'Benachrichtigungen erneut aktivieren',exact:true})).toHaveAttribute('aria-pressed','true');
  await expect(page.locator('.notification-status')).toContainText('Im Browser blockiert');
  await page.evaluate(()=>localStorage.setItem('test-notification-permission','granted'));
  await page.evaluate(()=>localStorage.removeItem('test-push-subscription'));
  await page.reload();
  await page.getByRole('button',{name:'Mein Profil',exact:true}).click();
  await page.getByRole('button',{name:'Benachrichtigungen erneut aktivieren',exact:true}).click();
  await expect(page.getByRole('button',{name:'Benachrichtigungen an',exact:true})).toHaveAttribute('aria-pressed','true');
  await page.getByRole('button',{name:'Benachrichtigungen an',exact:true}).click();
  await expect(page.getByRole('button',{name:'Benachrichtigungen',exact:true})).toHaveAttribute('aria-pressed','false');
  const count=requests.length;
  await page.reload();
  await page.getByRole('button',{name:'Mein Profil',exact:true}).click();
  await expect(page.getByRole('button',{name:'Benachrichtigungen',exact:true})).toHaveAttribute('aria-pressed','false');
  expect(requests).toHaveLength(count);
});


test('profile creates and revokes an API key without expiration', async ({page}) => {
  await login(page,'Unlimited key '+Date.now());
  await page.getByRole('button',{name:'Mein Profil',exact:true}).click();
  const keys=page.getByRole('region',{name:'Persönliche API-Schlüssel',exact:true});
  await keys.getByLabel('Bezeichnung',{exact:true}).fill('Home automation');
  await keys.getByLabel('Ohne Ablaufdatum',{exact:true}).check();
  await expect(keys.getByLabel('Gültigkeit in Tagen (1–365)',{exact:true})).toHaveCount(0);
  await keys.getByRole('button',{name:'Schlüssel erzeugen',exact:true}).click();
  await expect(keys.locator('.list-row')).toContainText('Ohne Ablaufdatum');
  const token=(await keys.locator('code').textContent())!;
  expect((await page.request.get('/api/me',{headers:{authorization:'Bearer '+token}})).status()).toBe(200);
  await keys.getByRole('button',{name:'Widerrufen',exact:true}).click();
  await expect(keys.locator('.list-row')).toHaveCount(0);
  expect((await page.request.get('/api/me',{headers:{authorization:'Bearer '+token}})).status()).toBe(401);
});
