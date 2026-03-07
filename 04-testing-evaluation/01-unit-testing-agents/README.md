<!-- ---
title: "Unit Testing Agents"
description: "Mock LLM responses and test agent behavior deterministically"
icon: "check-square"
--- -->

# Unit Testing Agents

Learn how to test AI agents without making API calls. By mocking LLM responses and testing everything around the model — tool execution, decision routing, message construction, error handling — you can build fast, deterministic tests that catch real bugs.

## 🎯 What You'll Learn

- Mock LLM responses to create deterministic test scenarios
- Test tool functions in isolation (input validation, output format, error handling)
- Define and verify behavioral contracts (things the agent must always/never do)
- Use pytest as a test runner for agent test suites
- Build a testable agent with dependency injection
- Record and replay API responses with cassette files for integration tests
- Detect regressions with snapshot testing and token budget assertions

## 📦 Available Examples

| Script | File | Description |
| ------ | ---- | ----------- |
| Run Tests | [01_run_tests.py](01_run_tests.py) | Run the full test suite with Rich UI and confirmation |

### Test Modules

| Test | File | Description |
| ---- | ---- | ----------- |
| Mock LLM | [tests/test_mock_llm.py](tests/test_mock_llm.py) | Mock `client.messages.create()`, test agent loop logic |
| Tools | [tests/test_tools.py](tests/test_tools.py) | Test tool functions in isolation with edge cases |
| Contracts | [tests/test_behavioral_contracts.py](tests/test_behavioral_contracts.py) | Define and verify agent invariants |
| Integration | [tests/test_integration.py](tests/test_integration.py) | Record/replay API responses, snapshot regression |

## 🚀 Quick Start

> **Prerequisites:** Python 3.11+, API keys, and uv. See [SETUP.md](../../SETUP.md) for full setup instructions.

```bash
# Run test suite with Rich UI (shows overview, asks for confirmation)
uv run --directory 04-testing-evaluation/01-unit-testing-agents python 01_run_tests.py

# Run all tests directly via pytest (42 tests)
uv run --directory 04-testing-evaluation/01-unit-testing-agents pytest tests/ -v

# Run a single test module
uv run --directory 04-testing-evaluation/01-unit-testing-agents pytest tests/test_mock_llm.py -v

# Run a specific test class
uv run --directory 04-testing-evaluation/01-unit-testing-agents pytest tests/test_behavioral_contracts.py::TestSafetyContracts -v
```

Or use the [Code Runner](https://marketplace.visualstudio.com/items?itemName=formulahendry.code-runner) VS Code extension to run the currently open script with a single click.

## 🔑 Key Concepts

### 1. The Testing Pyramid for Agents

Traditional testing pyramids apply to agents too, but with an AI twist — the higher you go, the more you rely on live LLM calls and statistical assertions instead of deterministic checks:

| Layer | Speed | Cost | What it tests |
|-------|-------|------|---------------|
| **Unit (mock)** ← test_mock_llm, test_tools | Fast | Free | Tool execution, routing, message construction, error handling |
| **Contracts** ← test_behavioral_contracts | Fast | Free | Safety, termination, history invariants |
| **Integration** ← test_integration | Medium | Free | End-to-end flows with recorded/cached LLM responses |
| **Eval** | Slow | $$ | LLM reasoning quality with live calls and statistical assertions |

### 2. Dependency Injection for Testability

The key to testable agents is **injecting the LLM client** instead of creating it internally:

```python
class ToolUseAgent:
    """Tool-use agent with dependency injection for testability."""

    def __init__(self, client: Any, model: str = "claude-sonnet-4-5-20250929") -> None:
        self.client = client  # Injected — can be a mock in tests
        self.model = model
```

### 3. Mocking LLM Responses

Use `unittest.mock` to create fake Anthropic responses:

```python
def create_mock_response(content, stop_reason="end_turn"):
    response = MagicMock()
    response.content = content
    response.stop_reason = stop_reason
    response.usage = Mock(input_tokens=100, output_tokens=50)
    return response

# In tests
mock_client = MagicMock()
mock_client.messages.create.return_value = create_mock_response(...)
agent = ToolUseAgent(client=mock_client)
```

### 4. Behavioral Contracts

Define invariants — things the agent must ALWAYS or NEVER do:

```python
def test_agent_never_executes_blocked_commands():
    """The agent must never execute rm, sudo, chmod, etc."""
    # Mock LLM to request a blocked command
    # Verify the tool returns an error, not an execution result

def test_agent_stops_after_max_iterations():
    """The agent must terminate after N iterations, not loop forever."""
    agent = SafeToolUseAgent(client=mock, max_iterations=3)
    # Mock LLM to always request tool use
    # Verify agent stops after exactly 3 iterations
```

### 5. Response Cassettes (Record/Replay)

Instead of maintaining brittle `MagicMock` shapes, record real API responses to JSON files and replay them in tests. The cassette system catches divergent behavior — if the agent makes more calls than recorded, the test fails:

```python
class CassetteClient:
    """Replays responses from a cassette file."""

    def __init__(self, cassette_path: Path) -> None:
        with cassette_path.open() as f:
            self._interactions = json.load(f)
        self._call_index = 0
        self.messages = self  # Expose messages.create like the real client

    def create(self, **kwargs) -> CassetteResponse:
        if self._call_index >= len(self._interactions):
            raise RuntimeError("Cassette exhausted — agent behavior has diverged")
        response = self._interactions[self._call_index]["response"]
        self._call_index += 1
        return CassetteResponse(response)
```

### 6. Snapshot Regression Testing

Compare agent output against golden baselines to detect regressions. If a code change causes different output, token usage spikes, or altered message history shape, the snapshot test catches it:

```python
def test_output_matches_snapshot(cassette_dir):
    golden_snapshot = "12 multiplied by 15 equals 180."
    client = CassetteClient(write_cassette(cassette_dir, "calc", CASSETTE_DATA))
    agent = ToolUseAgent(client=client)
    result = agent.send_message("What is 12 * 15?")
    assert result == golden_snapshot, f"Output drifted: {result!r}"
```

## ⚠️ Important Considerations

- **Mocks test scaffolding, not intelligence** — mocked tests verify your agent's harness logic, not the LLM's reasoning. You still need eval tests (Tutorial 02) for quality.
- **Keep mocks realistic** — mock responses should match the actual API format. Unrealistic mocks lead to false confidence.
- **Test error paths** — API failures, malformed tool output, and timeouts are where bugs hide.

## 🔗 Resources

- [Beyond Accuracy: Behavioral Testing of NLP Models with CheckList — Ribeiro et al., 2020](https://arxiv.org/abs/2005.04118) — The foundational paper on behavioral testing with invariance, directional, and minimum functionality tests
- [Building Effective Agents — Anthropic](https://www.anthropic.com/research/building-effective-agents) — Agent patterns (tool use, loops, delegation) that inform what to test and how to inject dependencies
- [pytest Documentation](https://docs.pytest.org/) — Test runner, fixtures, parametrize, and mock integration
- [unittest.mock — Python Docs](https://docs.python.org/3/library/unittest.mock.html) — MagicMock, patch, and side_effect for mocking LLM clients

## 👉 Next Steps

Once you've mastered unit testing, continue to:
- **[Evals](../02-evals/)** — Move beyond deterministic assertions to statistical evaluation with golden datasets and LLM-as-judge
- **Experiment** — Add more behavioral contracts for your own agents
- **Practice** — Write unit tests for agents from [Module 01](../../01-foundations/)
