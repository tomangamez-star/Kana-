"""Provider routing. Keys only go to their identified or explicitly selected provider."""
import asyncio
import ipaddress
import re
import socket
import time
from urllib.parse import urlsplit, quote

import httpx
from fastapi import HTTPException

PROVIDERS = {
    'mistral': ('Mistral', 'https://api.mistral.ai/v1'),
    'gemini': ('Gemini', 'https://generativelanguage.googleapis.com/v1beta'),
    'groq': ('Groq', 'https://api.groq.com/openai/v1'),
    'openrouter': ('OpenRouter', 'https://openrouter.ai/api/v1'),
    'custom': ('Custom OpenAI-compatible', ''),
}
PREFERRED = {
    'mistral': ['mistral-small-latest', 'mistral-medium-latest', 'ministral-8b-latest'],
    'gemini': ['gemini-2.5-flash', 'gemini-2.5-flash-lite'],
    'groq': ['llama-3.3-70b-versatile', 'llama-3.1-8b-instant', 'openai/gpt-oss-20b'],
    'openrouter': ['openrouter/free'],
}

def detect(key):
    if key.startswith('AIza'): return 'gemini'
    if key.startswith('gsk_'): return 'groq'
    if key.startswith('sk-or-'): return 'openrouter'
    # Mistral keys have no exclusive public prefix. Validate only against Mistral;
    # never broadcast an unidentified credential to unrelated providers.
    if re.fullmatch(r'[A-Za-z0-9]{24,128}', key): return 'mistral'
    raise HTTPException(422, 'Cannot safely identify this key. Choose its provider under Advanced, or use Custom with its API base URL.')

async def custom_url(value):
    value = value.strip().rstrip('/')
    try:
        u = urlsplit(value)
        if u.scheme != 'https' or not u.hostname or u.username or u.password or u.query or u.fragment or (u.port not in (None,443)):
            raise ValueError()
        hosts = await asyncio.to_thread(socket.getaddrinfo,u.hostname,443,type=socket.SOCK_STREAM)
        if not hosts or any(not ipaddress.ip_address(x[4][0]).is_global for x in hosts): raise ValueError()
    except (ValueError,OSError): raise HTTPException(422,'Custom API base URL must use HTTPS on port 443 and a public internet host, with no credentials or query string.') from None
    return value

class Router:
    def __init__(self, db, getsecret, storesecret, client):
        self.db,self.secret,self.storesecret,self.client=db,getsecret,storesecret,client
        self.cache={};self.cooldown={};self.last_error=''
    def keys(self):
        result={}
        for p in PROVIDERS:
            raw=self.db.get('ai_key_'+p,None)
            key=self.secret('ai_key_'+p) if raw is not None else self.secret(p+'_api_key') if p!='custom' else ''
            if key: result[p]=key
        return result
    def order(self):
        keys=self.keys()
        value=self.db.get('ai_priority','')
        return [p for p in value.split(',') if p in keys]+[p for p in keys if p not in value.split(',')]
    def status(self):
        return {'providers':[{'id':p,'name':PROVIDERS[p][0]} for p in self.order()], 'has_ai_key':bool(self.keys()),'ai_provider':self.db.get('ai_last_provider'),'ai_model':self.db.get('ai_last_model'),'ai_last_error':self.last_error}
    async def base(self,p):
        return await custom_url(self.db.get('ai_custom_url')) if p=='custom' else PROVIDERS[p][1]
    async def models(self,p,key,base=None,refresh=False):
        cachekey=(p,key,base)
        cached=self.cache.get(cachekey)
        if not refresh and cached and time.monotonic()-cached[0]<300: return cached[1]
        base=base or await self.base(p)
        headers={'x-goog-api-key':key} if p=='gemini' else {'Authorization':'Bearer '+key}
        names=[];token=''
        for _ in range(10 if p=='gemini' else 1):
            params={'pageSize':100,**({'pageToken':token} if token else {})} if p=='gemini' else {}
            r=await self.client().get(base+'/models',headers=headers,params=params,timeout=10,follow_redirects=False)
            if r.status_code!=200:
                raise HTTPException(502, self.reason(p,r.status_code))
            data=r.json()
            if p=='gemini':
                names += [m['name'].removeprefix('models/') for m in data.get('models',[]) if 'generateContent' in m.get('supportedGenerationMethods',[]) and not any(x in m['name'].lower() for x in ['embedding','tts','image','native-audio','live','robotics'])]
                token=data.get('nextPageToken','')
                if not token:break
            else:
                for m in data.get('data',[]):
                    name=m.get('id','')
                    if not name:continue
                    if p=='mistral' and not m.get('capabilities',{}).get('completion_chat',False):continue
                    if p=='groq' and (not m.get('active',True) or any(x in name.lower() for x in ['whisper','tts','guard','orpheus'])):continue
                    if p=='openrouter':
                        pricing=m.get('pricing',{})
                        try:
                            if not pricing or any(float(v)!=0 for v in pricing.values()):continue
                        except (TypeError,ValueError):continue
                        if m.get('architecture',{}).get('output_modalities',['text'])!=['text']:continue
                    names.append(name)
        # OpenRouter listing is public: authenticate the key independently before saving.
        if p=='openrouter':
            check=await self.client().get(base+'/key',headers=headers,timeout=10,follow_redirects=False)
            if check.status_code!=200:raise HTTPException(502,self.reason(p,check.status_code))
        names=list(dict.fromkeys(names))
        if not names:raise HTTPException(502,PROVIDERS[p][0]+': no eligible chat models found for this key. OpenRouter is restricted to zero-priced models.')
        self.cache[cachekey]=(time.monotonic(),names)
        return names
    @staticmethod
    def reason(p,status):
        return PROVIDERS[p][0]+': '+{400:'request rejected',401:'invalid API key',402:'no free quota or credit available',403:'access denied',404:'model unavailable',408:'request timed out',429:'quota or rate limit reached'}.get(status,'provider unavailable (HTTP '+str(status)+')')
    async def add(self,key,provider='auto',url=''):
        key=key.strip()
        if not key or any(c.isspace() for c in key):raise HTTPException(422,'Paste the API key alone, without spaces or a Bearer prefix.')
        p=detect(key) if provider=='auto' else provider
        if p not in PROVIDERS:raise HTTPException(422,'Unsupported provider')
        base=await custom_url(url) if p=='custom' else PROVIDERS[p][1]
        try: names=await self.models(p,key,base,refresh=True)
        except httpx.RequestError:raise HTTPException(502,PROVIDERS[p][0]+': connection failed; key was not saved.') from None
        except (ValueError,TypeError,KeyError):raise HTTPException(502,PROVIDERS[p][0]+': invalid model-list response; key was not saved.') from None
        # Listing only discovers capabilities; the first real chat tests generation.
        order=[p]+[x for x in self.order() if x!=p]
        with self.db.transaction():
            self.storesecret('ai_key_'+p,key)
            if p=='custom':self.db.put('ai_custom_url',base)
            self.db.put('ai_priority',','.join(order))
            self.db.put('ai_last_provider','');self.db.put('ai_last_model','')
        self.cooldown.pop(p,None);self.last_error=''
        return {'provider':p,'name':PROVIDERS[p][0],'model_count':len(names),'generation_verified':False,**self.status()}
    def remove(self,p):
        if p not in PROVIDERS:raise HTTPException(404,'Unknown provider')
        self.db.put('ai_key_'+p,'');self.db.put('ai_priority',','.join(x for x in self.order() if x!=p))
        if self.db.get('ai_last_provider')==p:self.db.put('ai_last_provider','');self.db.put('ai_last_model','')
        self.cache.clear();self.cooldown.pop(p,None)
    async def generate(self,system,history,text):
        if not self.keys():raise HTTPException(409,'Add an AI API key in Settings first.')
        errors=[];attempts=0
        deadline=time.monotonic()+65
        order=self.order()
        for index,p in enumerate(order):
            if time.monotonic()>=deadline or attempts>=6:break
            if self.cooldown.get(p,0)>time.monotonic():errors.append(PROVIDERS[p][0]+': cooling down after rate limit');continue
            key=self.keys().get(p)
            try:
                base=await self.base(p)
                names=await self.models(p,key,base)
                preferred=[self.db.get('ai_success_'+p)]+PREFERRED.get(p,[])
                names=sorted(names,key=lambda n:(preferred.index(n) if n in preferred else len(preferred),n))
                last=''
                allowance=min(3,max(1,6-attempts-(len(order)-index-1)))
                for model in names[:allowance]:
                    left=deadline-time.monotonic()
                    if left<1 or attempts>=6:break
                    attempts+=1
                    headers={'x-goog-api-key':key} if p=='gemini' else {'Authorization':'Bearer '+key}
                    if p=='gemini':
                        contents=[{'role':'model' if role=='assistant' else 'user','parts':[{'text':body}]} for role,body in history]
                        contents.append({'role':'user','parts':[{'text':text}]})
                        payload={'systemInstruction':{'parts':[{'text':system}]},'contents':contents,'generationConfig':{'temperature':0.9,'maxOutputTokens':2048}}
                        endpoint=base+'/models/'+quote(model,safe='-._')+':generateContent'
                    else:
                        payload={'model':model,'messages':[{'role':'system','content':system}]+[{'role':r,'content':t} for r,t in history]+[{'role':'user','content':text}], 'max_tokens':1024}
                        endpoint=base+'/chat/completions'
                    try:r=await self.client().post(endpoint,headers=headers,json=payload,timeout=min(18,left),follow_redirects=False)
                    except httpx.RequestError:last=PROVIDERS[p][0]+': network error';break
                    if r.status_code!=200:
                        last=self.reason(p,r.status_code)
                        if r.status_code==429:
                            try: delay=max(10,min(86400,float(r.headers.get('Retry-After','30'))))
                            except ValueError:delay=30
                            self.cooldown[p]=time.monotonic()+delay
                            break
                        if r.status_code in (401,402,403) or r.status_code>=500:break
                        continue
                    data=r.json()
                    if p=='gemini':
                        if data.get('promptFeedback',{}).get('blockReason'):raise HTTPException(422,'The provider blocked this message. Try rephrasing it.')
                        candidate=(data.get('candidates') or [{}])[0]
                        if candidate.get('finishReason') in ['SAFETY','PROHIBITED_CONTENT']:raise HTTPException(422,'The provider blocked this message. Try rephrasing it.')
                        reply=''.join(x.get('text','') for x in candidate.get('content',{}).get('parts',[]) if not x.get('thought')).strip()
                    else:
                        choice=(data.get('choices') or [{}])[0]
                        if choice.get('finish_reason')=='content_filter' or choice.get('message',{}).get('refusal'):raise HTTPException(422,'The provider blocked this message. Try rephrasing it.')
                        content=choice.get('message',{}).get('content','')
                        reply=content.strip() if isinstance(content,str) else ''
                    if not reply:last=PROVIDERS[p][0]+': no text returned';continue
                    self.db.put('ai_success_'+p,model);self.db.put('ai_last_provider',p);self.db.put('ai_last_model',model);self.last_error=''
                    return reply
                if last:errors.append(last)
            except HTTPException as e:
                if e.status_code==422:raise
                errors.append(str(e.detail))
            except (httpx.RequestError,ValueError,KeyError,TypeError):errors.append(PROVIDERS[p][0]+': could not read provider response')
        self.last_error='; '.join(errors) or 'No models answered within the retry window'
        raise HTTPException(502,self.last_error+'. No chat messages were saved. Retry later or add another provider.')
