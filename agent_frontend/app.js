const chat=document.getElementById('chat');
const form=document.getElementById('form');
let eventSource=null;
let currentSessionId = null;

function add(role,text){
  const d=document.createElement('div');
  d.className='msg '+role;
  d.textContent=text;
  chat.appendChild(d);
  chat.scrollTop=chat.scrollHeight;
}
function status(text){const el=document.getElementById('status'); if(el) el.textContent=text;}
function val(id){return (document.getElementById(id)?.value || '').trim();}
function uuid(){return crypto.randomUUID();}

function buildBusinessContext(session, messageId){
  return {
    customer_key: val('customerKey') || null,
    contract_key: val('contractKey') || null,
    interaction_key: val('interactionKey') || messageId,
    account_key: val('accountKey') || null,
    resource_key: val('resourceKey') || null,
    session_key: session || null,
    metadata: {frontend: 'agent_frontend', version: 'business-context-v2'}
  };
}

function syncDomainAliases(payload, businessContext){
  const agent=val('agent');
  if(agent === 'retail_orders'){
    payload.customer_id = businessContext.customer_key;
    payload.order_id = businessContext.contract_key;
  } else {
    payload.msisdn = businessContext.customer_key;
    payload.invoice_id = businessContext.contract_key;
    payload.ura_call_id = businessContext.interaction_key;
    payload.asset_id = businessContext.resource_key;
  }
}

function adicionarMensagem(role, text) {
  const chat =
      document.getElementById("chat") ||
      document.getElementById("messages") ||
      document.querySelector(".chat") ||
      document.querySelector(".messages") ||
      document.querySelector("[data-chat]");

  if (!chat) {
    console.error("Não encontrei o container do chat no HTML.");
    console.log("Mensagem que seria exibida:", role, text);
    return;
  }

  const div = document.createElement("div");

  if (role === "user") {
    div.className = "msg user chat-bubble--user";
  } else {
    div.className = "msg assistant chat-bubble--agent";
  }

  div.textContent = text || "";

  chat.appendChild(div);
  chat.scrollTop = chat.scrollHeight;
}

function abrirSSE(sessionId) {
  if (!sessionId) {
    console.error("Não vou abrir SSE sem sessionId.");
    return;
  }

  if (eventSource) {
    eventSource.close();
    eventSource = null;
  }

  const url = `http://localhost:9000/gateway/events/${sessionId}`;

  eventSource = new EventSource(url);

  eventSource.onopen = () => {
    console.log("SSE OPEN");
  };

  eventSource.onerror = (err) => {
    console.error("SSE ERROR:", err);
  };

  const eventos = [
    "connected",
    "waiting",
    "backend.selected",
    "flow.start",
    "workflow.started",
    "message.responded",
    "workflow.completed",
    "flow.end",
    "error"
  ];

  for (const nome of eventos) {
    eventSource.addEventListener(nome, (event) => {

      if (nome === "message.responded") {
        try {
          const data = JSON.parse(event.data);

          const text =
              data.text ||
              data.message ||
              data.response ||
              data.content ||
              data.output ||
              event.data;

          adicionarMensagem("assistant", text);
        } catch {
          adicionarMensagem("assistant", event.data);
        }
      }

      if (nome === "error") {
        adicionarMensagem("assistant", `Erro SSE: ${event.data}`);
      }
    });
  }
}

function connectSSE(backend, sessionId){
  if(!sessionId) return;
  if(eventSource) eventSource.close();
  eventSource=new EventSource(`${backend}/gateway/events/${encodeURIComponent(sessionId)}`);
  eventSource._sessionId=sessionId;
  eventSource.addEventListener('connected', ()=>status('SSE conectado'));
  eventSource.addEventListener('flow.start', ()=>status('Fluxo iniciado'));
  eventSource.addEventListener('workflow.started', ()=>status('Workflow em execução'));
  eventSource.addEventListener('session.upserted', e=>{
    try{
      const data=JSON.parse(e.data);
      if(data.business_context) console.debug('business_context', data.business_context);
    }catch(_){/* noop */}
  });
  eventSource.addEventListener('workflow.completed', ()=>status('Workflow concluído'));
  eventSource.addEventListener('message.responded', e=>{
    const data=JSON.parse(e.data);
    if(data.text) add('assistant', data.text);
    if(data.metadata?.business_context) console.debug('metadata.business_context', data.metadata.business_context);
    status('Resposta recebida');
  });
  eventSource.addEventListener('flow.end', ()=>status('Fluxo finalizado'));
  eventSource.onerror=()=>status('SSE desconectado ou aguardando backend');
}

form.addEventListener('submit', async (e)=>{
  e.preventDefault();
  const input=document.getElementById('message');
  const text=input.value.trim(); if(!text) return;
  add('user', text); input.value='';

  const backend=val('backend').replace(/\/$/,'');
  const channel=val('channel');
  const session=val('session') || uuid();
  const messageId=uuid();
  const tenantId=val('tenant') || 'default';
  const agentId=val('agent') || 'telecom_contas';
  document.getElementById('session').value=session;

  const businessContext=buildBusinessContext(session, messageId);
  const commonContext={
    channel_id:'browser',
    tenant_id:tenantId,
    agent_id:agentId,
    business_context:businessContext
  };

  const payload = channel === 'voice' ?
    {transcript:text, session_id:session, ani:businessContext.customer_key, message_id:messageId, tenant_id:tenantId, agent_id:agentId, context:commonContext} :
    {message:text, text:text, session_id:session, user_id:businessContext.customer_key || 'web-user', message_id:messageId, tenant_id:tenantId, agent_id:agentId, context:commonContext};
  syncDomainAliases(payload, businessContext);

  try{
    const useSse=document.getElementById('useSse')?.checked;
    const endpoint=useSse?'/gateway/message/sse':'/gateway/message';
    if(useSse){
      connectSSE(backend, session);
    }
    const res=await fetch(`${backend}${endpoint}`, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({channel, tenant_id:tenantId, agent_id:agentId, payload})});
    if(!res.ok) throw new Error(`${res.status} ${res.statusText}`);
    const data=await res.json();
    document.getElementById('session').value=data.session_id || session;

    if (data.text) {
      adicionarMensagem("assistant", data.text);
    }

    if (data.session_id) {
      currentSessionId = data.session_id;
      abrirSSE(currentSessionId);
    }
    if(!useSse) add('assistant', data.text || data.speak || JSON.stringify(data));
  }catch(err){
    add('assistant', `Erro ao chamar backend: ${err.message}`);
    status('Erro de conexão');
  }
});
