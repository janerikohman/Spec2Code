╔════════════════════════════════════════════════════════════════════════════╗
║          🏗️  AGENT ARCHITECTURE UPDATE: AUTONOMOUS DECISION MAKING           ║
║                   (Bitbucket + Confluence Model)                            ║
╚════════════════════════════════════════════════════════════════════════════╝

## What Changed

The v2.0 agent system now implements **true autonomous decision-making** with clear 
role-based tool access. This replaces the previous "prescriptive orchestration" model 
where agents followed step-by-step instructions.

---

## Core Principle

✅ **CORRECT**: Epic specifies BUSINESS NEEDS → Agents autonomously solve using only 
   available tools → No prescriptive direction

❌ **INCORRECT** (Old model): Epic specifies TECHNICAL DECISIONS → Agents implement 
   as told → No autonomy


---

## Agent Roles & Tool Access (Role-Based Access Control)

### 1️⃣ **PO Requirements Agent** 
**Role:** Requirements Validator (NOT Technical Decision-Maker)

**Mission:**
- Ask clarifying questions about epic business goals, scope, acceptance criteria
- Ensure requirements are unambiguous and implementable
- Do NOT prescribe technical solutions, frameworks, or tools

**Tool Access:**
- ✅ Jira API: Read epic details, POST clarification questions in comments
- ❌ Confluence, Bitbucket, Azure APIs, CI/CD systems
- ❌ Cannot invoke other agents (Orchestrator decides sequencing)

**Definition Of Done:**
- All acceptance criteria are testable and measurable
- Business goal is clear
- Scope (in/out) is explicit
- No open questions remain unanswered

---

### 2️⃣ **Architect Agent**
**Role:** Autonomous Solution Designer

**Mission:**
- Autonomously select technology stack (framework, storage, hosting)
- Design system architecture based on requirements & constraints
- Create detailed design documentation in Confluence
- Document key decisions with ADRs (Architecture Decision Records)

**Tool Access:**
- ✅ Jira API: Read epics/stories, write design summaries
- ✅ Confluence API: Write/update design docs, ADRs, architecture pages
- ✅ Bitbucket API: Read-only (understand existing tech patterns)
- ❌ Code implementation, CI/CD execution, Azure deployment

**Autonomy Model:**
- Evaluates multiple tech stack options (React vs Vue vs vanilla JS, etc.)
- Selects best fit based on requirements (cost, complexity, team expertise)
- May request feedback from Security & DevOps for informational purposes ONLY
- Feedback is NOT an approval gate - Architect owns final decision
- Posts decision rationale in Confluence for transparency

**Example Decision:**
```
Architect's Autonomous Choice:
- Frontend: React 18 (rationale: ecosystem maturity, developer availability)
- Storage: localStorage MVP (rationale: zero cost, simpler deployment, 
  documented migration path to backend)
- Hosting: Azure Static Web Apps (rationale: free tier meets budget, 
  auto-scaling, no ops overhead)
- CI/CD: Bitbucket Pipelines (company standard)

All documented in Confluence. Developer/DevOps use this as input, not direction.
```

---

### 3️⃣ **Security Architect Agent**
**Role:** Security Requirements Analyzer

**Mission:**
- Analyze proposed architecture for security risks
- Define security requirements & controls
- Document threat model and mitigations in Confluence
- Create implementation requirements for Developer

**Tool Access:**
- ✅ Jira API: Read/write comments
- ✅ Confluence API: Write security docs, threat models, requirements
- ❌ Code implementation, infrastructure deployment
- ℹ️ Feedback role: Informs Architect & Developer, not approval gate

---

### 4️⃣ **DevOps/IaC Agent**
**Role:** Autonomous Infrastructure Architect

**Mission:**
- Propose Azure infrastructure based on Architect's tech stack choice
- Design deployment pipeline (Bitbucket Pipelines → Azure)
- Create Infrastructure-as-Code (Bicep) templates
- Design CI/CD workflow

**Tool Access:**
- ✅ Jira API: Read/write comments
- ✅ Confluence API: Write deployment architecture
- ✅ Bitbucket API: Write Bicep code, create bitbucket-pipelines.yml
- ✅ Azure APIs: Read-only (validate available SKUs, costs)
- ❌ Azure deployment execution (that's deployment phase, not planning)

**Autonomy Model:**
- Given Architect's choice (e.g., React + localStorage)
- Evaluates infrastructure options aligned with architect's constraints
- Creates IaC + pipeline configuration
- Does NOT need DevOps Manager approval to finalize design

---

### 5️⃣ **Developer Agent**
**Role:** Autonomous Implementation Planner

**Mission:**
- Read Architect's design + Security's requirements
- Break down into implementation stories with acceptance criteria
- Estimate effort and create story points
- Define code structure & tech implementation approach
- Document any implementation risks or blockers

**Tool Access:**
- ✅ Jira API: Read/write stories and comments
- ✅ Confluence API: Read architecture, write implementation plan
- ✅ Bitbucket API: Read code patterns, discuss approach
- ❌ Code implementation (during planning phase)
- ❌ Azure deployment

**Autonomy Model:**
- Given Architect's tech stack and Security's requirements
- Developer autonomously decides:
  - Story breakdown and story points
  - Component structure (how to organize React components)
  - State management approach (Context API, Redux, Zustand, etc.)
  - Testing framework and approach
  - Development workflow (branching strategy, PR process)

---

### 6️⃣ **QA/Tester Agent**
**Role:** Autonomous Test Strategy Designer

**Mission:**
- Read epic acceptance criteria
- Read Developer's implementation plan
- Design comprehensive test strategy (unit, integration, E2E, manual)
- Define test coverage targets and quality gates
- Create test case matrix

**Tool Access:**
- ✅ Jira API: Read/write test plan
- ✅ Confluence API: Write test strategy docs
- ❌ Code implementation
- ❌ Test execution (during validation phase, not planning phase)

**Autonomy Model:**
- QA autonomously decides:
  - Which acceptance criteria need which test types
  - Coverage targets (85%, 90%, etc.)
  - Testing tools (Jest vs Vitest, Cypress vs Playwright, etc.)
  - Browser/device testing matrix
  - Performance benchmarks

---

### 7️⃣ **FinOps Agent**
**Role:** Cost Validator

**Mission:**
- Analyze infrastructure proposal against cost targets
- Create cost projections (monthly, annual)
- Identify optimization opportunities

**Tool Access:**
- ✅ Jira API: Read/write cost analysis
- ✅ Confluence API: Write cost breakdown
- ✅ Azure APIs: Read-only (pricing information)
- ❌ Azure deployment, infrastructure changes

---

### 8️⃣ **Release Manager Agent**
**Role:** Final Gate Verifier

**Mission:**
- Verify all prior agents' work meets DoR (Definition of Ready)
- Make final Go/No-Go decision
- Document release approach and next steps

**Tool Access:**
- ✅ Jira API: Read all prior work, write final gate decision
- ✅ Confluence API: Read all documentation
- ❌ Code, infrastructure, deployment

---

## What Epic Should Specify

### ✅ Business Requirements (PO's Job)
```
• Business goal: "Simple shopping list app to help busy families organize 
  household shopping"
• Personas: Busy parent, household shopper, budget-conscious org
• Acceptance criteria: Create list, add items, edit items, delete items, 
  persist data, responsive UI
• NFRs: <3s load time, works on mobile, secure input handling
• Constraints: Cost <$10/month, simple to use, easy deployment
```

### ❌ Technical Decisions (Epic Should NOT Specify)
```
• ❌ "Use React + Tailwind CSS" → Architect decides framework
• ❌ "Deploy to Azure App Service" → Architect & DevOps decide hosting
• ❌ "Use GitHub Actions" → DevOps decides CI/CD (we use Bitbucket Pipelines)
• ❌ "Implement with Node.js + PostgreSQL" → Architecture is autonomous choice
• ❌ "Use Jest for testing" → Developer & QA decide test tooling
```

---

## Documentation Flow (Bitbucket + Confluence)

### During Planning Phase (Days 1-2)

1. **Epic created in Jira** with business requirements only
2. **Architect** writes design doc in Confluence:
   - Architecture Decision Records (ADRs)
   - Component diagrams
   - Tech stack rationale
   
3. **Security Architect** writes in Confluence:
   - Threat model
   - Required security controls
   - Implementation security requirements
   
4. **DevOps** writes in Confluence:
   - Infrastructure architecture
   - Deployment workflow
   - Bitbucket Pipelines configuration (committed to repo)
   
5. **Developer** writes in Jira:
   - Implementation stories (story points, acceptance criteria)
   
6. **QA** writes in Confluence:
   - Test strategy
   - Test case matrix
   - Quality gates

### During Implementation Phase (Days 3-12)

- **Developer** commits code to Bitbucket
- **Bitbucket Pipelines** auto-runs on every push
- **QA** executes tests and documents results in Confluence
- **FinOps** monitors actual costs vs. projection

### During Release Phase (Day 13-14)

- **Release Manager** verifies all gates pass
- Deploy to production via Bitbucket Pipelines → Azure

---

## Key Changes from Old Model

| Aspect | Old Model | New Model |
|--------|-----------|-----------|
| **PO Role** | Prescriptive trainer | Requirements validator |
| **Architect** | Follows direction from PO | Autonomous tech stack decisions |
| **Agent Inter-Comm** | Orchestrator invokes agents in sequence | Agents work in parallel, feedback is optional |
| **Tool Access** | All agents have all tools (no RBAC) | **Role-based access control** |
| **Code Repository** | GitHub (references in old docs) | **Bitbucket** (company standard) |
| **CI/CD Pipeline** | GitHub Actions | **Bitbucket Pipelines** |
| **Documentation** | Scattered across tools | **Confluence as primary doc hub** |
| **Approval Gates** | Multiple agents must "approve" | Orchestrator verifies DoR (Definition of Ready) |

---

## Example: Shopping List Epic

### Epic Specification (Business Only)

```
TITLE: Simple Shopping List Application

BUSINESS GOAL:
Provide users with a simple, intuitive web app to manage household shopping lists.

PERSONAS:
- Busy parent managing grocery runs
- Household shopper planning meals
- Budget-conscious organization evaluating costs

ACCEPTANCE CRITERIA:
✓ Create new shopping list with name
✓ Add items to list (name, quantity, optional category)
✓ Edit item details
✓ Delete items
✓ Persist data across browser sessions
✓ Mobile-friendly responsive UI
✓ Works on Chrome, Firefox, Safari

NFRs:
✓ Page load time <3 seconds
✓ Add item operation <500ms
✓ HTTPS by default
✓ Input validation & XSS prevention

CONSTRAINTS:
✓ Must cost <$10/month on Azure
✓ MVP mindset (no auth, no multi-user sync)
✓ Launch ready in 2 weeks

ARCHITECTURE: [INTENTIONALLY BLANK - Let Architect Decide]
```

### What Architect Will Decide (Autonomously)

**Option A** (Most Likely):
- React 18 + Tailwind CSS
- Browser localStorage
- Azure Static Web Apps
- Bitbucket Pipelines

**Option B** (Also Valid):
- Vue 3 + Bootstrap
- Backend Node.js + Azure Cosmos DB
- Azure App Service
- Bitbucket Pipelines

**Architect picks the best fit for the constraints**, documents why, and 
Dev/QA/DevOps execute from there.

---

## New System Instructions Files (Updated)

✅ **po-requirements-agent/system-instructions.md**
- Removed: Technical direction, invoke_agent() calls
- Added: Tool access constraints, pure validator role

✅ **architect-agent/system-instructions.md**
- Removed: Approval gates from other agents
- Changed: Feedback is informational, not blocking
- Added: Tool access (Jira, Confluence, Bitbucket read-only)

✅ **SHOPPING_LIST_EPIC.md**
- Removed: "React/Vue", "App Service", "GitHub Actions"
- Added: "Architecture to be determined by Architect Agent"

✅ **SHOPPING_LIST_ORCHESTRATION_EXPECTATIONS.md**
- Changed: "Framework: React decided" → "Architect evaluates options"
- Changed: "GitHub Actions" → "Bitbucket Pipelines"
- Changed: "Feedback from other agents" → "Feedback is optional/informational"

---

## Next Steps

1. ✅ Verify shopping list epic has NO technical prescriptions
2. ✅ Post epic to Jira (will get KAN-XXX key)
3. ✅ Execute orchestration: `orchestrator.run_all_epics(["KAN-XXX"])`
4. ✅ Observe: Each agent autonomously investigates epic → outputs plan
5. ✅ Verify: All 9 agent outputs reflect autonomous decision-making

---

## Key Principle Checklist

Before posting ep epic, verify:

- [ ] Epic specifies WHAT to build (acceptance criteria)
- [ ] Epic specifies WHY (business goal, personas)
- [ ] Epic specifies CONSTRAINTS (cost, timeline, non-functionals)
- [ ] Epic does NOT specify HOW (no "use React", "use Azure SQL", etc.)
- [ ] Epic does NOT give step-by-step instructions
- [ ] Agents have role-specific tool access (not all-access)
- [ ] No agent invokes another agent for "approval" (feedback only)
- [ ] Documentation goes to Confluence (not lost in Jira)
- [ ] CI/CD uses Bitbucket Pipelines (not GitHub Actions)

✅ If all checkboxes pass → Epic is ready for autonomous orchestration!
