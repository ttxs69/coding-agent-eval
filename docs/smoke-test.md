# Smoke Test

Manual end-to-end check before tagging a release. Not run in CI.

## Steps

1. Import one SWE-bench Verified task (no network-heavy repo fetch — use `--no-fetch-repo` for the smoke test):

   ```
   cae add-task --from-swebench --instance-id django__django-12345 --no-fetch-repo
   ```

2. List available agents:

   ```
   cae list-agents
   ```

3. Run the mock adapter against the imported task to verify the harness + importer round-trip:

   ```
   cae run --agent mock --task django__django-12345
   cat results/<run_id>.json
   ```

   Expected: result JSON with `status` in `{resolved, failed, agent_error, ...}` and a non-empty `test_results` block.

4. (Optional) Run a real agent — Claude Code, Codex, or Aider — on the same task. Requires the CLI to be installed and an API key in the env.

## What this catches

- Importer fields map correctly to harness expectations.
- Workdir setup, test patch application, pre-flight, and grading all work on a real task.
- Result JSON is valid and contains all required fields.
