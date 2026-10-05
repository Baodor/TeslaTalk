import { test, expect } from '@playwright/test';
test('two microphones can publish concurrently in a real LiveKit room', async ({ page, browser }) => {
  test.skip(process.env.TT_VOICE_TEST!=='true','Needs the configured local LiveKit server.');
  for(const client of [page]) client.on('console',message=>{if(message.type()==='error'||message.type()==='warning')console.log('Audio browser: '+message.text());});
  const origin={origin:'http://localhost:8780'};
  await page.goto('/');
  await page.request.post('/api/demo/login',{headers:origin,data:{query:'Voice leader '+Date.now()}});
  const trip=await (await page.request.post('/api/trips',{headers:origin,data:{title:'Voice test',starts_at:new Date(Date.now()-60000).toISOString(),ends_at:new Date(Date.now()+600000).toISOString()}})).json();
  const secondContext=await browser.newContext();
  const second=await secondContext.newPage();
  await second.goto('/');
  await second.request.post('/api/demo/login',{headers:origin,data:{query:'Voice friend '+Date.now()}});
  await second.request.post('/api/trips/join',{headers:origin,data:{pin:trip.pin}});
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
  await page.getByRole('button',{name:'Mikrofon ausschalten',exact:true}).click();
  await second.getByRole('button',{name:'Mikrofon ausschalten',exact:true}).press('Space');
  for(const client of [page,second]) await expect(client.getByRole('button',{name:'Mikrofon einschalten',exact:true})).toHaveAttribute('aria-pressed','false');
  await page.request.post('/api/trips/'+trip.id+'/finish',{headers:origin});
  await expect(page.getByRole('button',{name:'Funk verbinden',exact:true})).toBeDisabled();
  await secondContext.close();
});
