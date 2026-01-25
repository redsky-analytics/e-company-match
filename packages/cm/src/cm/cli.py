"""CLI tool for company name matching and duplicate detection."""

import argparse

import pandas as pd
import structlog

from cm.config import MatchConfig
from cm.logging import configure_logging
from cm.matcher import Matcher
from cm.normalize import normalize


def _build_config(args: argparse.Namespace) -> MatchConfig:
    """Build a MatchConfig from CLI args."""
    log = structlog.get_logger()
    config = MatchConfig()

    # Handle --no <category> flags
    categories = getattr(args, "no", None) or []
    if categories:
        from cm.designators import get_available_categories, load_category_words

        available = get_available_categories()
        for cat in categories:
            if cat not in available:
                print(f"Warning: category '{cat}' not found. Available: {', '.join(available)}")
            else:
                words = load_category_words(cat)
                log.info("strip_category_enabled", category=cat, word_count=len(words))

        config.normalization.strip_categories = categories

    return config


def _build_matcher(args: argparse.Namespace) -> Matcher:
    """Build a Matcher, optionally wiring up Gemini providers."""
    log = structlog.get_logger()
    log.info("build_matcher_start", no_gemini=args.no_gemini)
    config = _build_config(args)

    embedding_provider = None
    llm_provider = None

    if not args.no_gemini:
        from cm.gemini import GeminiEmbeddingProvider, GeminiLLMProvider, _make_client

        log.info("gemini_client_init")
        client = _make_client()
        embedding_provider = GeminiEmbeddingProvider(client)
        llm_provider = GeminiLLMProvider(client)
        config.embedding.enabled = True
        config.llm.enabled = True
        log.info(
            "gemini_providers_enabled",
            embedding_model=GeminiEmbeddingProvider.MODEL,
            llm_model=GeminiLLMProvider.MODEL,
        )

    return Matcher(
        config=config,
        llm_provider=llm_provider,
        embedding_provider=embedding_provider,
    )


def cmd_match(args: argparse.Namespace) -> None:
    log = structlog.get_logger()
    log.info("load_files_start", top=args.top, cup=args.cup)
    top = pd.read_excel(args.top)
    cup = pd.read_excel(args.cup)

    a_names = top["A"].dropna().tolist()
    b_names = cup["CUP_NAME"].dropna().tolist()

    log.info("files_loaded", a_count=len(a_names), b_count=len(b_names))

    matcher = _build_matcher(args)
    log.info("preprocess_b_start", b_count=len(b_names))
    matcher.preprocess_b(b_names)
    log.info("preprocess_b_done")

    if args.group:
        _match_group(matcher, a_names, cup, args.output, args.show)
    else:
        _match_individual(matcher, a_names, cup, args.output, args.show)


def _match_individual(
    matcher: Matcher, a_names: list[str], cup: pd.DataFrame, output: str, show: bool
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

    if show:
        _show_matches(df_out)

    _print_summary(df_out)
    _print_stats(matcher)
    df_out.to_excel(output, index=False)
    print(f"\nSaved to: {output}")


def _match_group(
    matcher: Matcher, a_names: list[str], cup: pd.DataFrame, output: str, show: bool
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

    if show:
        _show_matches(df_out)

    _print_summary(df_out)
    _print_stats(matcher)
    df_out.to_excel(output, index=False)
    print(f"\nSaved to: {output}")


def _show_matches(df: pd.DataFrame) -> None:
    """Display matches on screen."""
    matches = df[df["decision"] == "MATCH"].copy()
    if matches.empty:
        print("\n=== No matches found ===")
        return

    # Select columns to display
    display_cols = ["A_name", "matched_CUP_NAME", "score"]
    if "group_size" in matches.columns:
        display_cols.insert(1, "group_size")

    print(f"\n=== Matches ({len(matches)}) ===")
    print(matches[display_cols].to_string(index=False))


def _print_stats(matcher: Matcher) -> None:
    """Print matching statistics."""
    s = matcher.stats
    print("\n--- Statistics ---")
    print(f"A names: {s.a_count}")
    print(f"B names: {s.b_count}")
    print(f"Comparisons: {s.comparisons}")
    print(f"No candidates: {s.no_candidates}")
    if s.embedding_api_calls > 0 or s.embedding_cache_hits > 0:
        print(f"Embedding API calls: {s.embedding_api_calls}")
        print(f"Embedding cache hits: {s.embedding_cache_hits}")
    if s.llm_calls > 0:
        print(f"LLM calls: {s.llm_calls}")
        print(f"LLM overrides: {s.llm_overrides}")


def _print_summary(df: pd.DataFrame) -> None:
    # If group_size column exists, compute row-weighted counts
    if "group_size" in df.columns:
        match_rows = df.loc[df["decision"] == "MATCH", "group_size"].sum()
        no_match_rows = df.loc[df["decision"] == "NO_MATCH", "group_size"].sum()
        review_rows = df.loc[df["decision"] == "REVIEW", "group_size"].sum()
        print(f"\nResults (rows): MATCH={match_rows}, NO_MATCH={no_match_rows}, REVIEW={review_rows}")
    else:
        match_count = (df["decision"] == "MATCH").sum()
        no_match_count = (df["decision"] == "NO_MATCH").sum()
        review_count = (df["decision"] == "REVIEW").sum()
        print(f"\nResults: MATCH={match_count}, NO_MATCH={no_match_count}, REVIEW={review_count}")


def cmd_dupes(args: argparse.Namespace) -> None:
    config = _build_config(args)
    use_normalization = bool(config.normalization.strip_categories)

    top = pd.read_excel(args.top)
    cup = pd.read_excel(args.cup)

    # Duplicates in top_2000_unmapped column A
    a_col = top["A"].dropna()

    if use_normalization:
        # Group by normalized core_string
        a_normalized = {name: normalize(name, config).core_string for name in a_col}
        a_groups: dict[str, list[str]] = {}
        for orig, norm in a_normalized.items():
            a_groups.setdefault(norm, []).append(orig)

        print("=== Duplicates in top_2000_unmapped (column A) [normalized] ===")
        has_dupes = False
        for norm, originals in sorted(a_groups.items()):
            count = sum(1 for name in a_col if a_normalized.get(name) == norm)
            if count > 1:
                has_dupes = True
                unique_originals = sorted(set(originals))
                print(f"  {norm} (x{count})")
                for orig in unique_originals:
                    orig_count = list(a_col).count(orig)
                    print(f"    - {orig} (x{orig_count})")
        if not has_dupes:
            print("  No duplicates found.")
    else:
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

    if use_normalization:
        b_normalized = {name: normalize(name, config).core_string for name in b_col}
        b_groups: dict[str, list[str]] = {}
        for orig, norm in b_normalized.items():
            b_groups.setdefault(norm, []).append(orig)

        print("=== Duplicates in CUP_raw_data (CUP_NAME) [normalized] ===")
        has_dupes = False
        for norm, originals in sorted(b_groups.items()):
            count = sum(1 for name in b_col if b_normalized.get(name) == norm)
            if count > 1:
                has_dupes = True
                unique_originals = sorted(set(originals))
                print(f"  {norm} (x{count})")
                for orig in unique_originals:
                    orig_count = list(b_col).count(orig)
                    print(f"    - {orig} (x{orig_count})")
        if not has_dupes:
            print("  No duplicates found.")
    else:
        b_dupes = b_col[b_col.duplicated(keep=False)].sort_values()
        print("=== Duplicates in CUP_raw_data (CUP_NAME) ===")
        if b_dupes.empty:
            print("  No duplicates found.")
        else:
            for name, count in b_col.value_counts()[b_col.value_counts() > 1].sort_index().items():
                print(f"  {name} (x{count})")
            print(f"\n  Total: {b_dupes.nunique()} duplicate names, {len(b_dupes)} total rows")


def cmd_clean(args: argparse.Namespace) -> None:
    """Generate cleaned versions of names with different normalization levels."""
    from cm.config import MatchConfig
    from cm.designators import get_available_categories

    top = pd.read_excel(args.top)
    cup = pd.read_excel(args.cup)

    # Get available categories
    categories = get_available_categories()

    # Build configs: base, one per category, and all combined
    config_base = MatchConfig()

    category_configs: dict[str, MatchConfig] = {}
    for cat in categories:
        cfg = MatchConfig()
        cfg.normalization.strip_categories = [cat]
        category_configs[cat] = cfg

    config_all = MatchConfig()
    config_all.normalization.strip_categories = list(categories)

    def clean_names(names: list[str]) -> pd.DataFrame:
        rows = []
        for name in names:
            row = {
                "original": name,
                "normalized": normalize(name, config_base).core_string,
            }
            # Add column for each category
            for cat in categories:
                row[f"no_{cat}"] = normalize(name, category_configs[cat]).core_string
            # Add combined column
            if len(categories) > 1:
                row["no_all"] = normalize(name, config_all).core_string
            rows.append(row)
        return pd.DataFrame(rows)

    def filter_df(df: pd.DataFrame, search: str) -> pd.DataFrame:
        """Filter dataframe rows where any column contains search string (case-insensitive)."""
        search_lower = search.lower()
        mask = df.apply(
            lambda row: any(search_lower in str(val).lower() for val in row),
            axis=1,
        )
        return df[mask]

    # Process top file (column A)
    a_names = top["A"].dropna().tolist()
    df_a = clean_names(a_names)

    # Process cup file (CUP_NAME column)
    b_names = cup["CUP_NAME"].dropna().tolist()
    df_b = clean_names(b_names)

    # If filter specified, print matching rows to screen
    if args.filter:
        df_a_filtered = filter_df(df_a, args.filter)
        df_b_filtered = filter_df(df_b, args.filter)

        print(f"=== A names matching '{args.filter}' ({len(df_a_filtered)} results) ===")
        if not df_a_filtered.empty:
            print(df_a_filtered.to_string(index=False))
        else:
            print("  No matches found.")

        print()

        print(f"=== B names matching '{args.filter}' ({len(df_b_filtered)} results) ===")
        if not df_b_filtered.empty:
            print(df_b_filtered.to_string(index=False))
        else:
            print("  No matches found.")
    else:
        # Write to files
        df_a.to_excel(args.output_top, index=False)
        print(f"Cleaned {len(a_names)} A names -> {args.output_top}")

        df_b.to_excel(args.output_cup, index=False)
        print(f"Cleaned {len(b_names)} B names -> {args.output_cup}")


def main() -> None:
    # Parent parser with global options (inherited by all subcommands)
    parent_parser = argparse.ArgumentParser(add_help=False)
    parent_parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Set logging level (default: INFO)",
    )
    parent_parser.add_argument(
        "--no-gemini",
        action="store_true",
        help="Disable Gemini providers (deterministic only)",
    )
    parent_parser.add_argument(
        "--no",
        action="append",
        metavar="CATEGORY",
        help="Strip words from category (repeatable, e.g., --no location --no institution)",
    )

    # Main parser
    parser = argparse.ArgumentParser(
        description="Company name matching CLI",
        parents=[parent_parser],
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # match subcommand
    match_parser = subparsers.add_parser("match", parents=[parent_parser], help="Match company names")
    match_parser.add_argument("--group", action="store_true", help="Enable group-based matching")
    match_parser.add_argument("--show", action="store_true", help="Display matches on screen")
    match_parser.add_argument("--top", default="localdata/top_2000_unmapped.xlsx", help="Path to top 2000 file")
    match_parser.add_argument("--cup", default="localdata/CUP_raw_data.xlsx", help="Path to CUP raw data file")
    match_parser.add_argument("--output", default="localdata/matching_results.xlsx", help="Output file path")
    match_parser.set_defaults(func=cmd_match)

    # dupes subcommand
    dupes_parser = subparsers.add_parser("dupes", parents=[parent_parser], help="Find duplicate names")
    dupes_parser.add_argument("--top", default="localdata/top_2000_unmapped.xlsx", help="Path to top 2000 file")
    dupes_parser.add_argument("--cup", default="localdata/CUP_raw_data.xlsx", help="Path to CUP raw data file")
    dupes_parser.set_defaults(func=cmd_dupes)

    # clean subcommand
    clean_parser = subparsers.add_parser("clean", parents=[parent_parser], help="Generate cleaned name variants")
    clean_parser.add_argument("--top", default="localdata/top_2000_unmapped.xlsx", help="Path to top 2000 file")
    clean_parser.add_argument("--cup", default="localdata/CUP_raw_data.xlsx", help="Path to CUP raw data file")
    clean_parser.add_argument("--output-top", default="localdata/top_cleaned.xlsx", help="Output path for cleaned top file")
    clean_parser.add_argument("--output-cup", default="localdata/cup_cleaned.xlsx", help="Output path for cleaned cup file")
    clean_parser.add_argument("--filter", "-f", help="Filter and display names matching this string (case-insensitive)")
    clean_parser.set_defaults(func=cmd_clean)

    args = parser.parse_args()
    configure_logging(args.log_level)
    args.func(args)


if __name__ == "__main__":
    main()
