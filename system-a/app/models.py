"""System A domain contracts. Beats are content blocks, never independent tree nodes."""
from __future__ import annotations
from typing import Literal,Any
import copy
from pydantic import BaseModel,Field,ConfigDict,model_validator

Level=Literal['premise','spine','sequence','scene','script']
class StateRef(BaseModel):
    subject:str
    predicate:str
    object:str
class ValueChange(BaseModel):
    axis:str
    from_:str=Field(alias='from')
    to:str
    model_config=ConfigDict(populate_by_name=True)
class Contract(BaseModel):
    summary:str=Field(min_length=1)
    preconditions:list[StateRef]=Field(default_factory=list)
    postconditions:list[StateRef]=Field(default_factory=list)
    valueChange:ValueChange
    reveals:list[str]=Field(default_factory=list)
    obligations:list[str]=Field(default_factory=list)
    entities:list[str]=Field(default_factory=list)
    producibility:dict|None=None
class Node(BaseModel):
    id:str
    projectId:str
    level:Level
    parentId:str|None=None
    order:str='0'
    title:str
    contract:Contract
    body:dict=Field(default_factory=dict)
    status:Literal['draft','accepted','locked','archived']='draft'
    freshness:Literal['clean','opportunity','broken']='clean'
    freshnessNotes:list[dict]=Field(default_factory=list)
    resolution:int=0
    speculative:bool=False
    currentRevision:str=''
    generationComplete:bool=False
    sourceCandidateId:str|None=None
class CandidateItem(BaseModel):
    title:str
    level:Level
    contract:Contract
    body:dict=Field(default_factory=dict)
class CandidateOutput(BaseModel):
    title:str
    summary:str
    rationale:str
    risks:list[str]=Field(default_factory=list)
    items:list[CandidateItem]=Field(min_length=1,max_length=24)
    entityProposals:list[dict]=Field(default_factory=list)
    factProposals:list[dict]=Field(default_factory=list)
    beliefProposals:list[dict]=Field(default_factory=list)

class StoryBody(BaseModel):
    """Minimum readable structure; creative extensions remain allowed."""
    model_config=ConfigDict(extra='allow',allow_inf_nan=False,str_strip_whitespace=True)

class DialogueLine(StoryBody):
    character:str=Field(min_length=1)
    text:str=Field(min_length=1)
    parenthetical:str=''

class ContentBlock(StoryBody):
    type:Literal['action','dialogue','scene_heading','parenthetical','transition']
    text:str=Field(min_length=1)
    character:str|None=None
    @model_validator(mode='after')
    def require_speaker(self):
        if self.type=='dialogue' and not self.character:raise ValueError('对白块必须指定角色 ID')
        return self

class PremiseBody(StoryBody):
    logline:str=Field(min_length=1)
    synopsis:str=Field(min_length=1)

class SpineBody(StoryBody):
    summary:str=Field(min_length=1)
    ending:str=Field(min_length=1)

class SequenceBody(StoryBody):
    goal:str=Field(min_length=1)
    obstacle:str=Field(min_length=1)
    turn:str=Field(min_length=1)
    cost:str=Field(min_length=1)
    summary:str=Field(min_length=1)

class SceneBody(StoryBody):
    location:str=Field(min_length=1)
    timeOfDay:str=Field(min_length=1)
    action:str=Field(min_length=1)
    targetDuration:float=Field(gt=0)
    dialogue:list[DialogueLine]=Field(default_factory=list)
    blocks:list[ContentBlock]=Field(default_factory=list)

class ScriptBody(StoryBody):
    sceneHeading:str=Field(min_length=1)
    action:str=''
    dialogue:list[DialogueLine]=Field(default_factory=list)
    blocks:list[ContentBlock]=Field(default_factory=list)
    targetDuration:float=Field(gt=0)
    @model_validator(mode='after')
    def require_content(self):
        if not self.action and not self.dialogue and not self.blocks:raise ValueError('剧本必须有可读的动作、对白或内容块')
        return self

BODY_MODELS={'premise':PremiseBody,'spine':SpineBody,'sequence':SequenceBody,'scene':SceneBody,'script':ScriptBody}
class ProbeSpec(BaseModel):
    decisionType:str
    sceneSelector:str
    renderTo:Literal['script','keyframe']='script'
    horizontalDepth:int=Field(default=4,ge=1,le=6)
class NodeRef(BaseModel):
    nodeId:str
    boundary:Literal['entry','exit']='entry'
class Entity(BaseModel):
    id:str
    kind:Literal['character','location','prop','rule','faction']
    name:str
    description:str=''
    freezeString:str=''
    voiceProfile:dict=Field(default_factory=dict)
class Fact(BaseModel):
    subject:str
    predicate:str
    object:str
    validFrom:NodeRef
    validUntil:NodeRef|None=None
class Belief(BaseModel):
    holder:str
    content:str
    truth:bool
    validFrom:NodeRef
    validUntil:NodeRef|None=None

CANDIDATE_SCHEMA=CandidateOutput.model_json_schema(by_alias=True)

def candidate_schema(level,phase):
    schema=copy.deepcopy(CANDIDATE_SCHEMA)
    body=BODY_MODELS[level].model_json_schema() if phase=='body' else {'type':'object','maxProperties':0}
    schema['$defs'].update(body.pop('$defs',{}))
    item=schema['$defs']['CandidateItem'];item['properties']['body']=body
    item['properties']['level']={'const':level,'type':'string'}
    item['required']=list(dict.fromkeys([*item.get('required',[]),'body']))
    return schema
