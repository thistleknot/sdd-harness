"""Tests for mermaid_to_infographic.py.

Spec: no governing spec found; basis is the operator instruction of 2026-10-08 recorded in
mermaid_to_infographic.py (x = role flow, y = model lane with effort inside it, squash roles
only when model and effort are identical). Run: python -m pytest diagrams/test_mermaid_to_infographic.py -q
"""
import re
import xml.dom.minidom

import pytest

import mermaid_to_infographic as m

THREE = '''```mermaid
flowchart LR
    User[User request] --> L["Leader<br/>gpt-5.4 / medium<br/>plans"]
    L <-->|"bodies / result"| F["Fighter<br/>gpt-5.4 / low<br/>read-write"]
    L <-->|"reading"| S["Scout<br/>gpt-5.4-mini / low<br/>read-only"]
    L <-->|"big spec"| G["Wizard<br/>gpt-6.1-sol / high<br/>specs only"]
    S -. "escalate" .-> G
    G -.still going.-> Stop["STOP: report to the operator"]
    L --> L
```'''

TWO = THREE.replace("gpt-6.1-sol / high", "gpt-5.4 / high")

# Scry has the same model and effort as the Leader, so it squashes into it.
SQUASH = THREE.replace("    L --> L", '''    L <-->|"unclear fault"| I["Scry<br/>gpt-5.4 / medium<br/>read-only"]
    I -. "IMPL_FAULT" .-> F''')

OPENROUTER = '''```mermaid
flowchart LR
    %% title: OpenRouter, any vendor on the same dial
    %% slot light: anthropic/claude-haiku-5.5, deepseek/deepseek-v4-flash
    %% slot mid: anthropic/claude-sonnet-5.5, openai/gpt-5.4
    %% slot heavy: openai/gpt-5.6-sol, openai/gpt-5.6-terra
    L["Leader<br/>anthropic/claude-sonnet-5.5 / medium"] <-->|"reading"| S["Scout<br/>deepseek/deepseek-v4-flash / low"]
    L <-->|"big spec"| G["Wizard<br/>openai/gpt-5.6-sol / high"]
```'''


def parsed(text):
    return m.parse_markdown(text)


def prepared(text):
    """Parse and squash, as render() does before laying out."""
    return m.merge_roles(*parsed(text))


def test_parse_label_splits_name_model_effort_and_description():
    n = m.parse_label("L", "Leader (the session)<br/>gpt-5.4 / medium<br/>plans<br/>does light work")
    assert n["name"] == "Leader (the session)"
    assert (n["model"], n["effort"]) == ("gpt-5.4", "medium")
    assert n["desc"] == ["plans", "does light work"]


def test_parse_label_without_effort_is_an_aux_node():
    n = m.parse_label("User", "User request")
    assert n["effort"] is None and n["model"] is None and n["name"] == "User request"


def test_edge_syntaxes_and_self_loop_dropped():
    nodes, edges = parsed(THREE)
    by_pair = {(e["src"], e["dst"]): e for e in edges}
    assert by_pair[("L", "F")]["bidir"] is True and by_pair[("L", "F")]["text"] == "bodies / result"
    assert by_pair[("S", "G")]["dotted"] is True and by_pair[("S", "G")]["text"] == "escalate"
    assert by_pair[("G", "Stop")]["text"] == "still going"  # unquoted dotted label
    assert by_pair[("User", "L")]["dotted"] is False and by_pair[("User", "L")]["text"] == ""
    assert ("L", "L") not in by_pair and len(edges) == 6


@pytest.mark.parametrize("model,slot", [
    ("Haiku 5.5", 0), ("gpt-5.4-mini", 0), ("Sonnet 5.5", 1), ("gpt-5.4", 1),
    ("gpt-6.1-sol", 2), ("gpt-6.5-tierra", 2), ("gpt-5-solr", 2), ("Opus 5.5", 2),
])
def test_slot_of(model, slot):
    assert m.slot_of(model) == slot


def test_palette_matches_the_color_key():
    assert m.palette(0, "high") == "#f91010"
    assert m.palette(1, "medium") == "#e2bd74"
    assert m.palette(2, "low") == "#c1e1c4"


# ---- squash rule: merge only when model AND effort are identical -------------------------

def test_roles_with_identical_model_and_effort_squash_into_one_node():
    nodes, edges = prepared(SQUASH)
    assert "I" not in nodes
    leader = nodes["L"]
    assert leader["name"] == "Leader + Scry" and leader["members"] == ["Leader", "Scry"]
    assert (leader["model"], leader["effort"]) == ("gpt-5.4", "medium")
    assert any(line.startswith("Scry: read-only") for line in leader["desc"])
    assert not any(e["src"] == e["dst"] for e in edges)                  # the Leader<->Scry hand-off is gone
    impl = [e for e in edges if e["text"] == "IMPL_FAULT"]
    assert len(impl) == 1 and (impl[0]["src"], impl[0]["dst"]) == ("L", "F")   # Scry's edge reattached
    assert len(edges) == 7                                                # 8 parsed, minus the internal pair


def test_squashed_description_prefixes_use_the_class_name_without_its_function():
    text = SQUASH.replace("Leader<br/>", "Captain (orchestrator)<br/>").replace("Scry<br/>", "Scry (debugger)<br/>")
    nodes, _ = prepared(text)
    head = nodes["L"]
    assert head["name"] == "Captain (orchestrator) + Scry (debugger)"
    assert head["desc"][0].startswith("Captain: plans") and head["desc"][-1] == "Scry: read-only"
    assert not any("(orchestrator):" in line or "(debugger):" in line for line in head["desc"])


def test_a_different_effort_keeps_roles_apart():
    nodes, _ = prepared(THREE)                       # Leader medium and Fighter low, same model
    assert nodes["L"]["name"] == "Leader" and nodes["F"]["name"] == "Fighter"
    assert nodes["L"]["members"] == ["Leader"]


def test_a_different_model_keeps_roles_apart():
    text = THREE.replace("gpt-5.4 / low", "gpt-5.4-mini / low")           # Fighter now matches the Scout
    nodes, _ = prepared(text)
    assert "S" not in nodes and nodes["F"]["name"] == "Fighter + Scout"      # same model and effort: squash
    nodes, _ = prepared(THREE)
    assert nodes["F"]["name"] == "Fighter" and nodes["S"]["name"] == "Scout"  # gpt-5.4 vs gpt-5.4-mini: apart


def test_squash_drops_duplicate_edges_after_remapping():
    text = THREE.replace("    L --> L", '''    L <-->|"bodies / result"| F2["Fighter2<br/>gpt-5.4 / low<br/>x"]''')
    nodes, edges = prepared(text)
    assert "F2" not in nodes
    assert sum(1 for e in edges if e["text"] == "bodies / result") == 1


# ---- layout: x is the role flow, y is the model lane with effort inside it ---------------

def test_flow_columns_start_at_the_leader_and_fan_out():
    nodes, edges = prepared(THREE)
    depth = m.flow_columns(nodes, edges)
    assert depth == {"L": 0, "F": 1, "S": 1, "G": 1}


def test_flow_columns_follow_hops_through_a_chain():
    text = '''```mermaid
flowchart LR
    User[User request] --> A["Alpha<br/>gpt-5.4 / medium"]
    A --> B["Beta<br/>gpt-5.4 / low"]
    B --> C["Gamma<br/>gpt-5.4-mini / low"]
```'''
    nodes, edges = prepared(text)
    assert m.flow_columns(nodes, edges) == {"A": 0, "B": 1, "C": 2}


def test_layout_x_is_flow_and_y_is_lane_then_effort():
    nodes, edges = prepared(THREE)
    geo = m.layout(nodes, edges)
    leader, fighter, scout, wizard = nodes["L"], nodes["F"], nodes["S"], nodes["G"]
    assert leader["x"] < fighter["x"] == scout["x"] == wizard["x"]       # Leader first, branches share a step
    assert wizard["y"] < leader["y"] < scout["y"]                        # heavy lane above mid above light
    assert leader["y"] < fighter["y"]                                    # inside the mid lane: medium above low
    assert geo["sub_y"][(1, "high")] < geo["sub_y"][(1, "medium")] < geo["sub_y"][(1, "low")]
    assert geo["lane_y"][2] < geo["lane_y"][1] < geo["lane_y"][0]
    for n in nodes.values():
        if n["effort"]:
            top, bottom = geo["lane_y"][n["slot"]], geo["lane_y"][n["slot"]] + geo["lane_h"][n["slot"]]
            assert top <= n["y"] and n["y"] + n["h"] <= bottom
    assert nodes["User"]["x"] < leader["x"] and nodes["Stop"]["x"] > fighter["x"]


def test_nodes_sit_inside_their_effort_row():
    nodes, edges = prepared(THREE)
    geo = m.layout(nodes, edges)
    for n in nodes.values():
        if n["effort"]:
            top = geo["sub_y"][(n["slot"], n["effort"])]
            assert top <= n["y"] and n["y"] + n["h"] <= top + geo["sub_h"][(n["slot"], n["effort"])]


def test_same_row_and_step_nodes_stack_with_room_for_a_label():
    text = THREE.replace("    L --> L", '    L --> H["Helper<br/>Sonnet 5.5 / low<br/>x"]')
    nodes, edges = prepared(text)
    m.layout(nodes, edges)
    a, b = nodes["F"], nodes["H"]                     # both mid lane, low effort, step 2, different models
    assert a["x"] == b["x"] and b["y"] - (a["y"] + a["h"]) == m.STACK_GAP


def test_two_comparable_heavy_models_share_one_lane():
    text = THREE.replace('S["Scout<br/>gpt-5.4-mini / low', 'S["Scout<br/>gpt-6.5-tierra / medium')
    nodes, edges = prepared(text)
    geo = m.layout(nodes, edges)
    assert nodes["S"]["slot"] == nodes["G"]["slot"] == 2
    top, bottom = geo["lane_y"][2], geo["lane_y"][2] + geo["lane_h"][2]
    assert top <= nodes["S"]["y"] and nodes["S"]["y"] + nodes["S"]["h"] <= bottom
    assert top <= nodes["G"]["y"] and nodes["G"]["y"] + nodes["G"]["h"] <= bottom
    svg = m.render(*parsed(text), title=None)
    assert svg.count(">gpt-6.1-sol<") == 1 and svg.count(">gpt-6.5-tierra<") == 1  # both named on the lane tab
    assert "Two model tiers" in svg      # mid and heavy are bound; the light lane is empty


def test_three_tiers_have_no_ghost_lane_and_two_tiers_do():
    three = m.render(*parsed(THREE), title=None)
    two = m.render(*parsed(TWO), title=None)
    assert "Three model tiers" in three and "no heavy model bound" not in three
    assert "Two model tiers" in two and "no heavy model bound" in two


# ---- rendering ---------------------------------------------------------------------------

def test_render_is_well_formed_and_escapes_text():
    nodes, edges = parsed(THREE.replace("plans", "a < b & c"))
    svg = m.render(nodes, edges, title="T & <title>")
    xml.dom.minidom.parseString(svg)
    assert "a &lt; b &amp; c" in svg and "T &amp; &lt;title&gt;" in svg


def test_every_lane_draws_three_effort_stripes_and_each_node_its_color():
    svg3 = m.render(*parsed(THREE), title=None)
    svg2 = m.render(*parsed(TWO), title=None)
    assert svg3.count('fill-opacity="0.28"') == 9        # three bound lanes x three effort rows
    assert svg2.count('fill-opacity="0.28"') == 6        # the unbound heavy lane draws none
    assert m.palette(1, "low") in svg3 and m.palette(2, "high") in svg3
    assert svg3.count("<marker") == 1 and svg3.count('marker-start="url(#arrow)"') == 3


def test_squashed_roles_are_named_on_the_node_and_in_the_note():
    svg = m.render(*parsed(SQUASH), title=None)
    assert svg.count(">Leader + Scry<") == 1
    assert "Squashed roles (same model and effort, so no context handoff): Leader + Scry" in svg
    assert "Squashed roles" not in m.render(*parsed(THREE), title=None)


def test_edge_labels_between_the_same_two_nodes_do_not_overlap():
    crowded = THREE.replace("    L --> L", '    F -->|"result and evidence"| L\n    F -->|"tests and diagnostics"| L')
    svg = m.render(*parsed(crowded), title=None)
    pills = [tuple(map(float, g)) for g in re.findall(
        r'<rect x="([\d.\-]+)" y="([\d.\-]+)" width="([\d.]+)" height="22" rx="11"', svg)]
    assert len(pills) == 7
    for i, (x1, y1, w1) in enumerate(pills):
        for x2, y2, w2 in pills[i + 1:]:
            assert not (abs(x1 - x2) < (w1 + w2) / 2 and abs(y1 - y2) < 22), (x1, y1, x2, y2)


def test_lane_tabs_are_drawn_after_the_edges():
    svg = m.render(*parsed(THREE), title=None)
    assert svg.rindex("<path d=") < svg.index('width="200" height=')  # last edge precedes the first lane tab


def test_stop_pill_is_wide_enough_for_its_text():
    nodes, edges = prepared(THREE)
    m.layout(nodes, edges)
    assert nodes["Stop"]["w"] >= len("STOP: report to the operator") * 7.6


def test_tab_and_title_fonts_shrink_long_text_and_cap():
    assert m.tab_font("Haiku 5.5") == 18
    assert m.tab_font("anthropic/claude-sonnet-5.5") < 18
    assert m.tab_font("x" * 200) == 11
    assert m.title_font("Fighter") == 20
    assert m.title_font("Wizard + Scry (widened) + Fighter") < 20
    assert m.title_font("x" * 200) == 13


# ---- routing -----------------------------------------------------------------------------

def test_edge_bows_around_a_node_sitting_on_its_path_and_only_then():
    def box(x, y, col):
        return {"x": x, "y": y, "w": 100, "h": 50, "col": col}
    nodes = {"a": box(0, 0, 0), "mid": box(200, 0, 1), "b": box(400, 0, 2), "off": box(200, 300, 1)}
    geo = {"grid_y": -500, "grid_h": 1000}
    blocked = {"p1": (100, 25), "p2": (400, 25)}
    bow = m.detour(nodes["a"], nodes["b"], blocked, {k: v for k, v in nodes.items() if k != "off"}, geo)
    assert bow == pytest.approx(-(50 / 2 + 40) * 1.35)                       # up: more room above than below
    clear = m.detour(nodes["a"], nodes["b"], blocked, {k: v for k, v in nodes.items() if k != "mid"}, geo)
    assert clear == 0.0                                                      # 'off' is nowhere near the line
    path, _ = m.edge_path({"p1": (100, 25), "p2": (400, 25), "kind": "h", "s1": "R", "bow": bow})
    assert f"{25 + bow:.1f}" in path                                         # control points carry the bow


def test_pill_nodes_never_block_an_edge():
    pill = {"x": 200, "y": 0, "w": 100, "h": 50, "col": "right"}
    a = {"x": 0, "y": 0, "w": 100, "h": 50, "col": 0}
    b = {"x": 400, "y": 0, "w": 100, "h": 50, "col": 2}
    assert m.detour(a, b, {"p1": (100, 25), "p2": (400, 25)}, {"a": a, "pill": pill, "b": b}, None) == 0.0


# ---- errors and OpenRouter-style slotting ------------------------------------------------

def test_edge_to_undefined_node_fails_fast():
    with pytest.raises(ValueError, match="never given a label"):
        m.parse_block('```\nA["x<br/>m / low"] --> B\n')


def test_markdown_without_effort_nodes_is_rejected():
    with pytest.raises(ValueError, match="no mermaid block"):
        m.parse_markdown('```mermaid\nflowchart LR\n    A[Start] --> B[End]\n```')


def test_parse_directives_reads_slots_and_title_in_declared_order():
    slots, title = m.parse_directives(OPENROUTER)
    assert title == "OpenRouter, any vendor on the same dial"
    assert slots == {
        0: ["anthropic/claude-haiku-5.5", "deepseek/deepseek-v4-flash"],
        1: ["anthropic/claude-sonnet-5.5", "openai/gpt-5.4"],
        2: ["openai/gpt-5.6-sol", "openai/gpt-5.6-terra"],
    }


def test_declared_slot_wins_over_name_patterns():
    assert m.slot_of("deepseek/deepseek-v4-flash", {"deepseek/deepseek-v4-flash": 0}) == 0
    assert m.slot_of("openai/gpt-5.6-sol", {"openai/gpt-5.6-sol": 1}) == 1  # declaration beats the 'sol' pattern


def test_undeclared_unknown_vendor_model_warns_and_lands_in_mid(capsys):
    assert m.slot_of("deepseek/deepseek-v4-flash") == 1
    assert "matches no slot pattern" in capsys.readouterr().err


def test_openrouter_lanes_list_every_declared_model_even_when_no_node_uses_it():
    nodes, edges = m.parse_markdown(OPENROUTER)
    slots, title = m.parse_directives(OPENROUTER)
    svg = m.render(nodes, edges, title, slots)
    for model in ("anthropic/claude-haiku-5.5", "openai/gpt-5.4", "openai/gpt-5.6-terra"):
        assert f">{model}<" in svg                       # declared, but no node uses them
    assert svg.index(">anthropic/claude-sonnet-5.5<") < svg.index(">openai/gpt-5.4<")  # declared order kept
    assert "OpenRouter, any vendor on the same dial" in svg and "no heavy model bound" not in svg


# ---- drawn straight from tiers.toml via party.py ---------------------------------------

def _party_tools():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    import party
    import render_agents
    return party, render_agents.load_schema()


def _party_svg(harness, provider=None, window=None):
    party, schema = _party_tools()
    p = party.resolve_party(schema, harness, provider, window)
    nodes, edges, groups, slots = m.party_graph(p, schema["binding"][p.provider])
    return m.render(nodes, edges, None, slots, groups), p, nodes, groups


def test_party_graph_draws_the_live_anthropic_binding_with_no_squash():
    svg, p, nodes, groups = _party_svg("claude")
    xml.dom.minidom.parseString(svg)
    assert groups == [["leader"], ["reader"], ["doer"], ["oracle"]]
    assert "Two model tiers" in svg and "Squashed roles" not in svg
    assert ">claude-sonnet-5-5<" in svg and ">claude-haiku-5-5<" in svg and "no heavy model bound" in svg
    assert (nodes["oracle"]["model"], nodes["oracle"]["effort"]) == ("claude-sonnet-5-5", "high")


def test_a_window_that_lowers_the_ceiling_squashes_the_oracle_and_the_note_names_it():
    svg, p, nodes, groups = _party_svg("claude", window=(0, 2))
    assert ["leader", "oracle"] in groups
    assert "Squashed roles (same model and effort, so no context handoff): Leader (the session) + Oracle (wild card)" in svg
    assert svg.count(">Oracle (wild card)<") == 0                      # no separate Oracle node any more


def test_party_groups_are_the_authority_even_where_model_and_effort_would_not_match():
    nodes, edges = m.parse_block('''
    A["Alpha<br/>gpt-5.4 / low"] --> B["Beta<br/>gpt-5.4 / high"]
''')
    merged, _ = m.merge_roles(nodes, edges, groups=[["A", "B"]])
    assert list(merged) == ["A"] and merged["A"]["members"] == ["Alpha", "Beta"]   # forced together by the caller
    merged, _ = m.merge_roles(nodes, edges)
    assert sorted(merged) == ["A", "B"]                                            # the default rule keeps them apart


def test_openai_binding_draws_three_tiers_with_a_heavy_lane_and_ollama_has_none():
    svg, p, nodes, groups = _party_svg("codex", "openai")
    assert "Three model tiers" in svg and ">gpt-6.1-sol<" in svg and "no heavy model bound" not in svg
    svg, p, nodes, groups = _party_svg("codex", "ollama")
    assert "Two model tiers" in svg and "no heavy model bound" in svg              # heavy = the mid model at high effort


def test_party_cli_writes_an_svg_for_a_harness_provider(tmp_path, capsys):
    out = tmp_path / "p.svg"
    assert m.main(["--party", "opencode:openrouter", "-o", str(out)]) == 0
    xml.dom.minidom.parseString(out.read_text(encoding="utf-8"))
    assert "opencode:openrouter" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        m.main([])                                                                 # neither inputs nor --party
