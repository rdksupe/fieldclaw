# FieldClaw mail — AgentMail for the agent, Gmail for the sim only

## Split (locked)

| Role | System | Notes |
|------|--------|-------|
| **Agent mailbox** | **AgentMail** `kaya-meow@agentmail.to` | Hermes via **AgentMail MCP / REST** (`message_read` / `message_send`) |
| **Sim sender** | **Gmail** (`sim/.env.sim`) | External `week_email_loop.py` sends **to** `kaya-meow@agentmail.to` |

## Agent (Hermes)

```bash
AGENTMAIL_API_KEY=am_...          # inbox-scoped key OK for messages/threads/send
EMAIL_ADDRESS=kaya-meow@agentmail.to
# EMAIL_PASSWORD=<org AGENTMAIL_API_KEY>  # enables Hermes IMAP/SMTP gateway
# Inbox: kaya-meow@agentmail.to
```

MCP (`mcp_servers.agentmail` in config.yaml) exposes `list_threads`, `get_thread`, `send_message`, etc.

**mail-poll cron:** poll AgentMail threads/messages for `kaya-meow@agentmail.to`, parse, project into FieldClaw — do **not** use Gmail IMAP.

## Do

- Read/send via AgentMail MCP tools (or REST).
- After understanding, project into FieldClaw `email.parsed` / `schedule.flagged`.

## Do not

- Point Hermes `EMAIL_*` at personal Gmail.
- Call FieldClaw `/mail/*` as the agent mail stack.

## Sim (external)

```bash
# sim/.env.sim
HERMES_INBOX=kaya-meow@agentmail.to
SIM_SMTP_USER=...@gmail.com
SIM_SMTP_PASSWORD=...

apps/api/.venv/bin/python sim/emitters/week_email_loop.py --mode smtp --reset-state
```

## Note on IMAP

If you create an **organization** API key (full permissions, not inbox-scoped whitelist missing `inbox_read`), Hermes can use native IMAP:

`EMAIL_PASSWORD=<org_key>` + `EMAIL_IMAP_HOST=imap.agentmail.to` + `EMAIL_SMTP_PORT=465`.
Until then, MCP/API is the path.
