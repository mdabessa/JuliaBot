import re
import subprocess
from datetime import datetime
from typing import List, Optional

import requests

from .config import GITHUB_REPOSITORY


class CommitInfo:
    """Represents the normalized metadata of a single Git commit.

    The instance stores the commit hash, subject line, author, and date,
    and automatically derives a category used by changelog formatting helpers.
    """

    def __init__(self, hash: str, message: str, author: str, date: str):
        self.hash = hash
        self.message = message
        self.author = author
        self.date = date
        self.type = self._categorize_commit()

    def _categorize_commit(self) -> str:
        """Categorize the commit based on its message.

        The method first checks for Conventional Commits prefixes (for example,
        ``feat:`` and ``fix(scope):``). If none matches, it falls back to keyword
        heuristics to infer a best-effort category.

        Returns:
            str: One of the internal category keys such as ``feature``, ``fix``,
            ``improvement``, ``refactor``, ``docs``, ``test``, ``chore``,
            ``removal``, or ``other``.
        """
        message_lower = self.message.lower()

        # Conventional Commits
        if re.match(r"^feat(\(.+\))?:", self.message):
            return "feature"
        elif re.match(r"^fix(\(.+\))?:", self.message):
            return "fix"
        elif re.match(r"^docs(\(.+\))?:", self.message):
            return "docs"
        elif re.match(r"^refactor(\(.+\))?:", self.message):
            return "refactor"
        elif re.match(r"^test(\(.+\))?:", self.message):
            return "test"
        elif re.match(r"^chore(\(.+\))?:", self.message):
            return "chore"

        if any(
            word in message_lower
            for word in ["add", "implement", "create", "introduce", "feature"]
        ):
            return "feature"
        elif any(word in message_lower for word in ["fix", "resolve"]):
            return "fix"
        elif any(
            word in message_lower
            for word in ["improve", "optimize", "refactor", "update"]
        ):
            return "improvement"
        elif any(word in message_lower for word in ["remove", "delete", "cleanup"]):
            return "removal"

        return "other"

    def get_short_message(self, max_length: int = 100) -> str:
        """Return the commit message truncated to a maximum length.

        Args:
            max_length (int, optional): Maximum number of characters allowed in
                the resulting string. Defaults to 100.

        Returns:
            str: The original message if it already fits; otherwise a truncated
            version ending with ``...``.
        """
        if len(self.message) <= max_length:
            return self.message
        return self.message[: max_length - 3] + "..."


class UpdateCollector:
    """Collect and format Git updates for changelog output.

    This utility class provides helpers to retrieve commit history ranges,
    classify commits into categories, and render the result in text or Markdown.
    """

    CATEGORY_ICONS = {
        "feature": "✨",
        "fix": "🐛",
        "improvement": "⚡",
        "refactor": "♻️",
        "docs": "📝",
        "test": "✅",
        "chore": "🔧",
        "removal": "🗑️",
        "other": "📌",
    }

    CATEGORY_NAMES = {
        "feature": "Novidades",
        "fix": "Correções",
        "improvement": "Melhorias",
        "refactor": "Refatorações",
        "docs": "Documentação",
        "test": "Testes",
        "chore": "Manutenção",
        "removal": "Remoções",
        "other": "Outras Mudanças",
    }

    GITHUB_API_TIMEOUT = 10

    @staticmethod
    def _to_commit_info(
        hash_value: str, message: str, author: str, date: str
    ) -> CommitInfo:
        """Build a ``CommitInfo`` from raw metadata values."""
        return CommitInfo(hash_value, message, author, date)

    @staticmethod
    def _parse_git_log_output(output: str) -> List[CommitInfo]:
        """Parse ``git log`` output into ``CommitInfo`` objects."""
        if not output:
            return []

        commits = []
        for line in output.split("\n"):
            if not line.strip():
                continue

            parts = line.split("|", 3)
            if len(parts) == 4:
                hash_value, message, author, date = parts
                commits.append(
                    UpdateCollector._to_commit_info(hash_value, message, author, date)
                )

        return commits

    @staticmethod
    def _fetch_commits_from_git(limit: Optional[int] = None) -> List[CommitInfo]:
        """Fetch commits from local Git history."""
        log_format = "--pretty=format:%h|%s|%an|%cs"
        command = ["git", "log", log_format, "--no-merges"]

        if limit is not None and limit > 0:
            command.insert(2, f"-{limit}")

        try:
            output = UpdateCollector.run_git_command(command)
            return UpdateCollector._parse_git_log_output(output)
        except Exception:
            return []

    @staticmethod
    def _fetch_commits_from_github(limit: Optional[int] = None) -> List[CommitInfo]:
        """Fetch commits from the public GitHub commits API."""
        if not GITHUB_REPOSITORY:
            return []

        commits = []
        page = 1
        per_page = 100

        while True:
            if limit is not None and len(commits) >= limit:
                break

            url = f"https://api.github.com/repos/{GITHUB_REPOSITORY}/commits"
            response = requests.get(
                url,
                params={"page": page, "per_page": per_page},
                timeout=UpdateCollector.GITHUB_API_TIMEOUT,
            )
            response.raise_for_status()

            data = response.json()
            if not data:
                break

            for item in data:
                sha = (item.get("sha") or "")[:7]
                commit_data = item.get("commit", {})
                message = (commit_data.get("message") or "").split("\n", 1)[0]
                author_data = commit_data.get("author", {})
                author = author_data.get("name") or "Unknown"
                date_raw = author_data.get("date") or ""
                date = date_raw[:10] if date_raw else "unknown date"

                commits.append(
                    UpdateCollector._to_commit_info(sha, message, author, date)
                )

                if limit is not None and len(commits) >= limit:
                    break

            if len(data) < per_page:
                break

            page += 1

        return commits

    @staticmethod
    def run_git_command(command: List[str]) -> str:
        """Run a Git command and return its standard output.

        Args:
            command (List[str]): Full command split into arguments, for example
                ``['git', 'log', '--oneline']``.

        Returns:
            str: Stripped standard output from the executed command.

        Raises:
            Exception: If the Git command fails. The exception message includes
            the command stderr output.
        """
        try:
            result = subprocess.run(command, capture_output=True, text=True, check=True)
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            raise Exception(f"Erro ao executar comando git: {e.stderr}")

    @staticmethod
    def get_latest_tag() -> Optional[str]:
        """Return the latest Git tag, if available.

        Returns:
            Optional[str]: The most recent tag name found by
            ``git describe --tags --abbrev=0``, or ``None`` when no tags exist
            or the lookup fails.
        """
        try:
            tag = UpdateCollector.run_git_command(
                ["git", "describe", "--tags", "--abbrev=0"]
            )
            return tag if tag else None
        except:
            return None

    @staticmethod
    def get_all_commits(limit: Optional[int] = None) -> List[CommitInfo]:
        """Collect commits using GitHub API when configured, else local Git.

        Args:
            limit (Optional[int], optional): Maximum number of commits to
                retrieve. Defaults to ``None`` (all available commits).

        Returns:
            List[CommitInfo]: Commit entries ordered from newest to oldest.
        """
        if GITHUB_REPOSITORY:
            try:
                commits = UpdateCollector._fetch_commits_from_github(limit=limit)
                if commits:
                    return commits
            except Exception:
                pass

        return UpdateCollector._fetch_commits_from_git(limit=limit)

    @staticmethod
    def get_commits_since_tag(tag: Optional[str] = None) -> List[CommitInfo]:
        """Collect commits since a specific tag or the latest tag.

        If ``tag`` is not provided, the method attempts to resolve the latest tag.
        When no tag is found, it falls back to collecting from ``HEAD`` history.

        Args:
            tag (Optional[str], optional): Tag to use as the lower bound in the
                commit range. Defaults to ``None``.

        Returns:
            List[CommitInfo]: Parsed commit entries ordered as returned by
            ``git log`` (most recent first). Returns an empty list on failure or
            when no commits are found.
        """
        if tag is None:
            tag = UpdateCollector.get_latest_tag()

        if not tag:
            return UpdateCollector.get_all_commits()

        try:
            tagged_hash = UpdateCollector.run_git_command(
                ["git", "rev-list", "-n", "1", tag]
            )
        except Exception:
            return UpdateCollector.get_all_commits()

        return UpdateCollector.get_commits_since_hash(tagged_hash[:7])

    @staticmethod
    def get_commits_since_date(date_str: str) -> List[CommitInfo]:
        """Collect commits created after a given date.

        Args:
            date_str (str): Date expression accepted by Git ``--since``. The
                expected format is ``YYYY-MM-DD``.

        Returns:
            List[CommitInfo]: Parsed commit entries from the selected range,
            excluding merge commits. Returns an empty list on failure or no data.
        """
        try:
            since_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            return []

        filtered = []
        for commit in UpdateCollector.get_all_commits():
            try:
                commit_date = datetime.strptime(commit.date[:10], "%Y-%m-%d").date()
            except ValueError:
                # Commits with relative/non-ISO date strings are skipped.
                continue

            if commit_date >= since_date:
                filtered.append(commit)

        return filtered

    @staticmethod
    def get_commits_since_hash(hash: str) -> List[CommitInfo]:
        """Collect commits after a specific commit hash.

        Args:
            hash (str): Commit hash used as the lower bound of the range
                (``<hash>..HEAD``).

        Returns:
            List[CommitInfo]: Parsed commit entries, excluding merge commits.
            Returns an empty list if command execution or parsing fails.
        """
        all_commits = UpdateCollector.get_all_commits()
        normalized_hash = hash.strip().lower()

        if not normalized_hash:
            return all_commits

        for index, commit in enumerate(all_commits):
            if commit.hash.lower().startswith(normalized_hash):
                return all_commits[:index]

        return all_commits

    @staticmethod
    def get_last_n_commits(n: int = 10) -> List[CommitInfo]:
        """Collect the most recent ``n`` non-merge commits.

        Args:
            n (int, optional): Maximum number of commits to retrieve. Defaults
                to 10.

        Returns:
            List[CommitInfo]: Parsed commit entries ordered from newest to
            oldest. Returns an empty list on failure or no data.
        """
        if n <= 0:
            return []
        return UpdateCollector.get_all_commits(limit=n)

    @staticmethod
    def group_commits_by_type(commits: List[CommitInfo]) -> dict:
        """Group commits by category and preserve configured category order.

        Args:
            commits (List[CommitInfo]): Commit objects to group.

        Returns:
            dict: Mapping of ``category_key -> List[CommitInfo]`` containing only
            categories present in ``commits``, ordered according to
            ``CATEGORY_NAMES``.
        """
        grouped = {}
        for commit in commits:
            if commit.type not in grouped:
                grouped[commit.type] = []
            grouped[commit.type].append(commit)

        ordered_grouped = {
            key: grouped[key]
            for key in UpdateCollector.CATEGORY_NAMES.keys()
            if key in grouped
        }

        return ordered_grouped

    @staticmethod
    def format_text(commits: List[CommitInfo], grouped: bool = True) -> str:
        """Format commits as plain text.

        Args:
            commits (List[CommitInfo]): Commits to include in the output.
            grouped (bool, optional): Whether to group entries by category.
                Defaults to ``True``.

        Returns:
            str: Human-readable text summary. Returns
            ``"Nenhum commit encontrado."`` when the input list is empty.
        """
        if not commits:
            return "Nenhum commit encontrado."

        output = []

        if grouped:
            grouped_commits = UpdateCollector.group_commits_by_type(commits)

            for type_key in [
                "feature",
                "improvement",
                "fix",
                "refactor",
                "docs",
                "test",
                "chore",
                "removal",
                "other",
            ]:
                if type_key in grouped_commits:
                    category_name = UpdateCollector.CATEGORY_NAMES[type_key]
                    icon = UpdateCollector.CATEGORY_ICONS[type_key]
                    output.append(f"\n{icon} {category_name}:")

                    for commit in grouped_commits[type_key]:
                        output.append(f"  • {commit.get_short_message()}")
        else:
            for commit in commits:
                icon = UpdateCollector.CATEGORY_ICONS[commit.type]
                output.append(f"{icon} {commit.get_short_message()}")

        return "\n".join(output)

    @staticmethod
    def format_markdown(
        commits: List[CommitInfo], grouped: bool = True, version: Optional[str] = None
    ) -> str:
        """Format commits as a Markdown changelog section.

        Args:
            commits (List[CommitInfo]): Commits to include in the output.
            grouped (bool, optional): Whether to group entries by category.
                Defaults to ``True``.
            version (Optional[str], optional): Version label used in the main
                heading. When ``None``, a generic ``# Changelog`` heading is used.

        Returns:
            str: Markdown-formatted changelog with commit hashes. Returns
            ``"Nenhum commit encontrado."`` when the input list is empty.
        """
        if not commits:
            return "Nenhum commit encontrado."

        output = []

        if version:
            output.append(f"# Versão {version}\n")
        else:
            output.append(f"# Changelog\n")

        output.append(f"*{len(commits)} mudanças*\n")

        if grouped:
            grouped_commits = UpdateCollector.group_commits_by_type(commits)

            for type_key in [
                "feature",
                "improvement",
                "fix",
                "refactor",
                "docs",
                "test",
                "chore",
                "removal",
                "other",
            ]:
                if type_key in grouped_commits:
                    category_name = UpdateCollector.CATEGORY_NAMES[type_key]
                    icon = UpdateCollector.CATEGORY_ICONS[type_key]
                    output.append(f"\n## {icon} {category_name}\n")

                    for commit in grouped_commits[type_key]:
                        output.append(f"- {commit.get_short_message()} `{commit.hash}`")
        else:
            output.append("\n## Mudanças\n")
            for commit in commits:
                icon = UpdateCollector.CATEGORY_ICONS[commit.type]
                output.append(f"- {icon} {commit.get_short_message()} `{commit.hash}`")

        return "\n".join(output)

    @staticmethod
    def get_category_name(category_key: str) -> str:
        """Return the human-readable label for a category key.

        Args:
            category_key (str): Internal category identifier.

        Returns:
            str: Display name for the category, or ``'Outras Mudanças'`` as a
            fallback for unknown keys.
        """
        return UpdateCollector.CATEGORY_NAMES.get(category_key, "Outras Mudanças")

    @staticmethod
    def get_category_icon(category_key: str) -> str:
        """Return the icon associated with a category key.

        Args:
            category_key (str): Internal category identifier.

        Returns:
            str: Emoji icon configured for the category, or ``'📌'`` for unknown
            keys.
        """
        return UpdateCollector.CATEGORY_ICONS.get(category_key, "📌")
