# Trifecta dial — the same dial as `trifecta.md` Diagram 2, rendered standalone

```mermaid
flowchart LR
    %% title: Trifecta dial: deepseek carries the top, glm the middle, qwen sits off-ladder (2026-11-07)
    %% slot light: qwen/qwen3.8-flash
    %% slot mid: z-ai/glm-5.3-flash
    %% slot heavy: deepseek/deepseek-v4.1-flash-1017

    subgraph Dial["Dial: model / effort, heaviest to cheapest — AA v5.0.1 index in brackets"]
        direction LR
        t4["t4<br/>deepseek / max<br/>(33)"] --> t3["t3<br/>deepseek / high<br/>(29)"] --> t2["t2<br/>glm / max<br/>(unmeasured)"] --> t1["t1<br/>glm / medium<br/>(unmeasured)"] --> t0["t0<br/>glm / low<br/>(unmeasured)"] --> q0["q0<br/>qwen / fixed<br/>(unscored, no dial)"]
    end

    Oracle -->|fixed, clamped to the top| t4
    Leader -->|floor| t1
    Leader -. ceiling .-> t2
    Fighters -->|floor| t0
    Fighters -. ceiling .-> t1
    Scout -->|fixed, no dial| q0

    style t4 fill:#10f924,stroke:#333,color:#111
    style t3 fill:#74e27d,stroke:#333,color:#111
    style t2 fill:#f9ab10,stroke:#333,color:#111
    style t1 fill:#e2bd74,stroke:#333,color:#111
    style t0 fill:#e1d6c1,stroke:#333,color:#111
    style q0 fill:#e27474,stroke:#333,color:#111
    style Oracle fill:#10f924,stroke:#333,color:#111
    style Leader fill:#e2bd74,stroke:#333,color:#111
    style Fighters fill:#e1d6c1,stroke:#333,color:#111
    style Scout fill:#e27474,stroke:#333,color:#111
```

Prices (OpenRouter, 2026-11-07): deepseek-1017 $0.006 in / $0.50 out ·
glm-5.3-flash $0.034 / $0.083 · qwen3.8-flash $0.15 / $0.47. Indices (AA v5.0.1,
2026-11-07): 33 and 29 measured; the amber rungs and q0 are not.
