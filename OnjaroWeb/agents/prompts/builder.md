Develop the following feature for the web application. Your goal is a COMPLETE, FULLY WORKING result - not a shell or placeholder.

## Webapp directory: {webapp_dir}

## Feature to Build:
Title: {feature_title}
Description: {feature_description}

## Current Project State (including known gaps):
{state_summary}

## CLAUDE.md (Project Goals):
{claude_md}

## THE MOST IMPORTANT RULE - COMPLETENESS:
Every feature you build must be complete end-to-end. This means:

1. **If a page needs data** → create or extend the data file with real, meaningful content (not "Lorem ipsum", not empty arrays). For a Hungarian cycling site, write real Hungarian content that fits the target audience (45-60 year old male cyclists).

2. **If a new route/page is created** → make sure at least one existing page links to it with a real href (not "#").

3. **If a feature fixes broken links** → update ALL the broken links, not just one.

4. **If you add a list page** → add a detail page too, or vice versa.

5. **Never leave placeholder text** → "Hamarosan...", "Lorem ipsum", "Tartalom rövidesen" are forbidden. Write real content.

6. **Data first** → Before building UI, check if the required data exists. If not, create it first.

## Instructions:
1. Read the existing codebase in {webapp_dir} to understand the structure
2. Identify what data/connections are needed for the feature to work end-to-end
3. Create or extend data files with real Hungarian content if needed
4. Implement the UI/logic
5. Wire up all links and navigation so the feature is reachable
6. Verify the feature is complete: a user can actually USE it, not just see an empty shell
7. Add a small focused test if appropriate

Keep the scope focused but make what you do build genuinely complete and useful.