"""Match company names from top_2000_unmapped column A against CUP_raw_data CUP_NAME."""

import pandas as pd
from bizmatch import Matcher

# Read data
top = pd.read_excel("localdata/top_2000_unmapped.xlsx")
cup = pd.read_excel("localdata/CUP_raw_data.xlsx")

a_names = top["A"].dropna().tolist()
b_names = cup["CUP_NAME"].dropna().tolist()

print(f"A names (top_2000_unmapped): {len(a_names)}")
print(f"B names (CUP_raw_data): {len(b_names)}")

# Create matcher and preprocess B list
matcher = Matcher()
matcher.preprocess_b(b_names)

# Match all A names against B
results = matcher.match_all(a_names)

# Build output dataframe
rows = []
for r in results:
    rows.append({
        "A_name": r.a_name,
        "matched_CUP_NAME": r.b_name,
        "matched_CUP_ID": cup.iloc[r.b_id]["CUP_ID"] if r.b_id is not None else None,
        "decision": r.decision,
        "score": round(r.score, 4),
        "runner_up_score": round(r.runner_up_score, 4) if r.runner_up_score is not None else None,
        "reasons": "; ".join(r.reasons),
    })

df_out = pd.DataFrame(rows)

# Summary
match_count = (df_out["decision"] == "MATCH").sum()
no_match_count = (df_out["decision"] == "NO_MATCH").sum()
review_count = (df_out["decision"] == "REVIEW").sum()

print(f"\nResults: MATCH={match_count}, NO_MATCH={no_match_count}, REVIEW={review_count}")

# Save to Excel
output_path = "localdata/matching_results.xlsx"
df_out.to_excel(output_path, index=False)
print(f"Saved to: {output_path}")
