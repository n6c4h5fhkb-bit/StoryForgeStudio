from __future__ import annotations
from typing import Literal
from pydantic import BaseModel,Field,ConfigDict

class StylePreset(BaseModel):
 id:str
 projectId:str
 name:str
 aslRange:list[float]
 shotCountRange:list[int]
 emptyShotRatio:list[float]
 aspectRatio:str
 shotSizePreference:list[str]
 movementAmplitude:str
 informationInterval:list[float]
 hookInterval:float
 palette:str='冷灰、自然光'
 lightingRatio:float=4
 texture:str='写实'
 promptPrefix:str='cinematic live action, natural light'
 negativePrompt:str='deformed anatomy, inconsistent identity, watermark'
 status:str='draft'
 freshness:str='clean'
 compilerVersion:str='1.0.0'
class Movement(BaseModel):
 type:str='static'
 speed:str='slow'
 startFraming:str=''
 endFraming:str=''
class Lighting(BaseModel):
 keyDirection:float=45
 ratio:float=4
 motivation:str='practical'
class ShotContract(BaseModel):
 id:str
 projectId:str
 sceneId:str
 order:int
 informationPayload:list[str]=Field(default_factory=list)
 shotSize:Literal['ELS','LS','MS','MCU','CU','ECU']
 angle:str='eye'
 lens:float=50
 movement:Movement
 actionLine:str
 isEmpty:bool=False
 duration:float=Field(gt=0)
 subjects:list[str]
 assetVariants:list[str]
 lighting:Lighting
 continuity:dict
 producibilityRisk:dict
 methodVersion:int=1
 performanceBeats:list[dict]=Field(default_factory=list)
 cameraCue:dict=Field(default_factory=dict)
 cutPoint:dict=Field(default_factory=dict)
 status:str='draft'
 freshness:str='clean'
class SceneDirection(BaseModel):
 dramaticFunction:str
 informationPayload:list[str]
 tensionType:Literal['suspense','surprise','mystery']
 emotion:dict
 coverage:dict
 blocking:dict
 lighting:Lighting
 palette:str
 sound:dict
 targetDuration:float=Field(gt=0)
 transitionIn:str|None=None
 transitionOut:str|None=None
 directingPlan:dict=Field(default_factory=dict)
class ShotSkeleton(BaseModel):
 shotId:str|None=None
 shotSize:Literal['ELS','LS','MS','MCU','CU','ECU']
 angle:str='eye'
 lens:float=50
 movement:Movement=Field(default_factory=Movement)
 actionLine:str
 isEmpty:bool=False
 subjects:list[str]=Field(default_factory=list)
 informationPayload:list[str]=Field(default_factory=list)
 emotionWeight:float=Field(default=1,ge=.25,le=4)
 cameraSide:Literal['positive','negative','axis']='positive'
 explicitCrossing:bool=False
 framing:dict=Field(default_factory=dict)
 performanceBeats:list[dict]=Field(default_factory=list)
 cameraCue:dict=Field(default_factory=dict)
 cutPoint:dict=Field(default_factory=dict)
class SkeletonOutput(BaseModel):
 shots:list[ShotSkeleton]=Field(min_length=1,max_length=40)
class TaskSpec(BaseModel):
 taskId:str
 renderKey:str|None=None
 role:Literal['builder','operator','curator']='operator'
 stage:str='B5'
 task:str='image_render'
 objective:str
 inputs:dict
 tools:list[str]
 workdir:str
 acceptance:dict
 limits:dict
 reportSchema:dict=Field(default_factory=dict)
class RunResult(BaseModel):
 status:Literal['ok','failed','timeout','budget_exceeded','rejected']
 artifacts:list[dict]=Field(default_factory=list)
 report:dict=Field(default_factory=dict)
 usage:dict=Field(default_factory=dict)
 runner:dict=Field(default_factory=dict)
