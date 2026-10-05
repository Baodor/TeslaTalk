import { test, expect } from '@playwright/test';

const catalog = {
  title:'TeslaTalk API',version:'0.1.0',base_url:'https://teslatalk.example',
  rules:['Persönlicher Bearer und Browsersitzung sind unterschiedliche Zugänge.'],
  examples:{navigation_cancelled:{active:false,captured_at:'<CURRENT_UNIX_SECONDS>'}},
  openapi:{components:{schemas:{Navigation:{type:'object',properties:{route_points:{type:'array'}}}}}},
  endpoints:[
    {method:'GET',path:'/api/me',group:'Profil',description:'Eigenes Profil lesen.',access:'Browser oder Bearer',returns:'Eigenes Profil',parameters:[],request_body:null,responses:{200:{description:'Profil'}},operation_id:'me'},
    {method:'PUT',path:'/api/vehicles/{vehicle_id}/navigation',group:'Navigation',description:'Fahrzeugnavigation importieren.',access:'Fahrer-Bearer',returns:'Navigation aus Fleet Telemetry RouteLine',parameters:[],request_body:{required:true},responses:{200:{description:'Navigation'}},operation_id:'navigation'},
    {method:'WEBSOCKET',path:'/api/ws/trips/{trip_id}',group:'WebSocket',description:'Live-Fahrtupdates empfangen.',access:'Fahrtmitglied',returns:'participants, message, navigation, heartbeat, ended',parameters:[],request_body:null,responses:{},operation_id:null},
  ],
};

test('API page copies all endpoints and schemas even when filtered', async ({page}) => {
  await page.route('**/api/config',route=>route.fulfill({json:{demo:true}}));
  await page.route('**/api/docs',route=>route.fulfill({json:catalog}));
  await page.addInitScript(() => {
    Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:async(text:string)=>{(window as any).llmCopiedText=text;}}});
  });
  await page.goto('/api-docs');
  await expect(page.getByRole('heading',{name:'API-Dokumentation.'})).toBeVisible();
  await expect(page.locator('.api-endpoint')).toHaveCount(3);
  await page.getByLabel('Endpunkte suchen').fill('navigation');
  await page.getByLabel('Bereich',{exact:true}).selectOption('Navigation');
  await expect(page.locator('.api-endpoint')).toHaveCount(1);
  await page.getByRole('button',{name:'Alle Informationen für ein LLM kopieren',exact:true}).click();
  await expect(page.getByRole('button',{name:'Alle Informationen kopiert',exact:true})).toBeVisible();
  const copied=await page.evaluate(()=>(window as any).llmCopiedText as string);
  const data=JSON.parse(copied.slice(copied.indexOf('{')));
  expect(data).toEqual(catalog);
  expect(copied).toContain('/api/me');
  expect(copied).toContain('WEBSOCKET');
  expect(copied).toContain('route_points');
  await page.setViewportSize({width:390,height:844});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
  const download=page.waitForEvent('download');
  await page.getByRole('button',{name:'Text herunterladen',exact:true}).click();
  expect((await download).suggestedFilename()).toBe('teslatalk-api-llm.txt');
});

test('API page offers complete manual context when clipboard access is denied', async ({page}) => {
  await page.route('**/api/config',route=>route.fulfill({json:{demo:true}}));
  await page.route('**/api/docs',route=>route.fulfill({json:catalog}));
  await page.addInitScript(() => {
    Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:async()=>{throw new Error('Denied');}}});
  });
  await page.goto('/api-docs');
  await page.getByRole('button',{name:'Alle Informationen für ein LLM kopieren',exact:true}).click();
  const text=page.getByLabel('Vollständiger LLM-Kontext');
  await expect(text).toBeVisible();
  await expect(text).toHaveValue(/\/api\/ws\/trips/);
  await text.focus();
  expect(await text.evaluate((element:HTMLTextAreaElement)=>element.selectionEnd-element.selectionStart)).toBe((await text.inputValue()).length);
});
