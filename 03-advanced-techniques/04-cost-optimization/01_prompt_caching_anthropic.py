"""
Prompt Caching (Anthropic)

Demonstrates prompt caching with a customer support agent that has a large
company policy document as the system prompt. The policy exceeds Anthropic's
1024-token minimum for caching, so repeated calls read from cache at 90% savings.

First call: cache MISS (cache_creation_input_tokens > 0)
Subsequent calls: cache HIT (cache_read_input_tokens > 0)
"""

from dataclasses import dataclass, field

import anthropic
from dotenv import find_dotenv, load_dotenv
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

from common import AnthropicTokenTracker, setup_logging

# Load environment variables from root .env file
load_dotenv(find_dotenv())

# Configure logging
logger = setup_logging(__name__)

# Model configuration
MODEL = "claude-sonnet-4-6"

# Anthropic pricing ($ per million tokens) — as of 2025
PRICING = {
    "input": 3.00,
    "output": 15.00,
    "cache_write": 3.75,  # 1.25x input
    "cache_read": 0.30,  # 0.1x input — the big win
}

# Large company policy document (~1200-1500 tokens) to ensure we exceed the
# 1024-token minimum required for prompt caching on Sonnet.
COMPANY_POLICY = """
# TechFlow Solutions — Customer Support Policy & FAQ

## Company Overview
TechFlow Solutions is a B2B SaaS company providing cloud-based project management,
team collaboration, and workflow automation tools. Founded in 2019, we serve over
15,000 business customers across 40 countries. Our product suite includes TechFlow
Pro (project management), TechFlow Connect (team messaging), and TechFlow Automate
(workflow builder).

## Return & Refund Policy

### Software Subscriptions
- All subscription plans include a 14-day free trial period with full feature access.
- Monthly subscriptions can be cancelled at any time; service continues until the
  end of the current billing cycle. No partial refunds for unused days.
- Annual subscriptions may be refunded within 30 days of purchase. After 30 days,
  the remaining balance is converted to account credit valid for 12 months.
- Enterprise contracts (50+ seats) follow custom terms outlined in the service
  agreement. Contact the enterprise team for modifications.

### Hardware & Accessories
- Physical products (TechFlow Hub devices, accessories) may be returned within
  30 days of delivery in original packaging for a full refund.
- Defective hardware is covered under warranty and replaced at no cost.
- Shipping costs for returns are covered by TechFlow for defective items only.

## Shipping & Delivery

### Digital Products
- Software licenses and subscription activations are delivered instantly via email.
- Enterprise deployments include a dedicated onboarding specialist and typically
  take 5-10 business days for full setup.

### Physical Products
- Standard Shipping (5-7 business days): Free for orders over $50, otherwise $7.99.
- Express Shipping (2-3 business days): $14.99.
- Next-Day Shipping (1 business day): $24.99 — available for US addresses only.
- International Shipping (7-14 business days): $19.99-$39.99 depending on region.
- All shipments include tracking. Signature required for orders over $200.

## Warranty Terms
- TechFlow Hub devices: 2-year manufacturer warranty covering defects in materials
  and workmanship. Does not cover physical damage, water damage, or unauthorized
  modifications.
- Software: Guaranteed 99.9% uptime SLA for Pro and Enterprise tiers. Basic tier
  does not include an SLA. Downtime credits are calculated at 10x the hourly cost
  for each hour below the SLA threshold.

## Account Management

### Plan Tiers
- **Basic** ($12/user/month): Core project management, 5GB storage, email support.
- **Pro** ($29/user/month): Advanced analytics, 50GB storage, priority support,
  API access, custom integrations.
- **Enterprise** ($49/user/month): Unlimited storage, dedicated account manager,
  SSO/SAML, audit logs, custom SLA, phone support.

### Upgrades & Downgrades
- Upgrades take effect immediately. The prorated difference is charged right away.
- Downgrades take effect at the next billing cycle. Features exclusive to the
  higher tier remain accessible until then.
- Data exceeding the lower tier's storage limit must be exported or deleted before
  the downgrade processes. Automated warnings are sent 7 days before.

### Billing
- Accepted payment methods: Visa, Mastercard, Amex, wire transfer (Enterprise only).
- Invoices are generated on the 1st of each month for annual plans, or on the
  subscription anniversary date for monthly plans.
- Failed payments are retried 3 times over 9 days. After the third failure, the
  account is suspended. Data is retained for 30 days after suspension.

## Frequently Asked Questions

1. **How do I reset my password?**
   Go to Settings > Security > Change Password, or use the "Forgot Password" link
   on the login page. A reset link is sent to your registered email.

2. **Can I transfer my license to another user?**
   Yes. Admins can reassign seats from the Team Management dashboard at no cost.
   The previous user loses access immediately upon reassignment.

3. **What integrations are available?**
   Pro and Enterprise plans support integrations with Slack, Jira, GitHub, GitLab,
   Salesforce, HubSpot, Zapier, and 200+ other tools via our API and Zapier
   connector.

4. **Is my data encrypted?**
   Yes. All data is encrypted at rest (AES-256) and in transit (TLS 1.3). Enterprise
   plans offer customer-managed encryption keys (BYOK).

5. **What happens to my data if I cancel?**
   Data is retained for 30 days after cancellation. You can export all data via
   Settings > Data Export at any time during this window. After 30 days, data is
   permanently deleted per our data retention policy.

6. **Do you offer educational or nonprofit discounts?**
   Yes. Verified educational institutions and registered nonprofits receive 40% off
   all plans. Apply through our website with valid documentation.

7. **How do I contact support?**
   - Basic: Email support (24-48 hour response time)
   - Pro: Priority email support (4-8 hour response time) + live chat
   - Enterprise: Dedicated account manager + phone support (1-hour response SLA)

8. **Can I get a demo before purchasing?**
   Yes. Book a personalized demo at techflow.com/demo or start a 14-day free trial
   instantly — no credit card required.

9. **What is your uptime guarantee?**
   Pro and Enterprise tiers include a 99.9% uptime SLA. Check real-time status at
   status.techflow.com.

10. **How do bulk licenses work?**
    Orders of 50+ seats qualify for Enterprise pricing with volume discounts.
    Contact sales@techflow.com for a custom quote.

## Escalation Procedures
- **Tier 1** (frontline agent): Handle general inquiries, password resets, billing
  questions, and standard troubleshooting.
- **Tier 2** (senior agent): Handle refund requests over $500, account suspensions,
  data recovery, and complex technical issues.
- **Tier 3** (engineering): Handle service outages, security incidents, API bugs,
  and infrastructure issues.
- Always attempt resolution at the current tier before escalating. Document all
  steps taken and customer communication before passing to the next tier.
""".strip()

SYSTEM_INSTRUCTIONS = (
    "You are a customer support agent for TechFlow Solutions. Use the company policy "
    "below to answer customer questions accurately. Be friendly, professional, and concise. "
    "If a question falls outside the policy, say so and suggest contacting the appropriate team. "
    "Always cite the relevant policy section when applicable."
)


@dataclass
class CacheMetrics:
    """Tracks cache performance across API calls."""

    call_count: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cache_write_tokens: int = 0
    total_cache_read_tokens: int = 0
    per_call_history: list[dict] = field(default_factory=list)

    def record_call(
        self,
        input_tokens: int,
        output_tokens: int,
        cache_write_tokens: int,
        cache_read_tokens: int,
    ) -> None:
        """Record metrics from a single API call."""
        self.call_count += 1
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens
        self.total_cache_write_tokens += cache_write_tokens
        self.total_cache_read_tokens += cache_read_tokens
        self.per_call_history.append(
            {
                "call": self.call_count,
                "input": input_tokens,
                "output": output_tokens,
                "cache_write": cache_write_tokens,
                "cache_read": cache_read_tokens,
            }
        )

    def cost_with_caching(self) -> float:
        """Calculate actual cost using cache pricing."""
        uncached_input = (
            self.total_input_tokens - self.total_cache_write_tokens - (self.total_cache_read_tokens)
        )
        return (
            uncached_input * PRICING["input"]
            + self.total_cache_write_tokens * PRICING["cache_write"]
            + self.total_cache_read_tokens * PRICING["cache_read"]
            + self.total_output_tokens * PRICING["output"]
        ) / 1_000_000

    def cost_without_caching(self) -> float:
        """Calculate hypothetical cost if all tokens were charged at base input rate."""
        return (
            self.total_input_tokens * PRICING["input"]
            + self.total_output_tokens * PRICING["output"]
        ) / 1_000_000

    def savings(self) -> float:
        """Dollar savings from caching."""
        return self.cost_without_caching() - self.cost_with_caching()

    def cache_hit_rate(self) -> float:
        """Percentage of cacheable tokens served from cache."""
        total_cache = self.total_cache_write_tokens + self.total_cache_read_tokens
        if total_cache == 0:
            return 0.0
        return (self.total_cache_read_tokens / total_cache) * 100


class CachedSupportAgent:
    """Customer support agent demonstrating prompt caching."""

    def __init__(
        self,
        model: str,
        token_tracker: AnthropicTokenTracker,
        use_cache: bool = True,
    ):
        self.client = anthropic.Anthropic()
        self.model = model
        self.token_tracker = token_tracker
        self.use_cache = use_cache
        self.messages: list[dict] = []
        self.metrics = CacheMetrics()

    def _build_system(self) -> str | list[dict]:
        """Build system prompt — with cache_control blocks or plain string."""
        if not self.use_cache:
            return f"{SYSTEM_INSTRUCTIONS}\n\n{COMPANY_POLICY}"

        # Explicit cache breakpoints: mark the large policy block for caching.
        # The instructions are short and change rarely, but the policy is the
        # bulk of the prompt — caching it saves ~90% on repeated calls.
        return [
            {"type": "text", "text": SYSTEM_INSTRUCTIONS},
            {
                "type": "text",
                "text": COMPANY_POLICY,
                "cache_control": {"type": "ephemeral"},  # cached for 5 minutes
            },
        ]
        # Alternative: automatic caching via client.messages.create(...) with no
        # explicit cache_control — Anthropic auto-caches prefixes > 1024 tokens.
        # Explicit breakpoints give you precise control over what gets cached.

    def chat(self, user_input: str) -> tuple[str, dict]:
        """Send message, track cache metrics, return (response, usage_dict)."""
        self.messages.append({"role": "user", "content": user_input})

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                system=self._build_system(),
                messages=self.messages,
            )
        except Exception:
            self.messages.pop()
            raise

        self.token_tracker.track(response.usage)

        # Extract cache metrics from usage
        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens
        cache_write = getattr(response.usage, "cache_creation_input_tokens", 0) or 0
        cache_read = getattr(response.usage, "cache_read_input_tokens", 0) or 0

        self.metrics.record_call(input_tokens, output_tokens, cache_write, cache_read)

        usage_dict = {
            "input": input_tokens,
            "output": output_tokens,
            "cache_write": cache_write,
            "cache_read": cache_read,
        }

        logger.info(
            "Call %d — input: %d, output: %d, cache_write: %d, cache_read: %d",
            self.metrics.call_count,
            input_tokens,
            output_tokens,
            cache_write,
            cache_read,
        )

        assistant_message = str(response.content[0].text)
        self.messages.append({"role": "assistant", "content": assistant_message})

        return assistant_message, usage_dict


def _render_call_metrics(console: Console, call_num: int, usage: dict) -> None:
    """Render per-call cache metrics."""
    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column("Metric", style="dim")
    table.add_column("Value", justify="right")

    table.add_row("Input tokens", f"[cyan]{usage['input']:,}[/cyan]")
    table.add_row("Output tokens", f"[cyan]{usage['output']:,}[/cyan]")

    # Highlight cache behavior
    if usage["cache_write"] > 0:
        table.add_row(
            "Cache write",
            f"[yellow]{usage['cache_write']:,}[/yellow] [dim](1.25x — first call populates cache)[/dim]",
        )
    if usage["cache_read"] > 0:
        table.add_row(
            "Cache read",
            f"[green]{usage['cache_read']:,}[/green] [dim](0.1x — 90% savings!)[/dim]",
        )
    if usage["cache_write"] == 0 and usage["cache_read"] == 0:
        table.add_row("Cache", "[dim]no cacheable content[/dim]")

    console.print(Panel(table, title=f"Call {call_num}", border_style="dim", padding=(0, 1)))


def _render_savings_summary(console: Console, metrics: CacheMetrics) -> None:
    """Render cumulative cost comparison."""
    cost_cached = metrics.cost_with_caching()
    cost_baseline = metrics.cost_without_caching()
    savings = metrics.savings()
    savings_pct = (savings / cost_baseline * 100) if cost_baseline > 0 else 0

    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column("Metric", style="dim", min_width=20)
    table.add_column("Value", justify="right")

    table.add_row("Cost without caching", f"[red]${cost_baseline:.6f}[/red]")
    table.add_row("Cost with caching", f"[green]${cost_cached:.6f}[/green]")
    table.add_row("Savings", f"[bold green]${savings:.6f} ({savings_pct:.1f}%)[/bold green]")
    table.add_row("Cache hit rate", f"[cyan]{metrics.cache_hit_rate():.1f}%[/cyan]")
    table.add_row("Total calls", f"[cyan]{metrics.call_count}[/cyan]")

    console.print(
        Panel(
            table,
            title="Cumulative Savings",
            border_style="green" if savings > 0 else "dim",
            padding=(0, 1),
        )
    )


def main() -> None:
    """Main orchestration function for the prompt caching demo."""
    console = Console()
    token_tracker = AnthropicTokenTracker()
    agent = CachedSupportAgent(MODEL, token_tracker)

    console.print(
        Panel(
            "[bold cyan]Prompt Caching Demo[/bold cyan]\n\n"
            "This customer support agent has a large company policy document (~1500 tokens)\n"
            "as its system prompt, cached using Anthropic's prompt caching.\n\n"
            "[bold]How it works:[/bold]\n"
            "  1. First call: cache MISS — the policy is written to cache (1.25x cost)\n"
            "  2. Subsequent calls: cache HIT — policy is read from cache (0.1x cost)\n"
            "  3. Cache TTL is 5 minutes — each hit refreshes it\n\n"
            "Ask support questions about TechFlow Solutions and watch the savings grow.\n"
            "Type [bold]'quit'[/bold] or [bold]'exit'[/bold] to end.\n\n"
            "[bold]Try these sample questions:[/bold]\n"
            "  1. What is TechFlow Solutions?\n"
            "  2. What is your return policy for annual subscriptions?\n"
            "  3. How long does shipping take?\n"
            "  4. What plan tiers do you offer and what do they cost?\n"
            "  5. Do you offer nonprofit discounts?",
            title="TechFlow Support",
        )
    )

    while True:
        console.print("\n[bold green]You:[/bold green] ", end="")
        user_input = input().strip()

        if user_input.lower() in ["quit", "exit", ""]:
            console.print("\n[yellow]Ending session...[/yellow]")
            break

        try:
            response, usage = agent.chat(user_input)

            console.print("\n[bold blue]Support Agent:[/bold blue]")
            console.print(Markdown(response))

            # Per-call cache breakdown
            console.print()
            _render_call_metrics(console, agent.metrics.call_count, usage)

            # Cumulative savings (meaningful after 2+ calls)
            if agent.metrics.call_count >= 2:
                _render_savings_summary(console, agent.metrics)

        except Exception as e:
            logger.error("Error during chat: %s", e)
            console.print(f"\n[red]Error: {e}[/red]")
            break

    # Final report
    console.print()
    token_tracker.report()

    if agent.metrics.call_count >= 2:
        console.print()
        _render_savings_summary(console, agent.metrics)


if __name__ == "__main__":
    main()
