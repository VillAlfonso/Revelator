# OpenAI response format change - 2026-10-17

Only these existing files were changed:
- backend/app/forgery/openai_vision.py
- backend/tests/test_intercept_openai.py

Changes: strict JSON response schema, exact field types and confidence range, category enum, field-specific format errors, explicit incomplete/refusal errors. No extra API calls, no semantic consistency check, no frontend or Gemini changes.

The .bak files contain the exact pre-change bytes. To undo only this update, compare current hashes with after_sha256 in manifest.json first. If they match, restore each .bak to the corresponding file. If they differ, preserve later edits and reverse only this update. Restart the backend normally after restoring. No server was launched or restarted by this update.
