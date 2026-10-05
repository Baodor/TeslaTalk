import pytest
from app import db,fleet
from .conftest import new_driver
from .test_access import trip,passenger


@pytest.mark.parametrize('url',['http://images.example/avatar.png','data:image/png;base64,AAA','https://user:secret@images.example/avatar.png','https://images.example:bad/avatar.png'])
def test_avatar_only_accepts_https_image_urls_without_credentials(url):
    assert fleet.profile_avatar({'profile_image_url':url}) is None


def test_avatar_migration_preserves_existing_accounts(owner):
    uid=owner.get('/api/me').json()['id']
    db.execute('ALTER TABLE users DROP COLUMN avatar_url')
    db.initialize(); db.initialize()
    profile=owner.get('/api/me').json()
    assert profile['id']==uid and profile['display_name']=='Fahrtleiter' and profile['avatar_url'] is None


def test_tesla_avatar_refresh_updates_only_own_image_and_keeps_public_share_private(owner,monkeypatch):
    uid=owner.get('/api/me').json()['id']; image='https://images.example/driver.png'
    db.execute("UPDATE users SET provider='tesla' WHERE id=?",(uid,))
    async def account(user_id,path,params=None):
        assert user_id==uid and path=='/api/1/users/me'
        return {'full_name':'Tesla account name','email':'private@example.test','profile_image_url':image}
    monkeypatch.setattr(fleet,'request',account)
    result=owner.post('/api/me/tesla-profile',json={'user_id':'someone-else'})
    assert result.status_code==200 and result.json()['avatar_url']==image
    assert result.json()['display_name']=='Fahrtleiter' and 'private@example.test' not in result.text
    created=trip(owner)
    assert owner.get('/api/trips/'+created['id']).json()['participants_detail'][0]['avatar_url']==image
    stranger=new_driver('Other account')
    assert stranger.post('/api/me/tesla-profile').status_code==409
    guest,_,_=passenger(owner,created)
    assert guest.post('/api/me/tesla-profile').status_code==403
    owner.post('/api/trips/'+created['id']+'/finish')
    share=owner.post('/api/trips/'+created['id']+'/share').json()['url']
    assert image not in owner.get('/api/public/'+share.split('/')[-1]).text
