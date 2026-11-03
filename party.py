"""party.py -- resolve the party's roles against one provider's dial.

Spec: C:/Users/user/.claude/plans/make-harness-render-and-install-the-party.md, section 2
      (operator instruction 2026-10-08: models are a wrapper layer restricted by provider;
      roles whose model AND effort are identical squash into one context, so no hand-off).
Task: plan layer 1.

The dial is the ordered list of (tier, effort) steps a provider declares in tiers.toml,
weakest first. Each role pins to one step; a window [lo, hi] clamps every role into a
sub-range of the dial; after clamping, roles that land on the same (model, effort) share
one context. A group containing the Leader (the session) runs inline: its other members
get no agent file, because the Leader is already that brain.
"""
from __future__ import annotations

from dataclasses import dataclass, field

EFFORT_ORDER = ("low", "medium", "high")
WRITE_TOOLS = frozenset({"Edit", "Write", "Bash"})


class PartyError(RuntimeError):
    """Raised when roles cannot be resolved against a provider's dial."""


@dataclass(frozen=True)
class Step:
    tier: str
    model: str
    effort: str


@dataclass(frozen=True)
class RoleSetting:
    role: str                 # key in [role.*]
    name: str                 # agent name, e.g. "doer"
    kind: str                 # "agent" or "session"
    tier: str
    model: str
    effort: str               # symbolic: low | medium | high
    effort_value: str         # the provider's spelling of that effort
    effort_key: str           # the harness's name for the effort field
    tools: tuple
    step: int                 # index into Party.steps after clamping
    target: int               # index the role pinned to before the window
    squashed_into: str | None  # role key of the Leader when this role runs inline


@dataclass
class Party:
    harness: str
    provider: str
    steps: list
    window: tuple
    roles: list
    groups: list              # lists of role keys sharing (model, effort)
    warnings: list = field(default_factory=list)
    leader_attempts: int = 1

    def agent_roles(self) -> list:
        """Roles that get an agent file: agents not squashed into the Leader."""
        return [r for r in self.roles if r.kind == "agent" and r.squashed_into is None]

    def leader(self) -> RoleSetting | None:
        return next((r for r in self.roles if r.kind == "session"), None)


def parse_window(text: str | None, n_steps: int) -> tuple:
    """'lo:hi' with either side optional -> inclusive (lo, hi) step indices."""
    if not text:
        return (0, n_steps - 1)
    lo_s, _, hi_s = text.partition(":")
    lo = int(lo_s) if lo_s.strip() else 0
    hi = int(hi_s) if hi_s.strip() else n_steps - 1
    return (lo, hi)


def parse_open_window(text: str | None) -> tuple | None:
    """'lo:hi' with either side optional -> (lo|None, hi|None); resolve_party fills open ends per dial."""
    if not text:
        return None
    lo_s, _, hi_s = text.partition(":")
    return (int(lo_s) if lo_s.strip() else None, int(hi_s) if hi_s.strip() else None)


def _tier_model(binding: dict, tier: str, what: str) -> str:
    model = binding.get(tier, "")
    if not model:
        raise PartyError(f"no model bound to {tier} (needed by {what})")
    return model


def _target_step(steps: list, binding: dict, role_key: str, role: dict) -> int:
    tier, effort = role["tier"], role["reasoning"]
    exact = [i for i, s in enumerate(steps) if s.tier == tier and s.effort == effort]
    if exact:
        return exact[0]
    model = _tier_model(binding, tier, f"role {role_key}")
    same_model = [i for i, s in enumerate(steps) if s.model == model]
    if not same_model:
        raise PartyError(f"role {role_key}: no dial step uses {model!r}")
    return min(same_model, key=lambda i: (abs(EFFORT_ORDER.index(steps[i].effort) - EFFORT_ORDER.index(effort)), i))


def _capability(tools) -> str:
    return "write" if WRITE_TOOLS & set(tools) else "read-only"


def resolve_party(schema: dict, harness: str, provider: str | None = None, window: tuple | None = None) -> Party:
    """Resolve every role of `harness` against `provider`'s dial, clamped to `window`."""
    h = schema.get("harness", {}).get(harness, {})
    speaks = list(h.get("providers", []))
    bindings = schema.get("binding", {})
    if provider is None:
        if speaks:
            provider = speaks[0]
        elif harness in bindings:
            provider = harness  # a binding named like the harness (older schemas)
        else:
            raise PartyError(f"harness {harness!r} speaks no provider (it gets an instruction document only)")
    elif speaks and provider not in speaks:
        raise PartyError(f"harness {harness!r} cannot speak provider {provider!r}; it speaks {speaks}")
    if provider not in bindings:
        raise PartyError(f"no binding for provider {provider!r}")
    binding = bindings[provider]

    dial = binding.get("dial")
    if not dial:
        raise PartyError(f"provider {provider!r} declares no dial")
    effort_map = binding.get("effort_map", {})
    steps = []
    for tier, effort in dial:
        if effort not in effort_map:
            raise PartyError(f"{provider}: effort_map has no entry for {effort!r}")
        steps.append(Step(tier, _tier_model(binding, tier, f"{provider} dial"), effort))

    lo, hi = window if window is not None else (None, None)
    lo = 0 if lo is None else lo                      # an open end means the first / last step of THIS dial
    hi = len(steps) - 1 if hi is None else hi
    if not (0 <= lo <= hi < len(steps)):
        raise PartyError(f"window {lo}:{hi} is outside the {len(steps)}-step dial of {provider!r}")

    effort_key = h.get("effort_key") or binding.get("effort_key", "effort")
    roles: list[RoleSetting] = []
    for role_key, role in schema["role"].items():
        target = _target_step(steps, binding, role_key, role)
        idx = min(max(target, lo), hi)
        step = steps[idx]
        roles.append(RoleSetting(
            role=role_key, name=role["name"], kind=role.get("kind", "agent"), tier=role["tier"],
            model=step.model, effort=step.effort, effort_value=effort_map[step.effort],
            effort_key=effort_key, tools=tuple(role.get("tools", [])), step=idx, target=target,
            squashed_into=None))

    grouped: dict = {}
    for r in roles:
        grouped.setdefault((r.model, r.effort), []).append(r)
    leader = next((r for r in roles if r.kind == "session"), None)
    warnings: list[str] = []
    for r in roles:
        if r.step != r.target:
            warnings.append(f"{r.role}: clamped from step {r.target} to {r.step} by window {lo}:{hi}")
    for members in grouped.values():
        if len(members) < 2:
            continue
        names = [m.role for m in members]
        if leader is not None and leader in members:
            for m in members:
                if m is not leader:
                    roles[roles.index(m)] = _squash(m, leader.role)
            others = [n for n in names if n != leader.role]
            warnings.append(f"{', '.join(others)} squashed into {leader.role} (same model and effort): "
                            "no hand-off and no agent file")
            if "oracle" in others:
                warnings.append("oracle squashed into the leader: nobody above him to escalate to, he keeps the problem")
        else:
            warnings.append(f"{' + '.join(names)} share one context (same model and effort)")
            caps = {_capability(m.tools) for m in members}
            if len(caps) > 1:
                warnings.append(f"{' + '.join(names)} mix read-only and write roles in one context: "
                                "keep each role's own tool allowlist")
    return Party(harness=harness, provider=provider, steps=steps, window=(lo, hi), roles=roles,
                 groups=[[m.role for m in ms] for ms in grouped.values()], warnings=warnings,
                 leader_attempts=int(schema.get("escalation", {}).get("leader_attempts", 1)))


def _squash(role: RoleSetting, leader_key: str) -> RoleSetting:
    return RoleSetting(**{**role.__dict__, "squashed_into": leader_key})


def report(party: Party) -> str:
    """Human-readable role table plus every warning, for the CLI."""
    lines = [f"{party.harness} / {party.provider}  window {party.window[0]}:{party.window[1]}  "
             f"({len(party.steps)} steps)"]
    for i, s in enumerate(party.steps):
        lines.append(f"  step {i}: {s.model} / {s.effort}  [{s.tier}]")
    for r in party.roles:
        tail = f"  -> squashed into {r.squashed_into}" if r.squashed_into else ""
        lines.append(f"  {r.role:8} {r.model} / {r.effort}  (step {r.step}){tail}")
    lines += [f"  note: {w}" for w in party.warnings]
    return "\n".join(lines)
