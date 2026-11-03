# Color key: model is the hue, effort is the vibrancy

Everything on the party diagrams is read from two positions.

- **Hue = which model.** A red → amber → green gradient with three slots:
  light = red, mid = amber, heavy = green. Slots are absolute, so Sonnet is
  amber in every diagram, and a binding without a heavy model simply has no
  green on its dial. A model that sits between two slots takes the blended hue.
- **Vibrancy = effort.** Within a hue: low is pale and muted, medium is normal,
  high is vivid.

| Slot | Claude | Codex (operator's ids) | low | medium | high |
|---|---|---|---|---|---|
| light (red) | Haiku 5.5 | gpt-5.4-mini | `#e1c1c1` | `#e27474` | `#f91010` |
| mid (amber) | Sonnet 5.5 | gpt-5.4 | `#e1d6c1` | `#e2bd74` | `#f9ab10` |
| heavy (green) | none (Oracle runs Sonnet 5.5 high; no Opus) | gpt-6.1-sol, gpt-6.5-tierra (comparable) | `#c1e1c4` | `#74e27d` | `#10f924` |

Rule, for any other ladder: `hue = 0°` at light, `40°` at mid, `125°` at heavy,
linear between slots; `(saturation, lightness)` = `(35%, 82%)` low, `(65%, 67%)`
medium, `(95%, 52%)` high. All nine colors keep at least 4.6:1 contrast with
the dark node text (`#111111`).

Color is a second channel. Every node still carries the model and effort in
words, because red and green alone fail for red-green color blindness.

```mermaid
flowchart LR
    subgraph Light["light: red"]
        direction LR
        r1["low"] --- r2["medium"] --- r3["high"]
    end
    subgraph Mid["mid: amber"]
        direction LR
        a1["low"] --- a2["medium"] --- a3["high"]
    end
    subgraph Heavy["heavy: green"]
        direction LR
        g1["low"] --- g2["medium"] --- g3["high"]
    end
    Light ~~~ Mid ~~~ Heavy

    style r1 fill:#e1c1c1,stroke:#333,color:#111
    style r2 fill:#e27474,stroke:#333,color:#111
    style r3 fill:#f91010,stroke:#333,color:#111
    style a1 fill:#e1d6c1,stroke:#333,color:#111
    style a2 fill:#e2bd74,stroke:#333,color:#111
    style a3 fill:#f9ab10,stroke:#333,color:#111
    style g1 fill:#c1e1c4,stroke:#333,color:#111
    style g2 fill:#74e27d,stroke:#333,color:#111
    style g3 fill:#10f924,stroke:#333,color:#111
```

Reading a diagram: a pale amber node is Sonnet at low effort; a vivid green
node is the heavy model at high effort. A window that lowers the ceiling
(see the squash rows) shows up as the vivid end of the dial disappearing.
