"""Find duplicate values in top_2000_unmapped column A and CUP_raw_data CUP_NAME."""

import pandas as pd

# Read data
top = pd.read_excel("localdata/top_2000_unmapped.xlsx")
cup = pd.read_excel("localdata/CUP_raw_data.xlsx")

# --- Duplicates in top_2000_unmapped column A ---
a_col = top["A"].dropna()
a_dupes = a_col[a_col.duplicated(keep=False)].sort_values()

print("=== Duplicates in top_2000_unmapped (column A) ===")
if a_dupes.empty:
    print("  No duplicates found.")
else:
    for name, count in a_col.value_counts()[a_col.value_counts() > 1].sort_index().items():
        print(f"  {name} (x{count})")
    print(f"\n  Total: {a_dupes.nunique()} duplicate names, {len(a_dupes)} total rows")

print()

# --- Duplicates in CUP_raw_data CUP_NAME ---
b_col = cup["CUP_NAME"].dropna()
b_dupes = b_col[b_col.duplicated(keep=False)].sort_values()

print("=== Duplicates in CUP_raw_data (CUP_NAME) ===")
if b_dupes.empty:
    print("  No duplicates found.")
else:
    for name, count in b_col.value_counts()[b_col.value_counts() > 1].sort_index().items():
        print(f"  {name} (x{count})")
    print(f"\n  Total: {b_dupes.nunique()} duplicate names, {len(b_dupes)} total rows")
