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
- Allowed commands: python3 -m engine (check, build, verify, preview, fonts, agents, ticket) and read-only ls, cat and head inside the project. Ali may write only content.md, the assets of the document named in the handoff and his delivery file. Amilus may write only the handoff and report files of the ticket. Lili may write only her audit file.
- Never git, rm, mv, cp, curl, pip, sudo. Committing, tagging, pushing, uploading and delivering a PDF (python3 -m engine deliver) are done by the owner.
- Never use the always-allow option of the application: it applies to every agent in the application.
- After every run the owner checks what changed with git status.

## How to create or restore an agent

1. In the agent application create a new agent with the exact name from the table.
2. Paste the complete text of its file as the first message.
3. The agent must answer READY followed by its numbered summary. If it answers anything else, discard the agent and create it again.
4. Never paste a changed rule into a chat. Change the file in this folder, raise its version, add a line to CHANGELOG.md, and paste the new file.

## Tickets as files

All work is passed through files in the tickets folder (see PART L in each agent file). The owner writes tickets/ID.txt (template: tickets/TEMPLATE.txt, check with python3 -m engine ticket tickets/ID.txt). Amilus writes the handoffs and the report, Ali the delivery files, Lili the audit files. Round files are written once and never overwritten. In the agent application the owner only sends one short line: PROCESS ID, APPROVE ID or CONTINUE ID. Chat text never replaces a file.

## Connection between the application and the project

The files in agents/ are the live definitions. At the start of every ticket each agent reads its own file with cat and follows it; if its chat copy differs, the file wins. Amilus also runs python3 -m engine agents, which compares the three files with agents/SHA256SUMS and reports OK or MISMATCH. When a role file changes, regenerate agents/SHA256SUMS in the same change.

## From content to PDF

1. The owner writes the ticket file in the project and sends PROCESS ID to Amilus; after the plan the owner sends APPROVE ID.
2. Amilus runs python3 -m engine agents and python3 -m engine ticket, then writes the handoff file for Ali.
3. Ali writes content.md and the assets of the document folder and runs python3 -m engine check on it.
4. Amilus runs check, build and verify, and sends the PDF, manifest and content to Lili.
5. Lili reports findings; Ali fixes them; Amilus rebuilds; at most three rounds.
6. The owner reviews. A draft goes to the Drafts folder with python3 -m engine deliver draft PATH. A release needs a file RELEASE_APPROVAL.txt in the document folder with the line APPROVED followed by the SHA-256 of that exact PDF, then python3 -m engine deliver release PATH. Both are run by the owner.

## Message protocol

Every message between agents carries a ticket id, sender, receiver, sequence number and type. The formats of the handoffs and reports are defined in the three files. Amilus rejects any delivery or report that does not follow its format.

## Not built yet

- Agents that run inside the engine or the future desktop product.
- A gate command and JSON output in the engine; until then Amilus follows the steps in agents/amilus.txt by hand.
- Any claim that the agents are tested beyond the limited trials recorded in TEST_LOG.md.
