# FieldClaw durable memory

## Product
- FieldClaw = system of record (logbook, zones, PO match, super queue, dashboard)
- Supervisor Claw (this agent) = project brain (wiki, mail, PDFs via Datalab, notifications)

## Endpoints / homes
- FieldClaw API: `FIELDCLAW_BASE_URL` (default `http://127.0.0.1:8000`) with `X-API-Key`
- Project id: `FIELDCLAW_PROJECT_ID` in env
- Wiki FS: `FIELDCLAW_KB_DIR` → `kb/wiki/index.md` first, then linked pages (no vector DB)
- PDF ingest: `wiki_fs.py datalab-ingest` with `DATALAB_API_KEY`

## Messaging
- Telegram bot paired; home channel = Meowy `6009530821`
- Agent email: **kaya-meow@agentmail.to** (AgentMail IMAP/SMTP + MCP)
- Personal Gmail is for the external scenario emitter only — never the agent mailbox

## Skills
- Primary skill: `fieldclaw` (see SKILL.md + MAIL.md)
- AgentMail MCP tools available for threads/messages when useful

## Eval traffic
- Day-wise site emails may arrive naturally via AgentMail; treat them as live site mail
- Never mention or control a “sim”
