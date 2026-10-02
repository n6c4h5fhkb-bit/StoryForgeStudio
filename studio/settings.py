from __future__ import annotations
import copy,json,os,threading,math
from pathlib import Path
from .core import ensure,digest

PRICE_FIELDS=('inputPerMillion','outputPerMillion','cachedInputPerMillion','cacheWritePerMillion','cacheWrite5mPerMillion','cacheWrite1hPerMillion')
CACHE_PRICE_FIELDS=PRICE_FIELDS[2:]
SAFE_EXTRA={'top_p','top_k','seed','stop','stop_sequences','presence_penalty','frequency_penalty','reasoning_effort','verbosity','prompt_cache_key','prompt_cache_retention','cache_control','metadata','user'}

def price_identity(model):
 return digest({k:model.get(k) for k in ('provider','baseUrl','model')})

def media_price_identity(media):
 return digest({k:media.get(k) for k in ('provider','baseUrl','model','imageModel','videoModel','imageResolution','videoResolution')})

def number(value,label,minimum,maximum=None,integer=False):
 try:parsed=float(value)
 except (TypeError,ValueError):parsed=float('nan')
 ensure(not isinstance(value,bool) and math.isfinite(parsed) and parsed>=minimum and (maximum is None or parsed<=maximum) and (not integer or parsed.is_integer()),label+' 超出有效范围','invalid_model_config')
 return parsed

def validate_model(model):
 ensure(isinstance(model,dict),'模型配置必须是对象','invalid_model_config')
 ensure(model.get('provider') in ('demo','openai','anthropic','gemini','codex_cli'),'不支持的模型协议','invalid_model_config')
 model['timeout']=number(model.get('timeout',180),'模型 timeout',.01,1800)
 model['maxTokens']=int(number(model.get('maxTokens',6000),'maxTokens',1,1000000,True))
 model['contextCharacters']=int(number(model.get('contextCharacters',32000),'contextCharacters',1,10000000,True))
 model['temperature']=number(model.get('temperature',.7),'temperature',0,2)
 model['imageTokenReservation']=int(number(model.get('imageTokenReservation',8192),'imageTokenReservation',1,1000000,True))
 for field in PRICE_FIELDS:
  if field in model:model[field]=number(model[field],field,0)
 ensure(model.get('format','json_object') in ('json_object','json_schema','text'),'不支持的输出格式','invalid_model_config')
 ensure(isinstance(model.get('priceConfigured',False),bool),'priceConfigured 必须是布尔值','invalid_model_config')
 for field in ('codexPath','codexHome','codexReasoning'):
  ensure(isinstance(model.get(field,''),str) and '\x00' not in model.get(field,''),field+' 必须是有效文本','invalid_model_config')
 ensure(model.get('codexReasoning','') in ('','none','minimal','low','medium','high','xhigh','max','ultra'),'Codex 推理强度无效','invalid_model_config')
 extra=model.get('extraBody',{})
 ensure(isinstance(extra,dict),'extraBody 必须是对象','invalid_model_config')
 ensure(not (set(extra)-SAFE_EXTRA),'extraBody 含不支持的字段；模型、消息、输出上限与工具必须通过受控配置设置','unsafe_extra_body',400,{'fields':sorted(set(extra)-SAFE_EXTRA)})

DEFAULT={
 'llm':{'provider':'demo','baseUrl':'','apiKey':'','model':'','format':'json_object','temperature':0.7,'maxTokens':6000,'timeout':180,'contextCharacters':32000,'inputPerMillion':0,'outputPerMillion':0,'priceConfigured':False,'extraBody':{}},
 'budget':{'project':50,'currency':'USD'}, 'models':{},'llmConcurrency':{'openai':2,'anthropic':2,'gemini':2,'codex_cli':1},
 'media':{'provider':'manual','baseUrl':'','apiKey':'','model':'','imageModel':'5.0','videoModel':'seedance2.0fast','imageResolution':'2k','videoResolution':'720p','session':0,'imageCost':0,'videoCostPerSecond':0,'priceConfigured':False,'pollSeconds':3,'timeout':900},
 'runners':{},'routing':{'roles':{'builder':'codex','operator':'subprocess','curator':'codex'},'overrides':[],'fallback':{'enabled':False}},
 'ffmpeg':'','ffprobe':'','maxRetries':3,'failureCircuit':5,'gatePlugins':[],
}
class Settings:
 def __init__(self,root):self.path=Path(root)/'settings.json';self.lock=threading.RLock()
 def read(self,redact=False):
  with self.lock:
   out=copy.deepcopy(DEFAULT)
   if self.path.exists():self._merge(out,json.loads(self.path.read_text(encoding='utf-8')))
  previous_identity=price_identity(out['llm'])
  if os.environ.get('STUDIO_LLM_KEY'):out['llm']['apiKey']=os.environ['STUDIO_LLM_KEY']
  if os.environ.get('STUDIO_LLM_URL'):out['llm']['baseUrl']=os.environ['STUDIO_LLM_URL']
  if os.environ.get('STUDIO_LLM_MODEL'):out['llm']['model']=os.environ['STUDIO_LLM_MODEL']
  if os.environ.get('STUDIO_LLM_URL'):out['llm']['provider']='openai'
  if price_identity(out['llm'])!=previous_identity or out['llm'].get('_priceIdentity',price_identity(out['llm']))!=price_identity(out['llm']):out['llm']['priceConfigured']=False
  return self._redact(out) if redact else out
 def _merge(self,a,b):
  for k,v in b.items():
   if k in ('apiKey','token','secret') and v=='__KEEP__':continue
   if k in CACHE_PRICE_FIELDS and v is None:a.pop(k,None);continue
   if isinstance(v,dict):
    if not isinstance(a.get(k),dict):a[k]={}
    self._merge(a[k],v)
   else:a[k]=copy.deepcopy(v)
 def _redact(self,d):
  if isinstance(d,dict):return {k:('__KEEP__' if v else '') if k in ('apiKey','token','secret') else self._redact(v) for k,v in d.items()}
  if isinstance(d,list):return [self._redact(x) for x in d]
  return d
 def save(self,patch):
  with self.lock:
   ensure(isinstance(patch,dict),'设置必须是对象')
   previous=self.read();value=copy.deepcopy(previous)
   # New dedicated roles retain the previous direction connection when first edited.
   for role in ('treatment','shots'):
    if role in (patch.get('models') or {}) and role not in value['models'] and 'direction' in value['models']:
     value['models'][role]=copy.deepcopy(value['models']['direction'])
   self._merge(value,patch)
   ensure(isinstance(value.get('llm'),dict) and isinstance(value.get('models'),dict),'模型配置必须是对象','invalid_model_config')
   if price_identity(value['llm'])!=price_identity(previous['llm']):
    value['llm']['priceConfigured']=False
    for field in CACHE_PRICE_FIELDS:
     if field not in patch.get('llm',{}):value['llm'].pop(field,None)
   if patch.get('llm',{}).get('priceConfigured') is True:
    value['llm']['priceConfigured']=True;value['llm']['_priceIdentity']=price_identity(value['llm'])
   validate_model(value['llm'])
   for role,override in value['models'].items():
    ensure(isinstance(override,dict),'角色模型配置必须是对象','invalid_model_config')
    previous_override=previous.get('models',{}).get(role,previous.get('models',{}).get('direction',{}) if role in ('treatment','shots') else {})
    before={**previous['llm'],**previous_override};after={**value['llm'],**override}
    if price_identity(before)!=price_identity(after):
     override['priceConfigured']=False
     for field in CACHE_PRICE_FIELDS:
      if field not in patch.get('models',{}).get(role,{}):override.pop(field,None)
    if patch.get('models',{}).get(role,{}).get('priceConfigured') is True:
     override['priceConfigured']=True;override['_priceIdentity']=price_identity(after)
    validate_model({**value['llm'],**override})
   ensure(isinstance(value.get('llmConcurrency'),dict),'并发配置必须是对象','invalid_model_config')
   for provider,limit in value['llmConcurrency'].items():value['llmConcurrency'][provider]=int(number(limit,provider+' 并发',1,32,True))
   for name in ('media','mediaImages','mediaVideos'):
    media=value.get(name,{})
    ensure(media.get('provider','manual') in ('manual','demo','dreamina','openai','generic','comfyui'),'不支持的媒体协议','invalid_media_config')
    for field in ('imageCost','videoCostPerSecond'):
     if field in media:ensure(math.isfinite(float(media[field])) and float(media[field])>=0,'媒体单价必须是非负有限数')
    for field,minimum,maximum in (('pollSeconds',.1,300),('timeout',1,86400),('session',0,1000000)):
     if field in media:media[field]=int(number(media[field],field,minimum,maximum,field=='session')) if field=='session' else number(media[field],field,minimum,maximum)
    if media.get('provider')=='dreamina':
     video_model=media.get('videoModel','seedance2.0fast');video_resolution=media.get('videoResolution','720p');image_model=media.get('imageModel','5.0');image_resolution=media.get('imageResolution','2k')
     ensure(video_model in ('seedance2.0','seedance2.0fast','seedance2.0_vip','seedance2.0fast_vip','seedance2.0mini','seedance2.5'),'Dreamina 视频模型无效','invalid_media_config')
     allowed_video={'seedance2.5':('480p','720p','1080p'),'seedance2.0_vip':('720p','1080p','4k')}.get(video_model,('720p',));ensure(video_resolution in allowed_video,'当前 Dreamina 视频模型不支持所选分辨率','invalid_media_config',422,{'model':video_model,'allowed':allowed_video})
     ensure(image_model in ('3.0','3.1','4.0','4.1','4.5','4.6','4.7','5.0','5.0Pro'),'Dreamina 图像模型无效','invalid_media_config')
     allowed_image=('1k','2k') if image_model in ('3.0','3.1') else ('1.5k','2k','4k') if image_model=='5.0Pro' else ('2k','4k');ensure(image_resolution in allowed_image,'当前 Dreamina 图像模型不支持所选分辨率','invalid_media_config',422,{'model':image_model,'allowed':allowed_image})
    before=previous.get(name,{})
    if media_price_identity(media)!=media_price_identity(before) and patch.get(name,{}).get('priceConfigured') is not True:media['priceConfigured']=False
    if patch.get(name,{}).get('priceConfigured') is True:media['_priceIdentity']=media_price_identity(media)
   temp=self.path.with_suffix('.tmp');temp.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8');temp.replace(self.path)
   try:self.path.chmod(0o600)
   except OSError:pass
  return self.read(True)
 def model(self,role):
  value=self.read();base=copy.deepcopy(value['llm']);fallback={'ideation':'structure','presentation':'script','treatment':'direction','shots':'direction','reviewer':'validator'}.get(role);override=value.get('models',{}).get(role,value.get('models',{}).get(fallback,{}));base.update(override)
  if price_identity(base)!=price_identity(value['llm']):
   for field in CACHE_PRICE_FIELDS:
    if field not in override:base.pop(field,None)
  if price_identity(base)!=price_identity(value['llm']) and 'priceConfigured' not in override:base['priceConfigured']=False
  if base.get('_priceIdentity',price_identity(base))!=price_identity(base):base['priceConfigured']=False
  validate_model(base);return base

 def media(self,kind="keyframe"):
  cfg=self.read();base=copy.deepcopy(cfg["media"]);self._merge(base,cfg.get("mediaVideos" if kind=="clip" else "mediaImages",{}));return base
