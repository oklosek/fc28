// frontend/farmcare.js – czysty JS, gotowy do podmiany UI z Figma
const $ = (s)=>document.querySelector(s);
const ventList = $("#ventList");
const allRange = $("#allRange");
const allVal = $("#allVal");
const modeBtn = $("#modeBtn");
let mode = "auto";
let vents = [];

async function fetchState() {
  const r = await fetch("/api/state");
  const j = await r.json();
  mode = j.mode;
  $("#t_in").textContent  = j.sensors.internal_temp.toFixed(1)+" °C";
  $("#t_out").textContent = j.sensors.external_temp.toFixed(1)+" °C";
  $("#hum").textContent   = j.sensors.internal_hum.toFixed(0)+" %";
  $("#wind").textContent  = j.sensors.wind_speed.toFixed(1)+" m/s";
  $("#rain").textContent  = j.sensors.rain>0.5 ? "tak" : "nie";
  modeBtn.textContent = (mode==="auto" ? "Przełącz na ręczny" : "Przełącz na auto");

  vents = j.vents;
  renderVents();
  const avg = vents.reduce((a,v)=>a+v.position,0)/Math.max(1,vents.length);
  allRange.value = Math.round(avg);
  allVal.textContent = Math.round(avg)+"%";
}

function renderVents() {
  ventList.innerHTML = "";
  vents.forEach(v=>{
    const row = document.createElement("div");
    row.className = "vent-row";
    row.innerHTML = `
      <span>#${v.id} ${v.name}</span>
      <input type="range" min="0" max="100" value="${Math.round(v.position)}" ${mode==="auto"||!v.available?"disabled":""} id="vent_${v.id}">
      <span>${Math.round(v.position)}%</span>
      <span class="${v.available?"ok":"err"}">${v.available?"OK":"AWARIA"}</span>
    `;
    ventList.appendChild(row);
    const slider = row.querySelector(`#vent_${v.id}`);
    slider?.addEventListener("change", async ()=>{
      const pos = parseInt(slider.value);
      await fetch(`/api/vents/${v.id}`, {
        method: "POST",
        headers: {"Content-Type":"application/json"},
        body: JSON.stringify({position: pos})
      });
    });
  });
}

allRange.addEventListener("change", async ()=>{
  if (mode!=="manual") return;
  const pos = parseInt(allRange.value);
  allVal.textContent = pos+"%";
  await fetch("/api/vents/all", {
    method: "POST",
    headers: {"Content-Type":"application/json"},
    body: JSON.stringify({position: pos})
  });
});

modeBtn.addEventListener("click", async ()=>{
  const next = (mode==="auto"?"manual":"auto");
  const r = await fetch("/api/mode", {method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify({mode: next})});
  const j = await r.json();
  mode = j.mode;
  modeBtn.textContent = (mode==="auto" ? "Przełącz na ręczny" : "Przełącz na auto");
  renderVents();
});

setInterval(fetchState, 1000);
fetchState();
