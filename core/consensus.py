"""
CONSENSUS — adaptasi pola TradingAgents (bull/bear debate + risk voices + PM sintesis)
tapi DETERMINISTIK (tanpa LLM).

Setiap agent kasih suara:
  - view: 'bull' | 'bear' | 'hold'
  - weight: 0..1 (seberapa yakin / pentingnya agent)
  - note:  alasan singkat

Tiga lapisan (persis kayak TradingAgents):
  1) ANALYST debate: Helios(bull/trend) vs Vega(bear/quant)  -> conviction
  2) RISK voices:    Nyx(conservative) / Leviathan(aggressive) / Atlas(neutral)
  3) PM sintesis:    Atlas agregat -> final decision + sizing multiplier

Output: decision('enter'/'hold'/'exit'), confidence(0..1), sizing_mult(0.5..1.5)
"""
from __future__ import annotations


def _score(view: str) -> float:
    return {"bull": 1.0, "hold": 0.0, "bear": -1.0}.get(view, 0.0)


def decide(analyst_votes: list, risk_votes: list,
           lessons: str = "") -> dict:
    """Aggregasi deterministik.

    analyst_votes / risk_votes: list of {name, view, weight, note}
    """
    # --- 1) analyst debate score (-1..+1) ---
    a_num = a_den = 0.0
    for v in analyst_votes:
        w = float(v.get("weight", 0.5))
        a_num += _score(v.get("view", "hold")) * w
        a_den += w
    a_score = (a_num / a_den) if a_den > 0 else 0.0

    # --- 2) risk voice score (-1..+1) ---
    r_num = r_den = 0.0
    for v in risk_votes:
        w = float(v.get("weight", 0.5))
        r_num += _score(v.get("view", "hold")) * w
        r_den += w
    r_score = (r_num / r_den) if r_den > 0 else 0.0

    # --- 3) PM sintesis: analyst dominan, risk jadi rem ---
    # final = analyst_score * (0.5 + 0.5*risk_score)  -> risk hanya perlambat, tdk membalik
    final = a_score * (0.5 + 0.5 * r_score)

    confidence = abs(final)
    if final > 0.45:
        decision = "enter"
    elif final < -0.45:
        decision = "exit"
    else:
        decision = "hold"

    # sizing multiplier: makin yakin & risk setuju -> makin besar (cap 1.5)
    sizing_mult = max(0.5, min(1.5, 1.0 + final * 0.5))

    bull_notes = [f"{v['name']}: {v.get('note','')}" for v in analyst_votes if v.get("view") == "bull"]
    bear_notes = [f"{v['name']}: {v.get('note','')}" for v in analyst_votes if v.get("view") == "bear"]
    risk_notes = [f"{v['name']}({v.get('view')}): {v.get('note','')}" for v in risk_votes]

    return {
        "decision": decision,
        "confidence": round(confidence, 2),
        "sizing_mult": round(sizing_mult, 2),
        "analyst_score": round(a_score, 2),
        "risk_score": round(r_score, 2),
        "final": round(final, 2),
        "bull_notes": bull_notes,
        "bear_notes": bear_notes,
        "risk_notes": risk_notes,
        "lessons": lessons,
    }


def summarize(c: dict) -> str:
    """Teks debat/consensus buat briefing (gaya TradingAgents)."""
    lines = [
        f"[CONSENSUS] decision={c['decision'].upper()} | conf={c['confidence']} | "
        f"analyst={c['analyst_score']} risk={c['risk_score']} final={c['final']} sizing={c['sizing_mult']}",
    ]
    if c["bull_notes"]:
        lines.append("BULL: " + " | ".join(c["bull_notes"]))
    if c["bear_notes"]:
        lines.append("BEAR: " + " | ".join(c["bear_notes"]))
    if c["risk_notes"]:
        lines.append("RISK: " + " | ".join(c["risk_notes"]))
    if c["lessons"]:
        lines.append("LESSONS: " + c["lessons"])
    return "\n".join(lines)
