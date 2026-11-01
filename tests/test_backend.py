import os
import json
import sqlite3
import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from server.main import create_app, DB

@pytest.fixture
def setup(tmp_path,monkeypatch):
    monkeypatch.setenv('APP_ACCESS_KEY','test-owner-key-with-32-characters')
    monkeypatch.setenv('SETTINGS_ENCRYPTION_KEY',Fernet.generate_key().decode())
    monkeypatch.setenv('GEMINI_API_KEY','env-secret')
    monkeypatch.delenv('RENDER',raising=False)
    db=DB(str(tmp_path/'test.db'))
    calls=[]
    def handler(request):
        calls.append(request)
        if 'generateContent' in str(request.url):
            if 'quota' in request.content.decode(): return httpx.Response(429,json={'error':{'message':'secret-do-not-echo'}})
            return httpx.Response(200,json={'candidates':[{'content':{'parts':[{'text':'There you are, MONTAi. ✨'}]}}]})
        if 'getWebhookInfo' in str(request.url):return httpx.Response(200,json={'ok':True,'result':{'url':''}})
        if 'getUpdates' in str(request.url):return httpx.Response(200,json={'ok':True,'result':[]})
        if 'getMe' in str(request.url):return httpx.Response(200,json={'ok':True,'result':{'id':1}})
        if 'models' in str(request.url):return httpx.Response(200,json={'models':[{'name':'models/test-model','supportedGenerationMethods':['generateContent']}]})
        return httpx.Response(404)
    client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    app=create_app(db,client)
    with TestClient(app) as c: yield c,db,calls
    db.conn.close()
H={'Authorization':'Bearer test-owner-key-with-32-characters'}
def test_health_auth(setup):
    c,db,calls=setup
    assert c.get('/health').status_code==200
    assert c.head('/').status_code==200
    assert c.get('/api/messages').status_code==401
    assert c.get('/api/status',headers={'Authorization':'Bearer nope'}).status_code==401
    assert 'env-secret' not in c.get('/api/status',headers=H).text

def test_chat_memory_retry_and_history(setup):
    c,db,calls=setup
    c.post('/api/memories',headers=H,json={'text':'I make anime edits.'})
    body={'text':'Hey Kana','request_id':'test-request-001'}
    a=c.post('/api/chat',headers=H,json=body)
    assert a.status_code==200
    assert c.post('/api/chat',headers=H,json=body).json()==a.json()
    assert len([r for r in calls if 'generateContent' in str(r.url)])==1
    payload=json.loads(calls[0].content)
    assert 'I make anime edits.' in payload['systemInstruction']['parts'][0]['text']
    rows=c.get('/api/messages',headers=H).json()['messages']
    assert [r['role'] for r in rows]==['user','assistant']
    assert len(c.get('/api/messages?before='+str(rows[1]['created']),headers=H).json()['messages'])==1
    c.delete('/api/messages',headers=H)
    assert c.get('/api/messages',headers=H).json()['messages']==[]
    assert len(c.get('/api/memories',headers=H).json()['memories'])==1

def test_settings_encrypt_and_validation(setup):
    c,db,calls=setup
    data={'model':'test-model','gemini_api_key':'private-new-key','telegram_enabled':False,'telegram_user_id':''}
    assert c.put('/api/settings',headers=H,json=data).status_code==200
    assert 'private-new-key' not in db.get('gemini_api_key')
    assert c.get('/api/models',headers=H).json()['models']==['test-model']
    assert c.put('/api/settings',headers=H,json={**data,'telegram_enabled':True}).status_code==422
    assert c.put('/api/settings',headers=H,json={**data,'model':'../escape'}).status_code==422
    assert c.put('/api/settings',headers=H,json={**data,'gemini_api_key':''}).status_code==200
    assert not c.get('/api/status',headers=H).json()['has_gemini_key']

def test_quota_does_not_write_or_leak(setup):
    c,db,calls=setup
    r=c.post('/api/chat',headers=H,json={'text':'quota','request_id':'quota-request-001'})
    assert r.status_code==502
    assert 'secret-do-not-echo' not in r.text
    assert c.get('/api/messages',headers=H).json()['messages']==[]
    assert c.post('/api/chat',headers=H,json={'text':'   ','request_id':'blank-request-001'}).status_code==422

def test_disk_persistence(setup):
    c,db,calls=setup
    c.post('/api/chat',headers=H,json={'text':'hello','request_id':'persist-request-001'})
    path=db.run('PRAGMA database_list').fetchone()[2]
    second=DB(path)
    assert second.run('SELECT COUNT(*) FROM messages').fetchone()[0]==2
    second.conn.close()

def test_memory_delete_and_pagination(setup):
    c,db,calls=setup
    m=c.post('/api/memories',headers=H,json={'text':'a memory'}).json()['id']
    assert c.delete('/api/memories/'+m,headers=H).status_code==200
    assert c.get('/api/memories',headers=H).json()['memories']==[]
    for i in range(105):db.run('INSERT INTO messages VALUES(?,?,?,?,?,?)',(str(i),'user','hello','app',float(i),'p'+str(i)))
    page=c.get('/api/messages',headers=H).json()
    assert page['has_more'] and len(page['messages'])==100
    assert len(c.get('/api/messages?before='+str(page['messages'][0]['created']),headers=H).json()['messages'])==5

def test_telegram_owner_filter(tmp_path,monkeypatch):
    import time
    monkeypatch.setenv('APP_ACCESS_KEY','test-owner-key-with-32-characters')
    monkeypatch.setenv('SETTINGS_ENCRYPTION_KEY',Fernet.generate_key().decode())
    monkeypatch.setenv('GEMINI_API_KEY','test')
    monkeypatch.setenv('TELEGRAM_BOT_TOKEN','test-token')
    monkeypatch.delenv('RENDER',raising=False)
    db=DB(str(tmp_path/'telegram.db'))
    db.put('telegram_enabled','true');db.put('telegram_user_id','123')
    sent=[];delivered=False
    def handler(request):
        nonlocal delivered
        url=str(request.url)
        if 'getUpdates' in url:
            if delivered:return httpx.Response(200,json={'ok':True,'result':[]})
            delivered=True
            return httpx.Response(200,json={'ok':True,'result':[
                {'update_id':1,'message':{'text':'intruder','from':{'id':666},'chat':{'id':666,'type':'private'}}},
                {'update_id':2,'message':{'text':'group','from':{'id':123},'chat':{'id':-1,'type':'group'}}},
                {'update_id':3,'message':{'text':'hey','from':{'id':123},'chat':{'id':123,'type':'private'}}}
            ]})
        if 'sendMessage' in url:sent.append(json.loads(request.content));return httpx.Response(200,json={'ok':True,'result':{}})
        return httpx.Response(200,json={'candidates':[{'content':{'parts':[{'text':'Hey, MONTAi.'}]}}]})
    client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    with TestClient(create_app(db,client)) as c:
        for _ in range(100):
            if sent:break
            time.sleep(.01)
        assert len(sent)==1 and sent[0]['chat_id']==123
        assert [m['source'] for m in c.get('/api/messages',headers=H).json()['messages']]==['telegram','telegram']
        offsets=db.run("SELECT value FROM settings WHERE key LIKE 'offset_%'").fetchall()
        assert offsets[0][0]=='4'
    db.conn.close()
