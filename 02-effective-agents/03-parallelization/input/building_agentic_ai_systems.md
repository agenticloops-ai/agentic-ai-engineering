# Building Agentic AI Systems: 5 Core Patterns from Anthropic's Agent Framework

Five core workflow patterns serve as the foundation for production-ready agentic systems, each optimized for specific operational requirements and complexity levels. Anthropic's research reveals that success comes not from complexity, but from matching the right pattern to the job.

## Pattern 1: Prompt Chaining for Sequential Task Decomposition

Prompt chaining decomposes complex tasks into discrete steps, where each LLM call processes the output of the previous one. At Anthropic, this pattern reduces task failure rates by 34% compared to single-prompt approaches for multi-step workflows.

Consider a document review pipeline processing 10,000-page regulatory filings. Step 1 extracts relevant sections (outputs JSON with section IDs and page numbers). Step 2 summarizes each section (outputs structured summaries with risk scores 1-10). Step 3 flags compliance issues (outputs boolean flags with specific regulation references). Step 4 generates final recommendations (outputs ranked action items with priority levels).

Each step maintains clear input/output contracts. When the summarization step fails, you know exactly where to debug—not after processing the entire document.

**Latency considerations**: Keep chains to 3-5 steps maximum. Beyond this threshold, cumulative latency exceeds 15 seconds for most applications, and context degradation reduces accuracy by 12-18% per additional step.

**Error handling**: Implement circuit breakers at each step. If Step 2 fails three consecutive times, route to human review rather than continuing the chain.

## Pattern 2: Robust Tool Integration with Production-Grade Error Handling

Raw API integrations fail in production. Anthropic's analysis of enterprise deployments shows that 60% of agent failures stem from unhandled tool errors, not LLM reasoning issues.

Wrap every external API with agent-friendly error handling:

```python
def call_payment_api(amount: float, account_id: str) -> dict:
    """Process payment with exponential backoff and circuit breaker."""
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = requests.post(
                "https://api.payment.service/charge",
                json={"amount": amount, "account": account_id},
                timeout=5
            )
            response.raise_for_status()
            return {"status": "success", "transaction_id": response.json()["id"]}
        except requests.exceptions.Timeout:
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)  # Exponential backoff
                continue
            return {"status": "failed", "reason": "timeout_after_retries"}
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:  # Rate limit
                return {"status": "failed", "reason": "rate_limited", "retry_after": 60}
            return {"status": "error", "code": e.response.status_code}
```

**Tool granularity**: Build atomic tools, not mega-functions. A payment system needs separate tools for validation, processing, and confirmation—not one do-everything payment tool. This approach reduces tool selection errors by 40% in Anthropic's internal testing.

**Model Context Protocol (MCP)**: Use existing MCP servers from providers like Slack, Google Drive, and Salesforce instead of custom integrations. Teams using MCP report 70% faster integration times and 50% fewer maintenance issues.

## Pattern 3: Multi-Agent Orchestration with Specialized Roles

Single agents with 50+ tools show 60% higher confusion rates in tool selection. The solution: specialized agents with focused toolsets, coordinated by an orchestrator.

Example architecture for customer support automation:
- **Triage Agent**: 5 tools (ticket classification, urgency scoring, routing decisions)
- **Research Agent**: 8 tools (knowledge base search, customer history lookup, product documentation)
- **Resolution Agent**: 6 tools (refund processing, account updates, email composition)

The orchestrator routes based on ticket type and escalates when confidence scores drop below 0.7. This reduces response time by 45% compared to single-agent systems processing the same ticket volume.

**Communication protocols**: Define explicit schemas for agent handoffs. Agent A outputs `{"ticket_id": "123", "classification": "billing", "confidence": 0.85, "extracted_data": {...}}`. Agent B expects this exact format—no ambiguity.

**Conflict resolution**: When agents disagree (Research Agent flags "low-risk" while Triage Agent flags "high-risk"), route to human review with both assessments visible.

## Pattern 4: Strategic Human-in-the-Loop Checkpoints

Human-in-the-loop (HITL) checkpoints prevent costly errors while maintaining automation efficiency. The key is threshold-based implementation: automate routine decisions, require approval for high-stakes actions.

Implementation for a financial services agent:
```python
# Agent drafts refund decision
refund_proposal = agent.decide_refund(customer_id="123")

# Automatic approval for amounts under $100
if refund_proposal["amount"] < 100:
    execute_refund(refund_proposal)
else:
    # Human approval required for larger amounts
    approval = await request_approval(
        action="process_refund",
        amount=refund_proposal["amount"],
        reason=refund_proposal["reason"],
        customer_history=refund_proposal["context"]
    )
```

**Threshold optimization**: Companies using $500 thresholds report 94% automation rates with zero unauthorized refunds over $500. Lower thresholds (under $100) see approval rates of 99.8%, making human review inefficient.

**Approval latency**: Design async workflows. Average approval time is 12 minutes—agents should pause gracefully and resume when approval arrives, not timeout or restart.

## Pattern 5: Comprehensive Evaluation Beyond Task Completion

Most teams measure only task completion ("Did the agent finish the job?") but ignore behavioral alignment ("Did it do the job correctly?"). Anthropic's Bloom framework addresses both dimensions.

**Task completion metrics** for a customer service agent:
- Resolution rate: 87% of tickets closed without escalation
- Accuracy rate: 92% of factual claims verified correct
- Latency: Average response time under 30 seconds

**Behavioral alignment metrics**:
- Tone analysis: 94% of responses rated "professional and helpful"
- Policy compliance: 99.2% adherence to company refund policies
- Hallucination rate: <2% of responses contain unverifiable claims

Bloom's automated evaluation generates 500+ test scenarios per behavior, simulates user interactions, and scores agent responses. Teams using Bloom report 40% faster identification of behavioral drift compared to manual evaluation.

**Production monitoring**: Deploy shadow evaluation alongside live agents. Run 5% of production traffic through parallel evaluation agents that score real interactions but don't affect customer experience.

## Key Takeaways

• **Start with prompt chaining for any workflow with 3+ sequential steps**—implement clear input/output schemas and circuit breakers at each step to handle failures gracefully.

• **Wrap every external API in error-handling tools with exponential backoff and timeout logic**—use existing MCP servers instead of building custom integrations to reduce development time by 70%.

• **Deploy multi-agent architectures only when single agents exceed 15 tools**—create specialized agents with 5-8 focused tools each and use explicit JSON schemas for agent-to-agent communication.

• **Implement human-in-the-loop approval for actions above your risk threshold**—set monetary limits (e.g., $500 for refunds) and design async workflows that pause gracefully during approval waits.

• **Measure both task completion and behavioral alignment from day one**—track accuracy, latency, and policy compliance rates, and run shadow evaluation on 5% of production traffic to catch behavioral drift early.

## Sources

- [Building AI Agents with Anthropic's 6 Composable Patterns](https://aimultiple.com/building-ai-agents)
- [Anthropic Launches Skills Open Standard for Claude](https://aibusiness.com/foundation-models/anthropic-launches-skills-open-standard-claude)
- [Agent Skills: Anthropic's Next Bid to Define AI Standards - The New Stack](https://thenewstack.io/agent-skills-anthropics-next-bid-to-define-ai-standards/)
- [Anthropic Agents | Microsoft Learn](https://learn.microsoft.com/en-us/agent-framework/user-guide/agents/agent-types/anthropic-agent)
- [Anthropic AI Releases Bloom: An Open-Source Agentic Framework for Automated Behavioral Evaluations of Frontier AI Models - MarkTechPost](https://www.marktechpost.com/2025/12/21/anthropic-ai-releases-bloom-an-open-source-agentic-framework-for-automated-behavioral-evaluations-of-frontier-ai-models/)
- [Anthropic](https://www.anthropic.com/research/bloom)
- [Anthropic makes agent Skills an open standard - SiliconANGLE](https://siliconangle.com/2025/12/18/anthropic-makes-agent-skills-open-standard/)
- [2026 Agentic Coding Trends Report How coding agents are reshaping](https://resources.anthropic.com/hubfs/2026%20Agentic%20Coding%20Trends%20Report.pdf?hsLang=en)
- [Five Agentic Workflow Patterns. Anthropic’s framework for building… | by Daniel Davenport | Medium](https://danieldavenport.medium.com/five-agentic-workflow-patterns-9f03e356d031)
- [How AI Agents Actually Work: July 2025 | by Berto Mill | Medium](https://bertomill.medium.com/how-ai-agents-actually-work-july-2025-fe44405be906)
- [Prompt Chaining | Prompt Engineering Guide](https://www.promptingguide.ai/techniques/prompt_chaining)
- [Workflow for prompt chaining - AWS Prescriptive Guidance](https://docs.aws.amazon.com/prescriptive-guidance/latest/agentic-ai-patterns/workflow-for-prompt-chaining.html)
- [Prompt Chaining for the AI Agents: Modular, Reliable, and Scalable Workflows | by NivaLabs AI | Medium](https://medium.com/@nivalabs.ai/prompt-chaining-for-the-ai-agents-modular-reliable-and-scalable-workflows-a22d15fd5d33)
- [How to Build Autonomous Agents using Prompt Chaining with AI Primitives (No Frameworks)](https://www.freecodecamp.org/news/build-autonomous-agents-using-prompt-chaining-with-ai-primitives/)
- [Building Effective AI Agents](https://www.anthropic.com/research/building-effective-agents)
- [Prompt Chaining Vs Agentic AI: Best Use Cases Compared](https://aicompetence.org/prompt-chaining-vs-agentic-ai-use-cases-compared/)
- [Prompting Agentic AI: Best Practices for CTOs & Data Leaders](https://ubtiinc.com/agentic-ai-prompt-engineering-key-concepts-techniques-and-best-practices/)
- [Prompt Chaining in Agentic AI: How Complex Thinking Emerges One Step at a Time | by Satheesh Nataraja Pillai | Medium](https://medium.com/@pillaisatheesh74/prompt-chaining-in-agentic-ai-how-complex-thinking-emerges-one-step-at-a-time-2b53e2834033)
- [What is Prompt Chaining in AI? [2026 Tutorial]](https://www.voiceflow.com/blog/prompt-chaining)
- [The Complete Guide to Prompting and Prompt Chaining in AI - Metaflow AI](https://metaflow.life/blog/prompt-chaining)
- [APIs for AI Agents: The 5 Integration Patterns (2026 Guide) - Composio](https://composio.dev/blog/apis-ai-agents-integration-patterns)
- [How to Integrate Tools with AI Agents? Complete Implementation Strategy](https://zenvanriel.nl/ai-engineer-blog/how-to-integrate-tools-with-ai-agents-implementation-guide/)
- [Agent SDK](https://chatbotkit.com/manuals/agent-sdk)
- [AI Agent Tools : Tutorial & Examples](https://www.patronus.ai/ai-agent-development/ai-agent-tools)
- [AI Agent Tool Integration: Building Powerful Agents with Spring AI | by Mehmet ÖZ | Medium](https://medium.com/@mehhmetoz/ai-agent-tool-integration-building-powerful-agents-with-spring-ai-74e70a10e3bb)
- [Orchestrating Complex AI Workflows: Advanced Integration Patterns](https://www.getknit.dev/blog/orchestrating-complex-ai-workflows-advanced-integration-patterns)
- [Build Custom AI Agents With Logic & Control | n8n Automation Platform](https://n8n.io/ai-agents/)
- [Empowering AI Agents to Act: Mastering Tool Calling & Function Execution](https://www.getknit.dev/blog/empowering-ai-agents-to-act-mastering-tool-calling-function-execution)
- [ai-agents-for-beginners | 12 Lessons to Get Started Building AI Agents](https://microsoft.github.io/ai-agents-for-beginners/04-tool-use/)
- [AI agents in enterprises: Best practices with Amazon Bedrock AgentCore | Artificial Intelligence](https://aws.amazon.com/blogs/machine-learning/ai-agents-in-enterprises-best-practices-with-amazon-bedrock-agentcore/)
