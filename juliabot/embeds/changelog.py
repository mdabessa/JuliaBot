"""Embed builders for changelog summaries.

This module converts categorized commit updates into a Discord embed suitable
for posting recent bot changes.
"""

from typing import List

from discord import Embed

from ..collect_updates import CommitInfo, UpdateCollector


def changelog_embed(updates: List[CommitInfo], color: int) -> Embed:
    """Build a changelog embed grouped by commit category.

    Commits are grouped using ``UpdateCollector.group_commits_by_type`` and the
    embed includes up to five short commit messages per category.

    Args:
        updates (List[CommitInfo]): Commit entries to render in the changelog.
        color (int): Discord embed color value.

    Returns:
        Embed: A formatted changelog embed with one field per category.
    """
    embed = Embed(
        title="Changelog",
        description="Últimas atualizações do Bot",
        color=color,
    )

    grouped_updates = UpdateCollector.group_commits_by_type(updates)

    for category, commits in grouped_updates.items():
        if not commits:
            continue

        category_name = UpdateCollector.get_category_name(category)
        category_icon = UpdateCollector.get_category_icon(category)
                        
        commit_list = []
        for commit in commits[:5]:
            commit_list.append(f"• {commit.get_short_message(70)}")

        embed.add_field(
            name=f"{category_icon} {category_name}",
            value="\n".join(commit_list),
            inline=False
        )

    return embed
