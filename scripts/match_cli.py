"""CLI tool for company name matching and duplicate detection."""

import argparse

import pandas as pd
from bizmatch import Matcher


def cmd_match(args: argparse.Namespace) -> None:
    top = pd.read_excel(args.top)
    cup = pd.read_excel(args.cup)

    a_names = top["A"].dropna().tolist()
    b_names = cup["CUP_NAME"].dropna().tolist()

    print(f"A names (top_2000_unmapped): {len(a_names)}")
    print(f"B names (CUP_raw_data): {len(b_names)}")

    matcher = Matcher()
    matcher.preprocess_b(b_names)

    if args.group:
        _match_group(matcher, a_names, cup, args.output)
    else:
        _match_individual(matcher, a_names, cup, args.output)


def _match_individual(
    matcher: Matcher, a_names: list[str], cup: pd.DataFrame, output: str
) -> None:
    results = matcher.match_all(a_names)

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
    _print_summary(df_out)
    df_out.to_excel(output, index=False)
    print(f"Saved to: {output}")


def _match_group(
    matcher: Matcher, a_names: list[str], cup: pd.DataFrame, output: str
) -> None:
    # Group A names by exact value
    groups: dict[str, int] = {}
    for name in a_names:
        groups[name] = groups.get(name, 0) + 1

    unique_names = list(groups.keys())
    print(f"Unique A groups: {len(unique_names)} (from {len(a_names)} rows)")

    # Match each unique name (all members of a group share the same value,
    # so matching once per unique name suffices for exact-duplicate groups)
    results = matcher.match_all(unique_names)

    rows = []
    for r in results:
        rows.append({
            "A_name": r.a_name,
            "group_size": groups[r.a_name],
            "matched_CUP_NAME": r.b_name,
            "matched_CUP_ID": cup.iloc[r.b_id]["CUP_ID"] if r.b_id is not None else None,
            "decision": r.decision,
            "score": round(r.score, 4),
            "runner_up_score": round(r.runner_up_score, 4) if r.runner_up_score is not None else None,
            "reasons": "; ".join(r.reasons),
        })

    df_out = pd.DataFrame(rows)
    _print_summary(df_out)
    df_out.to_excel(output, index=False)
    print(f"Saved to: {output}")


def _print_summary(df: pd.DataFrame) -> None:
    match_count = (df["decision"] == "MATCH").sum()
    no_match_count = (df["decision"] == "NO_MATCH").sum()
    review_count = (df["decision"] == "REVIEW").sum()
    print(f"\nResults: MATCH={match_count}, NO_MATCH={no_match_count}, REVIEW={review_count}")


def cmd_dupes(args: argparse.Namespace) -> None:
    top = pd.read_excel(args.top)
    cup = pd.read_excel(args.cup)

    # Duplicates in top_2000_unmapped column A
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

    # Duplicates in CUP_raw_data CUP_NAME
    b_col = cup["CUP_NAME"].dropna()
    b_dupes = b_col[b_col.duplicated(keep=False)].sort_values()

    print("=== Duplicates in CUP_raw_data (CUP_NAME) ===")
    if b_dupes.empty:
        print("  No duplicates found.")
    else:
        for name, count in b_col.value_counts()[b_col.value_counts() > 1].sort_index().items():
            print(f"  {name} (x{count})")
        print(f"\n  Total: {b_dupes.nunique()} duplicate names, {len(b_dupes)} total rows")


def main() -> None:
    parser = argparse.ArgumentParser(description="Company name matching CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # match subcommand
    match_parser = subparsers.add_parser("match", help="Match company names")
    match_parser.add_argument("--group", action="store_true", help="Enable group-based matching")
    match_parser.add_argument("--top", default="localdata/top_2000_unmapped.xlsx", help="Path to top 2000 file")
    match_parser.add_argument("--cup", default="localdata/CUP_raw_data.xlsx", help="Path to CUP raw data file")
    match_parser.add_argument("--output", default="localdata/matching_results.xlsx", help="Output file path")
    match_parser.set_defaults(func=cmd_match)

    # dupes subcommand
    dupes_parser = subparsers.add_parser("dupes", help="Find duplicate names")
    dupes_parser.add_argument("--top", default="localdata/top_2000_unmapped.xlsx", help="Path to top 2000 file")
    dupes_parser.add_argument("--cup", default="localdata/CUP_raw_data.xlsx", help="Path to CUP raw data file")
    dupes_parser.set_defaults(func=cmd_dupes)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
