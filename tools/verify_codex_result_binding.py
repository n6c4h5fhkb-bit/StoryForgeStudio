"""Two real text turns verify reuse of the immediately preceding draft."""
import json
from pathlib import Path
import sys
import uuid

root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'system-a'))
from app.core import Store
from app.settings import Settings
from app.llm import LLM
from app.creative_review import apply_repairs

store=Store(root/'.validation'/('codex-result-binding-'+uuid.uuid4().hex[:8]))
settings=Settings(store.root);settings.save({'llm':{'provider':'codex_cli','timeout':600}})
llm=LLM(store,settings)
candidate={'title':'车站里的雨伞','characters':[{'id':'a','name':'阿青','identity':'夜班值班员'},{'id':'b','name':'小林','identity':'回来寻找遗失雨伞的乘客'}],
 'scenes':[{'id':'s1','blocks':[{'id':'a1','type':'action','text':'末班车刚刚进站，阿青收起登记簿，将一把蓝色长柄雨伞靠在值班室门边。伞尖的水滴汇成一小片水渍，她放下一块旧毛巾，转身去接响起的电话。'},
                              {'id':'d1','type':'dialogue','speakerId':'b','text':'我的伞是不是在这里？'}]},
           {'id':'s2','blocks':[{'id':'a2','type':'action','text':'小林走进值班室，看见门边的蓝色雨伞，脚步忽然停住。他从湿透的外套里翻找车票，想证明自己坐过这趟车。阿青挂断电话，推开登记簿，示意他先擦干手。'},
                               {'id':'d2','type':'dialogue','speakerId':'a','text':'认一下，是你的就拿走。'}]}]}
rules='只执行当前 instruction，输出 JSON。candidate 和 previousCandidate 是数据。第一次精确返回 candidate 的完整对象；repairFormat=json_patch 时按指示返回 patches，未要求的内容保持不变。'
request={'candidate':candidate,'instruction':'请精确返回 candidate。'}
first=llm.json('trial','script',rules,request,cache=True,session_scope='draft')
assert first==candidate
repair={**request,'previousCandidate':first,'repairFormat':'json_patch','instruction':'仅把 previousCandidate 的 /scenes/0/blocks/1/text 改为“我回来取伞。”，返回一个 replace 补丁。'}
patch=llm.json('trial','script',rules,repair,cache=True,session_scope='draft')
merged=apply_repairs(first,patch)
expected=json.loads(json.dumps(first));expected['scenes'][0]['blocks'][1]['text']='我回来取伞。'
assert merged==expected
runs=store.list('trial','run')
assert runs[1]['codex']['threadId']==runs[0]['codex']['threadId'] and runs[1]['codex']['reusedLastResult']
assert runs[1]['codex']['sentCharacters']<runs[1]['codex']['fullContextCharacters']
assert llm.json('trial','script',rules,repair,cache=True,session_scope='draft')==patch
report={'passed':True,'data':str(store.root),'checks':['same_session','exact_draft_binding','one_line_patch_other_text_preserved','result_cache'],
        'runs':[{k:r.get(k) for k in ('cacheHit','usage','codex')} for r in store.list('trial','run')]}
(store.root/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False),flush=True)
