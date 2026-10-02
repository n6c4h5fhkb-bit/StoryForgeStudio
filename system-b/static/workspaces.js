import {workspacePrefix,workspaceUrl} from './common.js';
if(workspacePrefix){
 const stylesheet=document.createElement('link');stylesheet.rel='stylesheet';stylesheet.href=workspacePrefix+'/static/workspaces.css';document.head.append(stylesheet);
 const install=()=>{
  for(const element of document.querySelectorAll('a[href],link[href],img[src],video[src],source[src]')){
   const key=element.hasAttribute('href')?'href':'src',value=element.getAttribute(key),scoped=workspaceUrl(value);
   if(value!==scoped)element.setAttribute(key,scoped);
  }
  const header=document.querySelector('.rw-header-actions,.topbar-actions');if(!header||header.querySelector('.workspace-switcher'))return;header.insertAdjacentHTML('afterbegin',`<nav class="workspace-switcher" aria-label="工作区"><a href="/a/" class="${workspacePrefix==='/a'?'active':''}">A 剧本</a><a href="/b/" class="${workspacePrefix==='/b'?'active':''}">B 导演与制作</a></nav>`);
 };
 new MutationObserver(install).observe(document.documentElement,{childList:true,subtree:true,attributes:true,attributeFilter:['href','src']});install();
 if(workspacePrefix==='/b')document.addEventListener('click',event=>{const el=event.target.closest('[data-action="new"]');if(el){event.preventDefault();event.stopImmediatePropagation();location.assign('/a/');}},true);
}
