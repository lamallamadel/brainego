# How to Configure Codex with System Instructions

This guide shows you how to add the system prompt to Codex so it automatically follows all the rules.

---

## Option 1: Codex Web Interface (OpenAI Platform)

### Step 1: Go to Codex Settings
1. Visit: https://platform.openai.com/codex (or your Codex Cloud workspace)
2. Find "System Instructions" or "Instructions" section
3. Copy the entire content from `CODEX_DIRECT_PROMPT.md`

### Step 2: Paste Instructions
1. Click **Edit System Instructions** or **Configure**
2. Paste the full prompt
3. Click **Save** or **Apply**

### Step 3: Test
1. Start a new session
2. Ask Codex: "Create a new feature branch for brainego"
3. Verify it suggests: `feature/codex/...` pattern

---

## Option 2: Git-Based Configuration (If Using GitHub Codespaces)

### Create `.codex/instructions.txt`

```bash
mkdir -p .codex
cat > .codex/instructions.txt << 'EOF'
[Paste content from CODEX_DIRECT_PROMPT.md here]
EOF
```

### Add to `.gitignore` (Optional)
```bash
# .gitignore
# Keep local instructions, don't commit
# .codex/instructions.txt
```

### Configure Workspace
- GitHub Codespaces can read from `.codex/instructions.txt`
- On startup, Codex loads these instructions automatically

---

## Option 3: Team/Organization Setup

If your organization manages Codex instances centrally:

### 1. Store Instructions in Shared Location
- Confluence: Create a page with the prompt
- GitHub Wiki: `your-org/brainego/wiki/Codex-Instructions`
- Internal docs: Link in README.md

### 2. Reference in Codex
When initiating a Codex session, include:
```
Use the instructions from: https://your-wiki/codex-instructions
```

### 3. Update Frequency
- Keep `CODEX_DIRECT_PROMPT.md` updated in the repo
- Team reviews it monthly
- Push changes to all Codex instances

---

## Option 4: Programmatic (If Using OpenAI API)

If you're calling Codex via API:

```python
import openai

system_prompt = open("CODEX_DIRECT_PROMPT.md").read()

response = openai.ChatCompletion.create(
    model="gpt-4",  # or Codex model
    messages=[
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "Create a new RAG endpoint"}
    ]
)

print(response.choices[0].message.content)
```

---

## How to Use: Step-by-Step

### When Starting a Codex Session

1. **Load instructions** (automated if configured)
2. **Tell Codex what to build:**
   ```
   "Create a new endpoint for searching documents with RAG.
    Include unit tests and integration tests."
   ```
3. **Codex generates code** following all system rules:
   - ✅ Creates `feature/codex/...` branch
   - ✅ Includes tests
   - ✅ Adds type hints & docstrings
   - ✅ Updates requirements.txt
4. **Review the output**
5. **Push to GitHub** — CI/CD runs automatically

---

## Example: Codex Session Transcript

**You:** "I want to add a memory service that stores conversations in Redis. Include tests."

**Codex:** 
```
I'll create a memory service for brainego using Redis.
Following the system instructions:

1. Creating feature branch: feature/codex/add-memory-service
2. Code pattern: Service class with async methods
3. Tests: Unit tests (mocked Redis) + Integration tests (Testcontainers)
4. Type hints & docstrings: Yes
5. Updating requirements.txt: Yes

Here's the implementation:

## File: memory_service.py
[generates service code with docstrings and type hints]

## File: tests/unit/test_memory_service.py
[generates unit tests with mocks]

## File: tests/integration/test_memory_service.py
[generates integration tests with Testcontainers]

## Updated: requirements.txt
[shows what to add]

Next steps:
1. git checkout -b feature/codex/add-memory-service
2. Copy the code above to your files
3. git push origin feature/codex/add-memory-service
4. GitHub Actions will run your tests automatically
```

---

## Verifying Instructions Are Working

After configuration, ask Codex these questions to verify:

**Test 1: Branch Naming**
- **Ask:** "Create a simple Flask app"
- **Expected:** Codex should mention `feature/codex/...` branch

**Test 2: Test Requirements**
- **Ask:** "Add a new endpoint"
- **Expected:** Codex should generate unit + integration tests

**Test 3: Type Hints**
- **Ask:** "Write a function to fetch user data"
- **Expected:** All functions have type hints like `-> dict:`

**Test 4: No Docker**
- **Ask:** "How do I test this locally?"
- **Expected:** Codex should say "Tests run in GitHub Actions"

---

## Updating Instructions Over Time

As your project evolves:

1. **Update `CODEX_DIRECT_PROMPT.md`** in the repo
2. **Update the instructions** in your Codex workspace
3. **Notify the team** if rules changed
4. **Document why** (in commit message)

Example commit:
```
git commit -m "Update Codex instructions: add LoRA training pattern"
```

---

## Troubleshooting

### "Codex doesn't follow the type hints rule"
- **Fix:** Re-apply instructions in Codex workspace
- **Check:** Instructions are fully copied (not truncated)

### "Codex suggests using docker"
- **Fix:** Emphasize in prompt: "You have NO access to Docker"
- **Add:** Specific examples of what NOT to do

### "Codex creates PR to main instead of feature branch"
- **Fix:** Add to instructions: "ALWAYS start with: git checkout -b feature/codex/..."
- **Test:** Ask test question to verify

### "Instructions are too long and Codex truncates"
- **Fix:** Use `CODEX_SYSTEM_PROMPT_CONCISE.md` (shorter version)
- **Split:** Into multiple prompts if needed

---

## Recommended Approach for brainego

### Quick Setup (Recommended)

1. Copy `CODEX_DIRECT_PROMPT.md` content
2. Paste into your Codex workspace → System Instructions
3. Save
4. Test with: "Create a feature branch for adding a new endpoint"
5. Verify output matches rules

### Team Setup

1. Add `CODEX_DIRECT_PROMPT.md` to repo (already done ✅)
2. Link in `README.md`: "See CODEX_DIRECT_PROMPT.md for Codex setup"
3. Document in onboarding: "Load instructions from CODEX_DIRECT_PROMPT.md"
4. Review monthly in sprint retrospectives

### Organization Setup

1. Host `CODEX_DIRECT_PROMPT.md` on internal wiki
2. Create CI/CD check: "Validate all code follows Codex rules"
3. Auto-comment on PRs: "Did you follow CODEX_DIRECT_PROMPT.md?"

---

## Checklist: Is Codex Ready?

- [ ] System instructions pasted into Codex workspace
- [ ] Codex generates code with `feature/codex/*` branches
- [ ] Codex includes tests in generated code
- [ ] Codex adds type hints to functions
- [ ] Codex never mentions `docker run` or `docker build`
- [ ] Codex updates `requirements.txt` when adding packages
- [ ] Codex follows code patterns (FastAPI, services, etc.)
- [ ] Team knows how to use Codex (shared in Slack/Discord)

---

## Questions?

If Codex doesn't follow a rule:

1. **Check:** Are instructions loaded? (test by asking directly)
2. **Verify:** Full prompt is pasted (no truncation)
3. **Update:** Rephrase the rule more clearly
4. **Test:** Ask specific test question
5. **Document:** Add example to `CODEX_DIRECT_PROMPT.md`

---

## Final Summary

✅ **Codex is ready to use** when:
- Instructions are configured
- Codex follows the 5 hard rules
- Team knows the workflow
- CI/CD validates all code

**Result:** Safe, productive, automated code generation! 🚀
