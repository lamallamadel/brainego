# Codex Prompt & Instructions Complete Guide

This folder contains everything needed to configure and use Codex with the brainego project.

---

## 📄 Files Overview

### 1. **CODEX_DIRECT_PROMPT.md** ⭐ START HERE
**Purpose:** The actual system prompt to paste into Codex  
**Length:** ~2,000 words  
**Who:** Use this for direct Codex configuration  
**Action:** Copy → Paste into Codex workspace → Save

**Contains:**
- Hard rules (Docker, branching, testing)
- Code patterns to follow
- Common tasks
- Troubleshooting
- Pre-PR checklist

---

### 2. **CODEX_SYSTEM_PROMPT_CONCISE.md**
**Purpose:** Shorter version of the system prompt (if full version is too long)  
**Length:** ~1,500 words  
**Who:** Use if Codex has character/token limits  
**Action:** Alternative to CODEX_DIRECT_PROMPT.md

**Contains:**
- Same hard rules (condensed)
- Essential patterns only
- Quick reference
- Workflow in 8 steps

---

### 3. **CODEX_SYSTEM_PROMPT.md**
**Purpose:** Detailed, comprehensive guide (reference material)  
**Length:** ~8,000 words  
**Who:** Read for deep understanding  
**Action:** Share with team for onboarding

**Contains:**
- Detailed architecture context
- Full code patterns with examples
- Testing requirements explained
- Common tasks with full examples
- Resource links
- Final rules summary

---

### 4. **CODEX_SETUP_GUIDE.md**
**Purpose:** How to configure Codex (practical steps)  
**Length:** ~2,500 words  
**Who:** Person setting up Codex in the workspace  
**Action:** Follow the steps to configure

**Contains:**
- 4 configuration options (Web UI, Git, Team, API)
- How to verify it's working
- Troubleshooting
- Update strategy
- Readiness checklist

---

### 5. **CODEX_INSTRUCTIONS.md**
**Purpose:** Project-specific rules (already in repo)  
**Length:** ~5,000 words  
**Who:** Codex reads this; team references  
**Action:** Linked from CODEX_DIRECT_PROMPT.md

**Contains:**
- brainego architecture details
- Project context
- Rules specific to this repo
- Example tasks

---

## 🚀 Quick Start (5 Minutes)

### Step 1: Choose Your Configuration
- **Option A (Easiest):** Codex Web UI → Paste prompt into System Instructions
- **Option B (GitHub):** Create `.codex/instructions.txt` with the prompt
- **Option C (Team):** Host on internal wiki + link in README

### Step 2: Configure
1. Open `CODEX_DIRECT_PROMPT.md`
2. Copy the entire content
3. Paste into your Codex workspace
4. Save

### Step 3: Test
Ask Codex: **"I want to add a feature to brainego. What should I do first?"**

**Expected response:** Codex should mention creating a `feature/codex/*` branch

---

## 📖 Reading Order

**For Codex Setup Person:**
1. This file (overview)
2. `CODEX_SETUP_GUIDE.md` (how to configure)
3. `CODEX_DIRECT_PROMPT.md` (what to paste)

**For Developers Using Codex:**
1. `CODEX_INSTRUCTIONS.md` (rules + patterns)
2. `CODEX_DIRECT_PROMPT.md` (quick reference)
3. This file (if questions)

**For Team Leads/Managers:**
1. This file (overview)
2. `CODEX_SYSTEM_PROMPT.md` (comprehensive guide)
3. `CODEX_SETUP_GUIDE.md` (team setup section)

---

## 🎯 Key Points

### The 5 Hard Rules

1. **No Local Docker**
   - Codex Cloud has no Docker daemon
   - All builds happen in GitHub Actions via Docker Build Cloud
   - All tests use Testcontainers Cloud

2. **Branch Pattern: `feature/codex/*`**
   - Always create branches with this prefix
   - GitHub Actions auto-triggers on this pattern
   - Never commit directly to `main`

3. **Tests Mandatory**
   - Unit tests in `tests/unit/`
   - Integration tests in `tests/integration/`
   - No tests = PR rejected

4. **Type Hints & Docstrings**
   - Every function: `def func(x: str) -> dict:`
   - Every class/function has a docstring
   - Keep functions small (max 50 lines)

5. **Dependencies**
   - Update `requirements.txt` with exact versions
   - Never use `latest`

### The 3-Step Workflow

```
1. Create branch: git checkout -b feature/codex/your-feature
2. Write code + tests (follow patterns)
3. Push: git push origin feature/codex/your-feature
4. GitHub Actions runs automatically (5-10 min)
   → Results in PR
```

---

## ✅ Verification Checklist

After configuring Codex, verify:

- [ ] Codex mentions `feature/codex/*` branching
- [ ] Codex generates unit + integration tests
- [ ] Codex adds type hints to functions
- [ ] Codex never suggests `docker run`
- [ ] Codex updates `requirements.txt`
- [ ] Codex follows code patterns (FastAPI, services, etc.)

---

## 🔄 Update Strategy

### When to Update Instructions

- Monthly: Review and update based on team feedback
- Quarterly: Major pattern/architecture changes
- As-needed: New tools or significant workflow changes

### How to Update

1. Edit `CODEX_DIRECT_PROMPT.md`
2. Test changes with Codex
3. Commit: `git commit -m "Update Codex instructions: add new pattern"`
4. Push to `main`
5. Notify team in Slack/Discord

---

## 🆘 Common Issues

### "Codex suggests `docker run`"
→ Re-apply instructions; emphasize "NO Docker" in all caps

### "Codex creates PR to `main`"
→ Add explicit instruction: "ALWAYS start: `git checkout -b feature/codex/...`"

### "Codex doesn't include tests"
→ Add in prompt: "Every generated file MUST have corresponding tests"

### "Instructions too long"
→ Use `CODEX_SYSTEM_PROMPT_CONCISE.md` instead

---

## 📚 Files in This Project

```
brainego/
├── CODEX_DIRECT_PROMPT.md              ← Copy this into Codex
├── CODEX_SYSTEM_PROMPT_CONCISE.md      ← Alternative (shorter)
├── CODEX_SYSTEM_PROMPT.md              ← Detailed reference
├── CODEX_SETUP_GUIDE.md                ← How to configure
├── CODEX_INSTRUCTIONS.md               ← Project-specific rules
├── CODEX_PROMPTS_OVERVIEW.md           ← This file
│
├── .github/workflows/
│   └── codex-build.yml                 ← CI/CD pipeline
│
├── tests/
│   ├── conftest.py
│   ├── unit/
│   └── integration/
│
├── QUICKSTART.md
├── GITHUB_ACTIONS_SETUP.md
├── CI_CD_SUMMARY.md
└── SETUP_COMPLETE.md
```

---

## 🎓 Training New Team Members

### Day 1: Onboarding
1. Share this file
2. Share `CODEX_INSTRUCTIONS.md`
3. Show them `CODEX_DIRECT_PROMPT.md`

### Day 2: First Task
1. Ask them to create `feature/codex/test` branch
2. Have Codex generate a simple endpoint
3. Review output against checklist
4. Walk through PR process

### Day 3: Real Work
- Let them use Codex independently
- Review PRs and provide feedback
- Reinforce rules as needed

---

## 💡 Tips for Success

### For Managers
- Set expectations: "All Codex-generated code must follow these rules"
- Review PRs consistently
- Celebrate good Codex usage

### For Developers
- Read `CODEX_INSTRUCTIONS.md` before using Codex
- Test generated code locally first
- Ask Codex to explain its reasoning

### For Codex
- Be specific: "Add a RAG search endpoint with full tests"
- Not vague: "Add something to the API"
- Follow all 5 hard rules
- Ask for clarification if unsure

---

## 🔗 Related Documents

| Document | Purpose |
|----------|---------|
| `CODEX_DIRECT_PROMPT.md` | System prompt (copy to Codex) |
| `CODEX_INSTRUCTIONS.md` | Project rules & patterns |
| `CODEX_SYSTEM_PROMPT.md` | Detailed guide (reference) |
| `CODEX_SETUP_GUIDE.md` | Configuration instructions |
| `.github/workflows/codex-build.yml` | CI/CD pipeline |
| `QUICKSTART.md` | 5-minute setup |
| `GITHUB_ACTIONS_SETUP.md` | CI technical details |

---

## ❓ FAQ

**Q: Do I need to read all of these files?**
A: No. Start with `CODEX_SETUP_GUIDE.md` to configure, then use `CODEX_INSTRUCTIONS.md` for reference.

**Q: Which file do I paste into Codex?**
A: `CODEX_DIRECT_PROMPT.md` (or `CODEX_SYSTEM_PROMPT_CONCISE.md` if too long)

**Q: Can I modify the instructions?**
A: Yes, but keep the 5 hard rules intact.

**Q: How often should I update?**
A: Monthly review recommended; update as needed.

**Q: What if Codex doesn't follow the rules?**
A: Re-apply instructions or rephrase them more clearly.

---

## 🎉 Success Criteria

You've successfully set up Codex when:

✅ Instructions are configured  
✅ Codex generates code with `feature/codex/*` branches  
✅ All generated code includes tests  
✅ All generated code has type hints  
✅ CI/CD pipeline validates everything  
✅ Team knows how to use Codex  
✅ PRs are being generated and merged  

---

## 🚀 Next Steps

1. **Right now:** Read `CODEX_SETUP_GUIDE.md`
2. **Today:** Configure Codex with `CODEX_DIRECT_PROMPT.md`
3. **Tomorrow:** Test with a team member
4. **This week:** Generate your first feature
5. **Ongoing:** Review and refine

---

**Questions? Issues? Refer to the relevant document above or ask your team lead.**

**Happy coding with Codex! 🚀**
