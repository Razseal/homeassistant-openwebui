# OpenWebUI (HACS) for Home Assistant

Custom integration that provides:
- **Conversation agent**: routes Assist to OpenWebUI (optionally with RAG collections)
- **AI Task entity**: use with `ai_task.generate_data` in automations

## Setup
1. Add this private repo to HACS (Custom repositories → Integration).
2. Install → Restart Home Assistant.
3. Add integration: **OpenWebUI**.
4. Configure Base URL, API Key, default model, optional collection IDs.

## Notes
- RAG: supply comma-separated collection IDs; the integration adds them as `files` on every request.
- Attachments: planned (upload to `/api/v1/files/` then include file IDs).
