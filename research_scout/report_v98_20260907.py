"""Render the frozen experiment's recorded results without changing its decisions."""

import json
from collections import Counter

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from research_scout.v98_earnings_answers_20260907 import OUT, ROOT, read, save, sha


def main():
    verdict = read("verdict.json")
    bounded = (
        read("bounded_economic_verdict.json")
        if (OUT / "bounded_economic_verdict.json").exists()
        else None
    )
    status = bounded["status"] if bounded else verdict["status"]
    source = read("source_summary.json")
    panel = read("panel_audit.json")
    spec = read("specification.json")
    results = {
        name: read(f"{name}_evaluation.json") for name in ["primary", "baseline", "all_events"]
    }
    primary = results["primary"]
    coverage = read("market_coverage.json")
    retrieval = read("market_retrieval.json")
    raw_text = read("transcript_retrieval.json")
    audit = read("source_audit.json")
    models = read("model_audits.json")
    price_rows = sum(p["row_count"] for r in retrieval for p in r["pages"])
    accepted_by_year = source["eligible_by_year"]
    chart = None
    if primary["complete_equity"]:
        days = list(primary["daily_returns"]["net"])
        dates = pd.to_datetime(days)
        fig, ax = plt.subplots(figsize=(12, 6.2), constrained_layout=True)
        colors = {"primary": "#1965ad", "baseline": "#d87c29", "all_events": "#668b6b"}
        labels = {
            "primary": "Answers added: net",
            "baseline": "Prepared + prices: net",
            "all_events": "All eligible calls: net",
        }
        for name, result in results.items():
            if result["complete_equity"]:
                returns = [result["daily_returns"]["net"][d] for d in days]
                wealth = 100 * np.cumprod(1 + np.array(returns))
                ax.plot(
                    dates,
                    wealth,
                    label=labels[name],
                    color=colors[name],
                    lw=2.2 if name == "primary" else 1.4,
                    alpha=1 if name == "primary" else 0.8,
                )
        from research_scout.v98_backtest_20260907 import get_benchmark

        benchmark = get_benchmark()
        ax.plot(
            dates,
            100 * np.cumprod(1 + benchmark.to_numpy()),
            label="SPY adjusted buy-and-hold proxy",
            color="#202731",
            lw=2.3,
        )
        ax.axhline(100, color="#99a1aa", lw=0.7, linestyle="--")
        ax.set_title("V98 · Same-day earnings-call language test", fontsize=16, loc="left")
        ax.set_ylabel("Value of $100", fontsize=11)
        ax.grid(axis="y", alpha=0.2)
        ax.spines[["top", "right"]].set_visible(False)
        ax.legend(frameon=False, fontsize=9, loc="best")
        fig.supxlabel(
            "2021–2023 · 5 bps per side · retrospective source exclusions · bar-reference fills",
            fontsize=9,
        )
        chart = OUT / "equity_paths.png"
        fig.savefig(chart, dpi=160)
        plt.close(fig)
    elif bounded:
        bound = bounded["portfolios"]["primary"]
        values = [
            bound["optimistic_full_calendar_upper_bounds"]["net"],
            bound["optimistic_full_calendar_upper_bounds"]["reference"],
            bound["SPY_ending_cash"],
        ]
        labels = [
            "Strategy upper bound\n(known days after costs)",
            "Strategy upper bound\n(all costs removed)",
            "SPY\n(adjusted-price proxy)",
        ]
        fig, ax = plt.subplots(figsize=(10, 5), constrained_layout=True)
        ax.barh(labels, values, color=["#1965ad", "#8cb7dd", "#202731"], height=0.55)
        ax.invert_yaxis()
        for i, value in enumerate(values):
            ax.text(value + 1, i, f"${value:.2f}", va="center", fontsize=11)
        ax.set_xlim(0, max(values) * 1.15)
        ax.axvline(100, color="#99a1aa", linestyle="--", lw=0.8)
        ax.set_xlabel("Value relative to $100 initial capital")
        ax.set_title("V98 · Missing-day upper bounds versus SPY", loc="left", fontsize=15)
        ax.spines[["top", "right"]].set_visible(False)
        fig.supxlabel(
            f"Bounds allow perfect, costless low-to-high trading on {len(bound['missing_dates'])} missing dates.\nActual full-calendar strategy equity is unknown; daily-range and source-vintage limitations apply.",
            fontsize=9,
        )
        chart = OUT / "missing_day_bounds.png"
        fig.savefig(chart, dpi=160)
        plt.close(fig)
    lines = [
        "# V98: management's answers after earnings calls",
        "",
        f"Status: **{status}**. This is one new fixed hypothesis and two diagnostic controls. No validated edge or deployment decision.",
        "",
    ]
    if primary["complete_equity"]:
        lines += [
            f"Across all {primary['calendar_sessions']} exchange sessions in 2021–2023, $100 became **${primary['ending_cash']:.2f} after costs**, versus **${primary['SPY']['ending_cash']:.2f} in SPY**. The primary rule made {primary['legs']:,} stock trades on {primary['trade_days']} days. All positions were closed the same day.",
            "",
        ]
    else:
        lines += [
            f"Required market inputs are missing on {len(primary['missing_dates'])} evaluation dates. Full-calendar equity is unavailable; available-case returns are not a full backtest.",
            "",
        ]
        if bounded:
            bound = bounded["portfolios"]["primary"]
            ceiling = bound["optimistic_full_calendar_upper_bounds"]
            lines += [
                f"Even allowing perfect, costless low-to-high trades in the best eligible stock on every unknown day, the fixed run's ending-value ceiling is **${ceiling['net']:.2f}**, versus **${bound['SPY_ending_cash']:.2f} for SPY**. Removing costs on the known days too gives a ceiling of **${ceiling['reference']:.2f}**. These are bounds, not measured final returns. The comparison is conditional on the cached daily ranges covering the missing prices and leaves the fitted available-data models unchanged.",
                "",
            ]
    if chart:
        lines += [f"![Backtest comparison]({chart.as_posix()})", ""]
    lines += [
        "## What was tested",
        "",
        "The proposed mechanism is delayed incorporation of information in management's answers to analysts. A small text model tests whether those answers add predictive value beyond prepared remarks, the company's identity, its opening gap, and the first half-hour stock and SPY returns. It does not use a language model pretrained on later company outcomes.",
        "",
        "The training window begins in 2018. At each month in 2021–2023, both models are refitted using only earlier completed events. Each text block uses word unigrams and bigrams, a training-only vocabulary of at most 1,500 features, minimum document frequency 5, sublinear term frequency and L2 normalization. Both models use Ridge alpha 10 with identical fixed settings. There was no parameter or threshold search.",
        "",
        "The augmented model adds a separate management-answer block to the prepared-remarks, ticker and price features. A stock is selected only when its augmented predicted log return exceeds the 5 bps each-way cost hurdle and exceeds the baseline model's prediction. All selected stocks share the day's capital equally. The baseline control trades its own forecasts above the same hurdle; the all-event control buys every eligible call. These controls are diagnostic comparisons, not independently discovered strategies.",
        "",
        "## Information and execution clocks",
        "",
        "A transcript is eligible at the first full XNYS session whose opening is strictly later than the publisher's later publication/modification time plus 30 minutes. Revisions that move that eligible session are excluded because the original text was not retrieved. Early-close dates are skipped. Only management's prepared remarks and answers after an analyst question enter the model; analyst questions, operator remarks, current-price page introductions, recommendations and surrounding disclosures do not.",
        "",
        "The price features use the 09:30–09:55 five-minute bars, which finish at 10:00. One minute of processing makes the signal available at 10:01. Entry is the 10:05 bar open, and exit is the 15:55 bar open, in New York time. These are bar-reference scenarios: a bar's first qualifying trade is not a guaranteed executable quote. Historical split adjustment cancels in the within-day ratios; it does not establish original quoted price levels. The net scenario charges 5 bps on each side, with no additional invented spread or fee; the stress doubles those bps.",
        "",
        "## Data actually collected",
        "",
        f"The fixed universe contains {len(spec['universe'])} existing stock symbols. All 72 monthly sitemaps for 2018–2023 were retrieved. There were {source['documents']:,} candidate URLs, {sum('path' in r for r in raw_text):,} saved source pages, and {source['eligible_events']:,} admitted events across {source['eligible_symbols']} companies. Headline checks remove incidental ticker-word matches from URLs. The only issuer aliases were FB to META and GOOG to GOOGL; no merger predecessors were inferred.",
        "",
        "| Event year | Admitted events |",
        "|---|---:|",
    ]
    lines += [f"| {year} | {count:,} |" for year, count in sorted(accepted_by_year.items())]
    lines += [
        "",
        f"The price collection covered {len(retrieval):,} historical date batches and {len(coverage):,} requested instrument-sessions, with {price_rows:,} raw bars before regular-session filtering. Every response page was retained and hashed; pagination and exchange-session coverage were audited. Required event features were missing for {panel['feature_missing']} events and entry/exit labels for {panel['label_missing']} events. The initial complete training sample had {panel['complete_training_events']:,} events; there were {panel['evaluation_events']:,} evaluation events before trade selection.",
        "",
        "Exclusion counts below can overlap; they are data-admission reasons, not trading losses.",
        "",
        "| Source admission issue | Documents |",
        "|---|---:|",
    ]
    lines += [
        f"| {name.replace('_', ' ')} | {count:,} |"
        for name, count in sorted(source["problem_counts"].items(), key=lambda x: (-x[1], x[0]))
    ]
    lines += [
        "",
        "## Returns and controls",
        "",
        "Products below use known days only where gaps remain. They are not full-calendar ending equity. Trade counts exclude unknown days; missing days are never assigned zero returns.",
        "",
        "| Portfolio | Gross product on known days | Net product on known days | Doubled-cost product | Known trade days / stock trades | Known-day net drawdown |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for name, label in [
        ("primary", "Answers added"),
        ("baseline", "Prepared + prices"),
        ("all_events", "All eligible calls"),
    ]:
        r = results[name]
        m = r["available_case_metrics"]
        suffix = " (available cases only)" if not r["complete_equity"] else ""
        lines.append(
            f"| {label}{suffix} | ${m['reference']['ending_cash']:.2f} | ${m['net']['ending_cash']:.2f} | ${m['cost_stress']['ending_cash']:.2f} | {r['trade_days']} / {r['legs']:,} | {m['net']['max_daily_drawdown']:.2%} |"
        )
    lines += [
        f"| SPY adjusted proxy | ${primary['SPY']['ending_cash']:.2f} | — | — | Held across full calendar | {primary['SPY']['max_daily_drawdown']:.2%} |",
        "",
        "Idle cash earns zero. All values start from $100 and assume fractional shares without borrowing. Where data are missing, the drawdown statistic covers the known-day product only, not the actual full-calendar path. None of these daily statistics measure intraday adverse excursions. SPY includes overnight exposure and an existing adjusted-price dividend proxy. This is the user's full-calendar objective, not a claim of equal market exposure or volatility.",
        "",
        "| Year | Answers added, net | Prepared + prices, net | All eligible calls, net | SPY |",
        "|---|---:|---:|---:|---:|",
    ]
    for year, metrics in verdict["annual_net_metrics"].items():
        cells = [
            f"{metrics[n]['total_return']:.2%}" if n in metrics else "incomplete"
            for n in ["primary", "baseline", "all_events", "SPY"]
        ]
        lines.append(f"| {year} | " + " | ".join(cells) + " |")
    diagnostics = verdict["paired_forecast_diagnostics"]
    b = diagnostics["baseline_prediction"]
    a = diagnostics["augmented_prediction"]
    improvement = 1 - a["mean_squared_error"] / b["mean_squared_error"]
    lines += [
        "",
        f"On {a['events']:,} paired forward events, adding the answer text {'reduced' if improvement >= 0 else 'increased'} mean squared forecast error by **{abs(improvement):.2%}**. Baseline MSE: {b['mean_squared_error']:.8f}; augmented MSE: {a['mean_squared_error']:.8f}. The median absolute change in the predicted log return was {diagnostics['median_absolute_increment_bps']:.2f} bps. These are descriptive tests on exposed development history, not independent confirmation.",
        "",
    ]
    interval = primary["excess_mean_daily_95_interval"]
    if interval:
        lines += [
            f"The fixed five-session paired block-bootstrap 95% interval for mean daily strategy-minus-SPY return was [{interval[0] * 10000:.2f}, {interval[1] * 10000:.2f}] bps. This interval is not a correction for the repository's many previous strategy searches.",
            "",
        ]
    if bounded:
        lines += [
            "## Missing prices and the rejection bound",
            "",
            "Nine targeted repeats of the original five-minute requests and nine one-minute requests through the same SIP access did not recover the required prices. The primary inputs and missing decisions were preserved. The bound protocol was saved before inspecting portfolio performance.",
            "",
            "For each unknown portfolio day, the bound gives all capital to whichever eligible stock had the largest cached daily high/low ratio. It permits buying at the low and selling at the high even if their chronological order makes that impossible, charges no costs on that day, and also permits cash. Every funded long-only basket in the frozen universe is bounded above by that factor if the daily extrema cover its fills. Multiply those factors by the known-day portfolio factors; no missing price or actual return is imputed.",
            "",
            "The daily files were already available locally and were hashed before use. Their OHLC ordering and range consistency with observed intraday bars were checked. This is not independent certification of a second vendor. The bound holds the already-fitted available-data model and known-day trades fixed; it does not bound a different model retrained on repaired observations or a different strategy.",
            "",
            "| Portfolio | Known-day net product | Optimistic full-calendar ceiling | Ceiling with all costs removed | Unknown dates |",
            "|---|---:|---:|---:|---:|",
        ]
        for name, label in [
            ("primary", "Answers added"),
            ("baseline", "Prepared + prices"),
            ("all_events", "All eligible calls"),
        ]:
            r = bounded["portfolios"][name]
            lines.append(
                f"| {label} | ${r['independent_known_day_reconciliation']['net']['known_day_product_value']:.2f} | ${r['optimistic_full_calendar_upper_bounds']['net']:.2f} | ${r['optimistic_full_calendar_upper_bounds']['reference']:.2f} | {len(r['missing_dates'])} |"
            )
        lines += [
            "",
            "Primary unknown dates: "
            + ", ".join(bounded["portfolios"]["primary"]["missing_dates"])
            + ".",
            "",
            bounded["economic_interpretation"],
            "",
        ]
    lines += [
        "## What this result establishes",
        "",
        "This is a conditional historical screen. The fixed universe was chosen retrospectively from existing files, and present-day publisher metadata does not independently establish original text vintages. Excluding revised or unparseable pages is retrospective sample selection. Complete share/cash accounting for the admitted corpus does not remove those biases. A failure rejects this exact implementation on the available sample; it does not prove that every way of analyzing earnings calls lacks an edge.",
        "",
        "The declared economic objective governs the stop. If the net portfolio fails SPY, no different vocabulary, threshold, sign, timing, leverage or rescued variant is tried. Quotes, latency replay and 2024+ candidate outcomes are not opened after a clear failure. A positive conditional bar screen would still require incremental value, original source vintages, a point-in-time universe, executable quotes and fresh confirmation.",
        "",
        "## Verification and provenance",
        "",
        f"Eleven focused tests passed before fitting real outcomes, covering text isolation, explicit management attribution, historical fitting, held-out vocabulary/target isolation, feature completion times, missing-data handling, calendar timing and independent share/cash arithmetic. Two additional tests check that the bound covers funded stock/cash baskets and rejects invalid extrema. The {sum('training_last_day' in m for m in models)} monthly fits record their training ranges, event identity hashes, vocabularies, IDF hashes and coefficient hashes. Known-day share purchases and sale proceeds were reconciled independently with Decimal arithmetic for gross, net and stress products; actual full-calendar equity remains unknown where inputs are missing. All {len(verdict['historical_inputs_unchanged'])} protected historical input hashes remained unchanged.",
        "",
        "The initial source enumeration omitted older conference-call and truncated slugs. It was repaired to use the publisher's transcript directory before any market outcomes. A source-only attribution audit then found that the legacy pilot parser could label researchers and reporters as management when their title omitted 'analyst'. An additional explicit-management-role gate now rejects those ambiguous documents. Both the original implementation freeze and its pre-outcome repair record are retained. A scheduling helper fetched already-complete training years while later text downloaded; final price collection reused only exact matching request parameters. These changes did not alter the frozen trading or model rules.",
        "",
        "Public method/source references: [Motley Fool transcript source](https://www.fool.com/earnings/call-transcripts/2023/07/25/microsoft-msft-q4-2023-earnings-call-transcript/), [Alpaca historical-data access and bar conventions](https://docs.alpaca.markets/us/docs/market-data-faq), [historical bars API](https://docs.alpaca.markets/us/reference/stockbars), [Ridge regression documentation](https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.Ridge.html). These references support the data and method, not the strategy's profitability.",
        "",
        "Local records:",
        "",
    ]
    for name in [
        "specification.json",
        "implementation_freeze.json",
        "implementation_freeze_repair_1.json",
        "implementation_notes.json",
        "source_summary.json",
        "source_audit.json",
        "market_request_plan.json",
        "market_retrieval.json",
        "market_coverage.json",
        "panel_audit.json",
        "model_audits.json",
        "forecasts.json",
        "primary_evaluation.json",
        "baseline_evaluation.json",
        "all_events_evaluation.json",
        "verdict.json",
        "minute_gap_probe_audit.json",
        "missing_day_bound_protocol.json",
        "missing_day_bound_inputs.json",
        "bounded_economic_verdict.json",
    ]:
        lines.append(f"- [{name}]({(OUT / name).as_posix()})")
    (OUT / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    frozen = read("implementation_freeze_repair_1.json")
    completion = {
        "implementation_unchanged_since_freeze": {
            p: sha((ROOT / p).read_bytes()) == h for p, h in frozen["hashes"].items()
        },
        "source_retrieval_statuses": dict(Counter(str(r.get("status")) for r in raw_text)),
        "source_documents_admitted": sum(not r["problems"] for r in audit),
        "model_months": len(models),
        "source_original_vintage_verified": False,
        "strategy_status": status,
        "actual_full_calendar_equity_known": primary["complete_equity"],
        "report_path": str(OUT / "REPORT.md"),
        "report_sha256": sha((OUT / "REPORT.md").read_bytes()),
    }
    save("completion_checks.json", completion)
    print(json.dumps(completion, indent=2), flush=True)


if __name__ == "__main__":
    main()
