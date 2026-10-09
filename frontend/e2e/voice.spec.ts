import { test, expect } from '@playwright/test';
import { mockMapTiles } from './map-tiles';
test.beforeEach(async({context})=>{await mockMapTiles(context);});
test('two microphones can publish concurrently in a real LiveKit room', async ({ page, browser }) => {
  test.skip(process.env.TT_VOICE_TEST!=='true','Needs the configured local LiveKit server.');
  const errors:string[]=[];
  page.on('pageerror',error=>errors.push(error.message));
  for(const client of [page]) client.on('console',message=>{if(message.type()==='error'||message.type()==='warning')console.log('Audio browser: '+message.text());});
  const origin={origin:'http://localhost:8780'};
  await page.goto('/');
  const leaderLogin=await page.request.post('/api/demo/login',{headers:origin,data:{query:'Voice leader '+Date.now()}});
  expect(leaderLogin.status()).toBe(200);
  const trip=await (await page.request.post('/api/trips',{headers:origin,data:{title:'Voice test',starts_at:new Date(Date.now()-60000).toISOString(),ends_at:new Date(Date.now()+600000).toISOString()}})).json();
  const secondContext=await browser.newContext({locale:'de-DE'});
  await mockMapTiles(secondContext);
  const second=await secondContext.newPage();
  await second.goto('/');
  const friendLogin=await second.request.post('/api/demo/login',{headers:origin,data:{query:'Voice friend '+Date.now()}});
  expect(friendLogin.status()).toBe(200);
  const joined=await second.request.post('/api/trips/join',{headers:origin,data:{pin:trip.pin}});
  expect(joined.status()).toBe(200);
  await Promise.all([page.goto('/trip/'+trip.id),second.goto('/trip/'+trip.id)]);
  for(const client of [page,second]) {
    const tokenResponse=client.waitForResponse(response=>response.url().endsWith('/voice-token'));
    await client.getByRole('button',{name:'Funk verbinden',exact:true}).click();
    const result=await tokenResponse;
    expect(result.status(),result.ok()?'Authorized voice token issued.':await result.text()).toBe(200);
    try { await expect(client.getByText('Verbunden · mehrere Sprecher möglich',{exact:true})).toBeVisible({timeout:20000}); }
    catch(error){console.log('Audio UI: '+await client.locator('.radio-panel').innerText());throw error;}
    await expect(client.locator('.radio-status')).toContainText('FUNK AN · MIKROFON AUS');
    await expect(client.getByRole('button',{name:'Funk trennen',exact:true})).toHaveAttribute('aria-pressed','true');
  }
  await page.getByRole('button',{name:'Mikrofon einschalten',exact:true}).click();
  await second.getByRole('button',{name:'Mikrofon einschalten',exact:true}).press('Space');
  // Mouse/touch release and key release leave both microphones enabled.
  for(const client of [page,second]) {
    await expect(client.getByRole('button',{name:'Mikrofon ausschalten',exact:true})).toHaveAttribute('aria-pressed','true');
    await expect(client.getByText('Mikrofon an · Du sendest',{exact:true})).toBeVisible();
    await expect(client.locator('.radio-status')).toContainText('DU SENDEST · MIKROFON AN');
    await expect(client.locator('.radio-panel')).toHaveClass(/radio-sending/);
  }
  await expect.poll(()=>page.locator('audio').count()).toBeGreaterThan(0);
  await expect.poll(()=>second.locator('audio').count()).toBeGreaterThan(0);
  const audioBefore=await page.locator('audio').count();
  let languageTokenRequests=0;
  const countToken=(request: import('@playwright/test').Request)=>{if(request.url().endsWith('/voice-token'))languageTokenRequests++;};
  page.on('request',countToken);
  const settings=await page.context().newPage();await settings.goto('/');
  await settings.getByRole('button',{name:'Mein Profil',exact:true}).click();
  await settings.getByRole('combobox',{name:'Anzeigesprache',exact:true}).selectOption('nl');
  await expect(page.locator('.radio-status')).toHaveText('JE ZENDT · MICROFOON AAN');
  await expect(page.getByRole('button',{name:'Microfoon uitschakelen',exact:true})).toHaveAttribute('aria-pressed','true');
  await expect(page.locator('audio')).toHaveCount(audioBefore);
  await settings.getByRole('combobox',{name:'Weergavetaal',exact:true}).selectOption('de-AT');
  await expect(page.locator('.radio-status')).toHaveText('DU SENDEST · MIKROFON EIN');
  await expect(page.getByRole('button',{name:'Mikrofon abdrahn',exact:true})).toHaveAttribute('aria-pressed','true');
  await expect(page.locator('audio')).toHaveCount(audioBefore);
  await settings.getByRole('combobox',{name:'Anzeigsprach',exact:true}).selectOption('de');
  await expect(page.locator('html')).toHaveAttribute('lang','de');await settings.close();
  expect(languageTokenRequests).toBe(0);page.off('request',countToken);
  await page.getByRole('button',{name:'Mikrofon ausschalten',exact:true}).click();
  await second.getByRole('button',{name:'Mikrofon ausschalten',exact:true}).press('Space');
  for(const client of [page,second]) await expect(client.getByRole('button',{name:'Mikrofon einschalten',exact:true})).toHaveAttribute('aria-pressed','false');
  await page.getByRole('button',{name:'Sprachaktivierung',exact:true}).click();
  await expect(page.getByRole('button',{name:'Sprachaktivierung aktiv',exact:true})).toBeDisabled();
  await page.getByRole('button',{name:'Funk trennen',exact:true}).click();
  await expect(page.locator('.radio-status')).toHaveText('FUNK AUS');
  await page.request.post('/api/trips/'+trip.id+'/finish',{headers:origin});
  await expect(page.getByRole('button',{name:'Funk verbinden',exact:true})).toBeDisabled();
  expect(errors).toEqual([]);
  await secondContext.close();
});
