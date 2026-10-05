import { test, expect, type Page } from '@playwright/test';

test('admin push test uses the server broadcast endpoint and reports queued devices', async ({page}) => {
  const requests:string[]=[];
  await page.route('**/api/config',route=>route.fulfill({json:{demo:true,admin_ready:true,push_ready:true}}));
  await page.route('**/api/admin',route=>route.fulfill({json:{users:3,trips:2,samples:9,push_ready:true,poll_interval:120,storage:'SQLite'}}));
  await page.route('**/api/admin/push/test',route=>{
    requests.push(route.request().method());
    return route.fulfill({json:{ok:true,queued_accounts:3,queued_devices:4}});
  });
  await page.goto('/admin');
  await page.getByRole('button',{name:'Testnachricht an alle Geräte',exact:true}).click();
  await expect(page.getByRole('status')).toContainText('4 Geräte in 3 Konten eingeplant');
  expect(requests).toEqual(['POST']);
});

async function login(page: Page, name: string) {
  await page.goto('/');
  await page.getByLabel('Dein Demo-Name').fill(name);
  await page.getByRole('button', { name: 'Demo öffnen', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Deine Fahrten.' })).toBeVisible();
}

test('microphone permission precedes the voice request and failures release the device', async ({page}) => {
  await page.addInitScript(()=>{
    const real=navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
    const state={deny:true,calls:0,tracks:[] as MediaStreamTrack[]};
    (window as any).radioPermissionTest=state;
    navigator.mediaDevices.getUserMedia=async constraints=>{
      state.calls++;
      if(state.deny) throw new DOMException('Test permission denied','NotAllowedError');
      const stream=await real(constraints); state.tracks.push(...stream.getAudioTracks()); return stream;
    };
  });
  let voiceRequests=0;
  await page.route('**/voice-token',async route=>{
    voiceRequests++;
    expect(await page.evaluate(()=>{const s=(window as any).radioPermissionTest;return {calls:s.calls,enabled:s.tracks[0]?.enabled};})).toEqual({calls:2,enabled:false});
    return route.fulfill({status:503,json:{detail:'Test voice server unavailable'}});
  });
  await login(page,'Microphone permission '+Date.now());
  const created=await (await page.request.post('/api/trips',{headers:{origin:'http://localhost:8780'},data:{title:'Permission test',starts_at:new Date(Date.now()-60000).toISOString(),ends_at:new Date(Date.now()+600000).toISOString()}})).json();
  await page.goto('/trip/'+created.id);
  const activate=page.getByRole('button',{name:'Mikrofon erlauben & Funk verbinden',exact:true});
  await activate.click();
  await expect(page.locator('.radio-panel .error')).toContainText('Mikrofonzugriff wurde nicht erlaubt');
  expect(voiceRequests).toBe(0);
  await page.evaluate(()=>{(window as any).radioPermissionTest.deny=false;});
  await activate.click();
  await expect(page.locator('.radio-panel .error')).toContainText('Test voice server unavailable');
  expect(voiceRequests).toBe(1);
  expect(await page.evaluate(()=>(window as any).radioPermissionTest.tracks.every((track:MediaStreamTrack)=>track.readyState==='ended'))).toBe(true);
  await expect(page.locator('.radio-status')).toHaveText('FUNK AUS');
  await expect(page.getByRole('button',{name:'Mikrofon einschalten',exact:true})).toBeDisabled();
});

test('Tesla avatars appear on person markers and fall back to initials without changing vehicle markers',async({page})=>{
  const picture='https://images.example.test/tesla-profile.png'; let fails=false;
  const image=await (await page.request.get('/apple-touch-icon.png')).body();
  await page.route(picture,route=>route.fulfill({status:fails?404:200,contentType:'image/png',body:fails?'':image,headers:{'cache-control':'no-store'}}));
  await page.route('**/api/me',async route=>{const response=await route.fetch();return route.fulfill({response,json:{...(await response.json()),avatar_url:picture}});});
  await page.route('**/api/trips/*',async route=>{
    const response=await route.fetch(),data=await response.json();
    if(data.participants_detail) data.participants_detail=data.participants_detail.map((p:any)=>({...p,avatar_url:picture}));
    return route.fulfill({response,json:data});
  });
  await login(page,'Avatar Driver '+Date.now());
  const headers={origin:'http://localhost:8780'};
  const created=await (await page.request.post('/api/trips',{headers,data:{title:'Avatar trip',starts_at:new Date(Date.now()-60000).toISOString(),ends_at:new Date(Date.now()+600000).toISOString()}})).json();
  const keyResponse=await page.request.post('/api/keys',{headers,data:{label:'Avatar telemetry test',days:1}});
  expect(keyResponse.ok()).toBe(true);
  const {token}=await keyResponse.json();
  const vehicleSample=await page.request.post(`/api/trips/${created.id}/samples`,{headers:{authorization:`Bearer ${token}`},data:{source:'telemetry',latitude:49.871,longitude:8.65}});
  expect(vehicleSample.ok()).toBe(true);
  const personSample=await page.request.post(`/api/trips/${created.id}/samples`,{headers,data:{source:'browser',latitude:49.872,longitude:8.651}});
  expect(personSample.ok()).toBe(true);
  await page.goto('/trip/'+created.id);
  await expect(page.locator('.person-marker img')).toHaveAttribute('src',picture);
  await expect.poll(()=>page.locator('.person-marker img').evaluate((image:HTMLImageElement)=>image.naturalWidth)).toBeGreaterThan(0);
  await expect(page.locator('.car-marker')).toHaveCount(1);
  await expect(page.locator('.car-marker img')).toHaveCount(0);
  fails=true; await page.reload();
  await expect(page.locator('.person-marker')).toHaveText('AD');
  await expect(page.locator('.person-marker img')).toHaveCount(0);
});

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
  await expect.poll(()=>page.evaluate(async()=>{
    const registration=await navigator.serviceWorker.ready;
    return registration.active?.state;
  })).toBe('activated');
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
  await page.route('**/api/push/test',route=>{testMessages.push(route.request().postDataJSON());return route.fulfill({json:{ok:true,accepted_by_provider:true,provider_accepted_at:1780000000,provider_elapsed_ms:250}});});
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
  await page.getByRole('button',{name:'Testnachricht an dieses Gerät',exact:true}).click();
  await expect(page.locator('.notification-status')).toContainText('Testnachricht an den Push-Dienst übergeben');
  await expect(page.locator('.notification-status')).toContainText('Angenommen um');
  await expect(page.locator('.notification-status')).toContainText('(0.25 s)');
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
