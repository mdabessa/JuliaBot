from typing import List, Optional

from discord import Embed

from ..collect_updates import CommitInfo, UpdateCollector


def changelog_embed(updates: List[CommitInfo], color: int) -> Embed:
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
