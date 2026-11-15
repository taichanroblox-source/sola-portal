const body=document.body;
const theme=localStorage.getItem("sola-theme")||"sunset";
body.dataset.theme=theme;
const chooser=document.getElementById("theme");
if(chooser){chooser.value=theme;chooser.addEventListener("change",e=>{body.dataset.theme=e.target.value;localStorage.setItem("sola-theme",e.target.value)})}
if(localStorage.getItem("sola-collapse")==="yes")body.classList.add("collapsed");
document.getElementById("collapse")?.addEventListener("click",()=>{body.classList.toggle("collapsed");localStorage.setItem("sola-collapse",body.classList.contains("collapsed")?"yes":"no")});
document.getElementById("more")?.addEventListener("click",()=>{let menu=document.getElementById("mobilemenu");menu.hidden=!menu.hidden});
const hour=new Date().getHours(),greeting=document.getElementById("greeting");
if(greeting)greeting.textContent=hour<11?"おはよう":hour<18?"こんにちは":"こんばんは";
document.querySelectorAll(".servicecard").forEach(a=>a.addEventListener("click",()=>{localStorage.setItem("sola-recent-title",a.querySelector("h3")?.textContent||"サービス");localStorage.setItem("sola-recent-url",a.href)}));
const recent=document.getElementById("recent"),recentlink=document.getElementById("recentlink");
if(recent&&recentlink){const title=localStorage.getItem("sola-recent-title"),url=localStorage.getItem("sola-recent-url");if(title&&url&&url.startsWith(location.origin+"/go/")){recent.hidden=false;recentlink.href=url;recentlink.className="servicecard";recentlink.textContent=title+" ↗"}}
const file=document.getElementById("avatarfile"),hidden=document.getElementById("avatar"),preview=document.getElementById("avatarpreview");
file?.addEventListener("change",()=>{const f=file.files[0];if(!f)return;if(f.size>350000||!["image/png","image/jpeg","image/webp"].includes(f.type)){alert("画像は350KB以下のPNG・JPEG・WebPにしてね");file.value="";return}const reader=new FileReader();reader.onload=()=>{hidden.value=reader.result;preview.innerHTML="";const img=document.createElement("img");img.src=reader.result;img.alt="プロフィール画像";preview.append(img)};reader.readAsDataURL(f)});
