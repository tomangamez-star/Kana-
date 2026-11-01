import json
import os
import asyncio
import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException
from fastapi.testclient import TestClient
from server.main import DB,create_app
from server.ai import Router,detect,custom_url
H={'Authorization':'Bearer test-owner-key-with-32-characters'}
MKEY='MistralFakeKeyForTestingOnly123456'

@pytest.fixture
def factory(tmp_path,monkeypatch):
    monkeypatch.setenv('APP_ACCESS_KEY','test-owner-key-with-32-characters')
    monkeypatch.setenv('SETTINGS_ENCRYPTION_KEY',Fernet.generate_key().decode())
    for name in ['GEMINI_API_KEY','MISTRAL_API_KEY','GROQ_API_KEY','OPENROUTER_API_KEY','RENDER']:monkeypatch.delenv(name,raising=False)
    open_dbs=[]
    def make(handler):
        db=DB(str(tmp_path/('db'+str(len(open_dbs))+'.sqlite')));open_dbs.append(db)
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
        return TestClient(create_app(db,client)),db
    yield make
    for db in open_dbs:db.conn.close()

def model_data(names):return {'data':[{'id':name,'capabilities':{'completion_chat':True}} for name in names]}
def reply(text='Hi, MONTAi.'):return {'choices':[{'message':{'content':text},'finish_reason':'stop'}]}
def chat(c,id='test-id-12345'):return c.post('/api/chat',headers=H,json={'text':'Hello','request_id':id})

def test_auto_mistral_encrypted_fallback_remember_winner(factory):
    attempts=[];bodies=[]
    def handler(r):
        assert r.url.host=='api.mistral.ai'
        if r.method=='GET':return httpx.Response(200,json=model_data(['mistral-small-latest','mistral-alternate']))
        body=json.loads(r.content);attempts.append(body['model']);bodies.append(body)
        return httpx.Response(404,json={}) if body['model']=='mistral-small-latest' else httpx.Response(200,json=reply())
    c,db=factory(handler)
    with c:
        result=c.post('/api/providers',headers=H,json={'api_key':MKEY})
        assert result.status_code==200,result.text
        assert result.json()['provider']=='mistral'
        assert result.json()['generation_verified'] is False
        assert MKEY not in db.get('ai_key_mistral')
        c.post('/api/memories',headers=H,json={'text':'I make edits.'})
        assert chat(c).status_code==200
        assert attempts==['mistral-small-latest','mistral-alternate']
        assert 'I make edits.' in bodies[0]['messages'][0]['content']
        assert chat(c).status_code==200 and len(attempts)==2
        assert chat(c,'another-request-001').status_code==200
        assert attempts[-1]=='mistral-alternate'
        status=c.get('/api/status',headers=H)
        assert status.json()['ai_model']=='mistral-alternate'
        assert MKEY not in status.text
        assert len(c.get('/api/messages',headers=H).json()['messages'])==4
        assert c.delete('/api/providers/mistral',headers=H).status_code==200
        assert chat(c,'after-removal-001').status_code==409

def test_cross_provider_quota_fallback_and_cooldown(factory):
    seen=[]
    def handler(r):
        if r.method=='GET':return httpx.Response(200,json=model_data(['mistral-small-latest'] if r.url.host=='api.mistral.ai' else ['llama-3.1-8b-instant']))
        seen.append(r.url.host)
        if r.url.host=='api.mistral.ai':return httpx.Response(429,json={'error':'PRIVATE'},headers={'Retry-After':'60'})
        return httpx.Response(200,json=reply())
    c,db=factory(handler)
    with c:
        assert c.post('/api/providers',headers=H,json={'api_key':'gsk_testgroqkey'}).status_code==200
        assert c.post('/api/providers',headers=H,json={'api_key':MKEY}).status_code==200
        assert chat(c).status_code==200
        assert seen==['api.mistral.ai','api.groq.com']
        assert chat(c,'second-request-001').status_code==200
        assert seen.count('api.mistral.ai')==1
        assert db.run('SELECT COUNT(*) FROM messages').fetchone()[0]==4

def test_openrouter_only_zero_cost_and_key_validated(factory):
    seen=[]
    def handler(r):
        seen.append(r)
        if r.url.path.endswith('/models'):return httpx.Response(200,json={'data':[
            {'id':'paid','pricing':{'prompt':'0.1','completion':'0.1'}},
            {'id':'request-fee','pricing':{'prompt':'0','completion':'0','request':'1'}},
            {'id':'free-model:free','pricing':{'prompt':'0','completion':'0','request':'0'}}]})
        if r.url.path.endswith('/key'):return httpx.Response(200,json={'data':{}})
        return httpx.Response(200,json=reply())
    c,db=factory(handler)
    with c:
        assert c.post('/api/providers',headers=H,json={'api_key':'sk-or-v1-test'}).status_code==200
        assert chat(c).status_code==200
        assert json.loads(seen[-1].content)['model']=='free-model:free'
        assert any(r.url.path.endswith('/key') for r in seen)

def test_failed_detection_does_not_save_or_broadcast(factory):
    hosts=[]
    def handler(r):hosts.append(r.url.host);return httpx.Response(401,json={'message':MKEY})
    c,db=factory(handler)
    with c:
        r=c.post('/api/providers',headers=H,json={'api_key':MKEY})
        assert r.status_code==502 and MKEY not in r.text
        assert hosts==['api.mistral.ai']
        assert db.get('ai_key_mistral')==''
        assert c.post('/api/providers',headers=H,json={'api_key':'sk-unidentified-test'}).status_code==422
        assert hosts==['api.mistral.ai']
        assert c.post('/api/providers',json={'api_key':MKEY}).status_code==401

def test_all_failed_no_partial_history_and_sanitized(factory):
    def handler(r):
        if r.method=='GET':return httpx.Response(200,json=model_data(['mistral-small-latest']))
        return httpx.Response(404,json={'message':'SECRET-UPSTREAM-CONTENT'})
    c,db=factory(handler)
    with c:
        c.post('/api/providers',headers=H,json={'api_key':MKEY})
        r=chat(c)
        assert r.status_code==502 and 'SECRET-UPSTREAM-CONTENT' not in r.text
        assert c.get('/api/messages',headers=H).json()['messages']==[]
        assert db.run('SELECT COUNT(*) FROM receipts').fetchone()[0]==0

def test_refusal_does_not_route_around_filter(factory):
    seen=[]
    def handler(r):
        if r.method=='GET':return httpx.Response(200,json=model_data(['mistral-small-latest','other-model']))
        seen.append(1);return httpx.Response(200,json={'choices':[{'finish_reason':'content_filter','message':{'content':''}}]})
    c,db=factory(handler)
    with c:
        c.post('/api/providers',headers=H,json={'api_key':MKEY})
        assert chat(c).status_code==422 and len(seen)==1

def test_custom_url_private_rejected():
    for url in ['http://example.com/v1','https://127.0.0.1/v1','https://[::1]/v1','https://example.com:8443/v1','https://user:pass@example.com/v1']:
        with pytest.raises(HTTPException):asyncio.run(custom_url(url))

def test_provider_override_custom_protocol(factory,monkeypatch):
    import server.ai as module
    async def trusted(url):return 'https://custom.example/v1'
    monkeypatch.setattr(module,'custom_url',trusted)
    def handler(r):
        assert r.url.host=='custom.example'
        assert r.headers['authorization']=='Bearer opaque-test-key'
        if r.method=='GET':return httpx.Response(200,json=model_data(['custom-chat']))
        return httpx.Response(200,json=reply())
    c,db=factory(handler)
    with c:
        assert c.post('/api/providers',headers=H,json={'api_key':'opaque-test-key','provider':'custom','base_url':'https://custom.example/v1'}).status_code==200
        assert chat(c).status_code==200
        assert c.get('/api/status',headers=H).json()['ai_provider']=='custom'

def test_auto_prefixes():
    assert detect('AIza123')=='gemini'
    assert detect('gsk_123')=='groq'
    assert detect('sk-or-v1-123')=='openrouter'
    assert detect(MKEY)=='mistral'
