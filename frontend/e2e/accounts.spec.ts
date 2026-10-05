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
  await expect(max.locator('td').nth(4)).not.toHaveText('Noch nicht erfasst');
  await expect(max.locator('img')).toHaveAttribute('src',picture);
  await expect.poll(()=>max.locator('img').evaluate((image:HTMLImageElement)=>image.naturalWidth)).toBeGreaterThan(0);
  await expect(users.getByRole('row').filter({hasText:'Anna'})).toContainText('Noch nicht erfasst');
  await page.setViewportSize({width:390,height:844});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
});

test('deleting a user requires exact typed confirmation and a deliberate final action',async({page})=>{
  let deleted=false;const requests:any[]=[];
  await page.route('**/api/config',route=>route.fulfill({json:{admin_ready:true}}));
  await page.route('**/api/admin',route=>route.fulfill({json:{users:1,trips:1,samples:0,push_ready:false,poll_interval:120,storage:'SQLite'}}));
  await page.route('**/api/admin/users',route=>route.fulfill({json:deleted?[]:[{id:'delete-user',provider:'tesla',display_name:'Max',username:'MaxDriver',email:'tesla@example.test',plate:'HHTT123',avatar_url:null,created_at:1791179000,last_login_at:null}]}));
  await page.route('**/api/admin/users/delete-user',route=>{requests.push({method:route.request().method(),body:route.request().postDataJSON()});deleted=true;return route.fulfill({json:{ok:true,deleted_user_id:'delete-user',deleted_trips:1,deleted_qr_accounts:1}});});
  await page.goto('/admin');await page.getByRole('button',{name:'Max löschen',exact:true}).click();
  const modal=page.getByRole('dialog',{name:'Benutzer dauerhaft löschen'});
  await expect(modal).toContainText('geleiteten Fahrten');
  const final=modal.getByRole('button',{name:'Dauerhaft löschen',exact:true});await expect(final).toBeDisabled();
  await modal.getByLabel('Benutzername zur Bestätigung').fill('maxdriver');await expect(final).toBeDisabled();
  await modal.getByRole('button',{name:'Abbrechen',exact:true}).click();expect(requests).toEqual([]);
  await page.getByRole('button',{name:'Max löschen',exact:true}).click();
  await modal.getByLabel('Benutzername zur Bestätigung').fill('MaxDriver');await final.click();
  await expect(page.getByRole('region',{name:'Alle Benutzer'})).toContainText('Max wurde gelöscht.');
  await expect(page.getByRole('button',{name:'Max löschen',exact:true})).toHaveCount(0);
  expect(requests).toEqual([{method:'DELETE',body:{username:'MaxDriver'}}]);
});

test('a passenger can link and unlink a Tesla picture while staying a passenger without cars',async({page})=>{
  let linked=false;const calls:string[]=[];
  const trip={id:'passenger-profile-trip',title:'Passenger trip',status:'active',leader_id:'other',starts_at:Date.now()/1000-60,ends_at:Date.now()/1000+3600,finished_at:null,participants:2,destination:''};
  await page.route('**/api/config',route=>route.fulfill({json:{tesla_ready:true,demo:false}}));
  await page.route('**/api/me',route=>route.fulfill({json:{id:'guest-profile',username:'gast-profile',display_name:'Anna',provider:'guest',plate:null,favorite_vehicle:null,tesla_profile_linked:linked,avatar_url:linked?'/apple-touch-icon.png':null}}));
  await page.route('**/api/trips',route=>route.fulfill({json:[trip]}));await page.route('**/api/invites',route=>route.fulfill({json:[]}));
  await page.route('**/api/vehicles**',route=>{calls.push(route.request().url());return route.fulfill({json:[]});});
  await page.route('**/api/me/tesla-profile-link',route=>{calls.push(route.request().method());linked=false;return route.fulfill({json:{ok:true}});});
  await page.goto('/');await page.getByRole('button',{name:'Mein Profil',exact:true}).click();
  const profile=page.getByRole('region',{name:'Tesla-Profil für Mitfahrer'});
  await expect(profile.getByRole('link',{name:'Mit Tesla verknüpfen'})).toHaveAttribute('href','/auth/tesla/passenger?trip_id=passenger-profile-trip');
  await expect(page.getByRole('button',{name:'Fahrzeuge abrufen',exact:true})).toHaveCount(0);
  await expect(page.getByRole('region',{name:'Persönliche API-Schlüssel'})).toHaveCount(0);
  linked=true;await page.reload();await page.getByRole('button',{name:'Mein Profil',exact:true}).click();
  await expect(profile).toContainText('Tesla-Profil verknüpft · Mitfahrer');await expect(profile.locator('img')).toHaveAttribute('src','/apple-touch-icon.png');
  await profile.getByRole('button',{name:'Tesla-Verknüpfung entfernen',exact:true}).click();
  await expect(profile.getByRole('link',{name:'Mit Tesla verknüpfen'})).toBeVisible();expect(calls).toEqual(['DELETE']);
});
