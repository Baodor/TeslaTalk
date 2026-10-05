import asyncio
import sqlite3
import time
import pytest
from app import db, main
from app.config import settings


def test_maintenance_recovers_and_removes_expired_sessions(tmp_path,monkeypatch,caplog):
    monkeypatch.setattr(settings,'db_path',str(tmp_path/'maintenance.sqlite'))
    db.initialize()
    db.execute('INSERT INTO sessions VALUES (?,?,?,?)',('expired',None,'user',time.time()-1))
    original=db.execute
    calls=[]
    def temporary_failure(sql,args=()):
        calls.append(sql)
        if len(calls)==1:
            raise sqlite3.OperationalError('private database details')
        return original(sql,args)
    async def tick(seconds):
        if len(calls)>=4:
            raise asyncio.CancelledError
    monkeypatch.setattr(db,'execute',temporary_failure)
    monkeypatch.setattr(main.asyncio,'sleep',tick)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(main.background())
    assert db.one('SELECT * FROM sessions WHERE token_hash=?',('expired',)) is None
    assert 'OperationalError' in caplog.text
    assert 'private database details' not in caplog.text
