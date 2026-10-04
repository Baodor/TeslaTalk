import { test, expect } from '@playwright/test';
test('two microphones can publish concurrently in a real LiveKit room', async ({ page, browser }) => {
  test.skip(process.env.TT_VOICE_TEST!=='true','Needs the configured local LiveKit server.');
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
    await client.getByRole('button',{name:'Funk verbinden',exact:true}).click();
    await expect(client.getByText('Verbunden · mehrere Sprecher möglich',{exact:true})).toBeVisible({timeout:20000});
  }
  await page.getByRole('button',{name:'Zum Sprechen gedrückt halten',exact:true}).dispatchEvent('keydown',{key:' '});
  await second.getByRole('button',{name:'Zum Sprechen gedrückt halten',exact:true}).dispatchEvent('keydown',{key:' '});
  await expect(page.getByText('Du sendest …',{exact:true})).toBeVisible();
  await expect(second.getByText('Du sendest …',{exact:true})).toBeVisible();
  await expect.poll(()=>page.locator('audio').count()).toBeGreaterThan(0);
  await expect.poll(()=>second.locator('audio').count()).toBeGreaterThan(0);
  await page.getByRole('button',{name:'Du sendest …',exact:true}).dispatchEvent('keyup',{key:' '});
  await second.getByRole('button',{name:'Du sendest …',exact:true}).dispatchEvent('keyup',{key:' '});
  await page.request.post('/api/trips/'+trip.id+'/finish',{headers:origin});
  await expect(page.getByRole('button',{name:'Funk verbinden',exact:true})).toBeDisabled();
  await secondContext.close();
});
