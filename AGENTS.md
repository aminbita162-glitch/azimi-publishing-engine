# Agents

Status: ACTIVE DEVELOPMENT. The agents are defined and tested in a limited way. They run outside the engine.

## What exists

Three agents produce a PDF together. Their complete role definitions are the files in the agents folder. Those files are the only source of truth; the chat history of an agent is not.

| Agent | File | Duty |
|:------|:-----|:-----|
| Amilus Publishing Manager | agents/amilus.txt | Takes the request, plans, splits the work, validates every message, runs the engine commands, reports to the owner |
| Ali Publishing Composer | agents/ali.txt | The only author: writes content.md and the assets of one document |
| Lili Publishing Auditor | agents/lili.txt | Independent audit: reports findings, never fixes |

The owner is the only person who changes rules, names the series, accepts a risk or decides a release.

## How they run

The agents run in a separate agent application on the owner's computer. They are not part of the engine and the engine does not need them: every PDF can be built from the terminal alone.
As proven in November 2026, the application lets an agent read the project folder and run terminal commands, and it asks the owner for approval of every single command.

## Limits that apply to all agents

- The only interpreter is .venv/bin/python3 in the project root.
- Allowed commands: python3 -m engine (check, build, verify, preview, fonts) and read-only ls, cat and head inside the project. Ali may write only content.md and the assets of the document named in the handoff. Lili is read-only.
- Never git, rm, mv, cp, curl, pip, sudo. Committing, tagging, pushing and uploading are done by the owner.
- Never use the always-allow option of the application: it applies to every agent in the application.
- After every run the owner checks what changed with git status.

## How to create or restore an agent

1. In the agent application create a new agent with the exact name from the table.
2. Paste the complete text of its file as the first message.
3. The agent must answer READY followed by its numbered summary. If it answers anything else, discard the agent and create it again.
4. Never paste a changed rule into a chat. Change the file in this folder, raise its version, add a line to CHANGELOG.md, and paste the new file.

## Message protocol

Every message between agents carries a ticket id, sender, receiver, sequence number and type. The formats of the handoffs and reports are defined in the three files. Amilus rejects any delivery or report that does not follow its format.

## Not built yet

- Agents that run inside the engine or the future desktop product.
- A gate command, JSON output and a delivery command in the engine; until then Amilus follows the steps in agents/amilus.txt by hand.
- Any claim that the agents are tested beyond the limited trials recorded in TEST_LOG.md.
