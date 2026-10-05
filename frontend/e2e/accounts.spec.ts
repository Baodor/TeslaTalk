import { test, expect } from '@playwright/test';

test('Tesla first sign-in requires a unique username and preserves account data', async ({page}) => {
  let user={id:'test-tesla-first-login',provider:'tesla',username:'fahrer-generated',display_name:'Tesla Driver',plate:'HHTT123',favorite_vehicle:null,needs_username:true};
  const submissions:any[]=[];
  await page.route('**/api/config',route=>route.fulfill({json:{demo:false,tesla_ready:true}}));
  await page.route('**/api/me',route=>{
    if (route.request().method()==='PATCH') {
      const body=route.request().postDataJSON();submissions.push(body);
      if (body.username==='taken') return route.fulfill({status:409,json:{detail:'Dieser Benutzername ist bereits vergeben. Bitte einen anderen wählen.'}});
      user={...user,...body,needs_username:false};
    }
    return route.fulfill({json:user});
  });
  for (const path of ['/api/trips','/api/invites','/api/vehicles']) await page.route('**'+path,route=>route.fulfill({json:[]}));
  await page.goto('/');
  await expect(page.getByRole('heading',{name:'Wähle deinen Benutzernamen.'})).toBeVisible();
  await expect(page.getByRole('heading',{name:'Deine Fahrten.'})).toHaveCount(0);
  await page.getByLabel('Benutzername',{exact:true}).fill('taken');
  await page.getByRole('button',{name:'Benutzername speichern & weiter',exact:true}).click();
  await expect(page.getByRole('alert')).toContainText('bereits vergeben');
  await page.getByLabel('Benutzername',{exact:true}).fill('Roadtrip_Max-1');
  await page.getByRole('button',{name:'Benutzername speichern & weiter',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Deine Fahrten.'})).toBeVisible();
  expect(submissions[1]).toEqual({username:'Roadtrip_Max-1',display_name:'Tesla Driver',plate:'HHTT123'});
  await page.reload();
  await expect(page.getByRole('heading',{name:'Deine Fahrten.'})).toBeVisible();
  await expect(page.getByRole('heading',{name:'Wähle deinen Benutzernamen.'})).toHaveCount(0);
});

test('admin lists Tesla mail, username, plate, last login and account picture', async ({page}) => {
  const picture='https://images.example.test/admin-tesla-picture.png';
  const image=await (await page.request.get('/apple-touch-icon.png')).body();
  await page.route(picture,route=>route.fulfill({contentType:'image/png',body:image}));
  await page.route('**/api/config',route=>route.fulfill({json:{admin_ready:true}}));
  await page.route('**/api/admin',route=>route.fulfill({json:{users:2,trips:0,samples:0,push_ready:false,poll_interval:120,storage:'SQLite'}}));
  await page.route('**/api/admin/users',route=>route.fulfill({json:[
    {id:'tesla-driver',provider:'tesla',display_name:'Roadtrip Max',username:'MaxDriver',email:'tesla@example.test',plate:'HHTT123',avatar_url:picture,created_at:1791179000,last_login_at:1791180000},
    {id:'old-account',provider:'guest',display_name:'Anna',username:'gast-test',email:null,plate:null,avatar_url:null,created_at:1791179000,last_login_at:null},
  ]}));
  await page.goto('/admin');
  const users=page.getByRole('region',{name:'Alle Benutzer',exact:true});
  const max=users.getByRole('row').filter({hasText:'Roadtrip Max'});
  await expect(max).toContainText('tesla@example.test');
  await expect(max).toContainText('MaxDriver');
  await expect(max).toContainText('HHTT123');
  await expect(max.locator('td').last()).not.toHaveText('Noch nicht erfasst');
  await expect(max.locator('img')).toHaveAttribute('src',picture);
  await expect.poll(()=>max.locator('img').evaluate((image:HTMLImageElement)=>image.naturalWidth)).toBeGreaterThan(0);
  await expect(users.getByRole('row').filter({hasText:'Anna'})).toContainText('Noch nicht erfasst');
  await page.setViewportSize({width:390,height:844});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
});
