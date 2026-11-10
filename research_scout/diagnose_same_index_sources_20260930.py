"""Explain frozen source gates; does not alter signals or evaluate returns."""

import json

import numpy as np
import pandas as pd

from research.same_index_supply import Quotes
from research_scout.prepare_same_index_hft_20260930 import OUT, ROOT


def main():
    manifest = json.loads((OUT/"quote_manifest.json").read_text())
    rows = []
    for item in manifest["files"]:
        if not item["complete"]:
            continue
        quotes = Quotes(pd.read_parquet(ROOT/item["path"]))
        first = pd.Timestamp(item["date"]+" 09:32", tz="America/New_York").value
        grid = first+np.arange(600, dtype=np.int64)*250_000_000-100_000_000
        indices = quotes.indices(grid)
        assert np.all(indices >= 0)
        fields = {k: v[indices] for k, v in quotes.fields.items()}
        row = {"date": item["date"], "symbol": item["symbol"], "decisions": 600,
               "valid": int(quotes.valid[indices].sum()),
               "conflicting_ties": int(quotes.ambiguous[indices].sum()),
               "locked": int((fields["bid_price"] == fields["ask_price"]).sum()),
               "crossed": int((fields["bid_price"] > fields["ask_price"]).sum()),
               "nonpositive_prices_or_sizes": int(np.any(np.vstack([fields[k] <= 0 for k in ["bid_price", "ask_price", "bid_size", "ask_size"]]), axis=0).sum()),
               "non_regular_conditions": int((fields["conditions"] != '["R"]').sum()),
               "conditions": pd.Series(fields["conditions"]).value_counts().to_dict()}
        rows.append(row)
    result = {"rows": rows, "counts_nonexclusive": True, "policy_changed": False, "future_returns_evaluated": False}
    (OUT/"source_gate_diagnostics.json").write_text(json.dumps(result, indent=2)+"\n")
    print(json.dumps([r for r in rows if r["valid"] < 300]))


if __name__ == "__main__":
    main()
