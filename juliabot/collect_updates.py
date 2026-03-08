import re
import subprocess
from datetime import datetime
from typing import List, Optional

class CommitInfo:
    """Representa informações de um commit."""
    
    def __init__(self, hash: str, message: str, author: str, date: str):
        self.hash = hash
        self.message = message
        self.author = author
        self.date = date
        self.type = self._categorize_commit()
    
    def _categorize_commit(self) -> str:
        """Categoriza o commit baseado na mensagem."""
        message_lower = self.message.lower()
        
        # Conventional Commits
        if re.match(r'^feat(\(.+\))?:', self.message):
            return 'feature'
        elif re.match(r'^fix(\(.+\))?:', self.message):
            return 'fix'
        elif re.match(r'^docs(\(.+\))?:', self.message):
            return 'docs'
        elif re.match(r'^refactor(\(.+\))?:', self.message):
            return 'refactor'
        elif re.match(r'^test(\(.+\))?:', self.message):
            return 'test'
        elif re.match(r'^chore(\(.+\))?:', self.message):
            return 'chore'
        
        if any(word in message_lower for word in ['add', 'implement', 'create', 'introduce', 'feature']):
            return 'feature'
        elif any(word in message_lower for word in ['fix', 'resolve']):
            return 'fix'
        elif any(word in message_lower for word in ['improve', 'optimize', 'refactor', 'update']):
            return 'improvement'
        elif any(word in message_lower for word in ['remove', 'delete', 'cleanup']):
            return 'removal'
        
        return 'other'
    
    def get_short_message(self, max_length: int = 100) -> str:
        """Retorna a mensagem truncada se necessário."""
        if len(self.message) <= max_length:
            return self.message
        return self.message[:max_length-3] + '...'


class UpdateCollector:
    """Coleta e formata atualizações do git."""
    
    CATEGORY_ICONS = {
        'feature': '✨',
        'fix': '🐛',
        'improvement': '⚡',
        'refactor': '♻️',
        'docs': '📝',
        'test': '✅',
        'chore': '🔧',
        'removal': '🗑️',
        'other': '📌'
    }
    
    CATEGORY_NAMES = {
        'feature': 'Novidades',
        'fix': 'Correções',
        'improvement': 'Melhorias',
        'refactor': 'Refatorações',
        'docs': 'Documentação',
        'test': 'Testes',
        'chore': 'Manutenção',
        'removal': 'Remoções',
        'other': 'Outras Mudanças'
    }
    
    @staticmethod
    def run_git_command(command: List[str]) -> str:
        """Executa um comando git e retorna a saída."""
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=True
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            raise Exception(f"Erro ao executar comando git: {e.stderr}")
    
    @staticmethod
    def get_latest_tag() -> Optional[str]:
        """Retorna a última tag git ou None se não houver tags."""
        try:
            tag = UpdateCollector.run_git_command(['git', 'describe', '--tags', '--abbrev=0'])
            return tag if tag else None
        except:
            return None
    
    @staticmethod
    def get_commits_since_tag(tag: Optional[str] = None) -> List[CommitInfo]:
        """Coleta commits desde uma tag específica ou desde a última tag."""
        if tag is None:
            tag = UpdateCollector.get_latest_tag()
        
        if tag:
            git_range = f'{tag}..HEAD'
        else:
            git_range = 'HEAD'
        
        # Formato: hash|message|author|date
        log_format = '--pretty=format:%h|%s|%an|%ar'
        
        try:
            output = UpdateCollector.run_git_command([
                'git', 'log', git_range, log_format, '--no-merges'
            ])
        except:
            return []
        
        if not output:
            return []
        
        commits = []
        for line in output.split('\n'):
            if not line.strip():
                continue
            
            parts = line.split('|', 3)
            if len(parts) == 4:
                hash, message, author, date = parts
                commits.append(CommitInfo(hash, message, author, date))
        
        return commits
    
    @staticmethod
    def get_commits_since_date(date_str: str) -> List[CommitInfo]:
        """Coleta commits desde uma data específica (formato: YYYY-MM-DD)."""
        log_format = '--pretty=format:%h|%s|%an|%ar'
        
        try:
            output = UpdateCollector.run_git_command([
                'git', 'log', f'--since={date_str}', log_format, '--no-merges'
            ])
        except:
            return []
        
        if not output:
            return []
        
        commits = []
        for line in output.split('\n'):
            if not line.strip():
                continue
            
            parts = line.split('|', 3)
            if len(parts) == 4:
                hash, message, author, date = parts
                commits.append(CommitInfo(hash, message, author, date))
        
        return commits
    
    @staticmethod
    def get_commits_since_hash(hash: str) -> List[CommitInfo]:
        """Coleta commits desde um hash específico."""
        log_format = '--pretty=format:%h|%s|%an|%ar'
        
        try:
            output = UpdateCollector.run_git_command([
                'git', 'log', f'{hash}..HEAD', log_format, '--no-merges'
            ])
        except:
            return []
        
        if not output:
            return []
        
        commits = []
        for line in output.split('\n'):
            if not line.strip():
                continue
            
            parts = line.split('|', 3)
            if len(parts) == 4:
                hash, message, author, date = parts
                commits.append(CommitInfo(hash, message, author, date))
        
        return commits


    @staticmethod
    def get_last_n_commits(n: int = 10) -> List[CommitInfo]:
        """Coleta os últimos N commits."""
        log_format = '--pretty=format:%h|%s|%an|%ar'
        
        try:
            output = UpdateCollector.run_git_command([
                'git', 'log', f'-{n}', log_format, '--no-merges'
            ])
        except:
            return []
        
        if not output:
            return []
        
        commits = []
        for line in output.split('\n'):
            if not line.strip():
                continue
            
            parts = line.split('|', 3)
            if len(parts) == 4:
                hash, message, author, date = parts
                commits.append(CommitInfo(hash, message, author, date))
        
        return commits
    
    @staticmethod
    def group_commits_by_type(commits: List[CommitInfo]) -> dict:
        """Agrupa commits por tipo/categoria."""
        grouped = {}
        for commit in commits:
            if commit.type not in grouped:
                grouped[commit.type] = []
            grouped[commit.type].append(commit)

        ordered_grouped = {key: grouped[key] for key in UpdateCollector.CATEGORY_NAMES.keys() if key in grouped}
    
        return ordered_grouped
    

    @staticmethod
    def format_text(commits: List[CommitInfo], grouped: bool = True) -> str:
        """Formata commits em texto simples."""
        if not commits:
            return "Nenhum commit encontrado."
        
        output = []
        
        if grouped:
            grouped_commits = UpdateCollector.group_commits_by_type(commits)
            
            for type_key in ['feature', 'improvement', 'fix', 'refactor', 'docs', 'test', 'chore', 'removal', 'other']:
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
        
        return '\n'.join(output)
    
    @staticmethod
    def format_markdown(commits: List[CommitInfo], grouped: bool = True, version: Optional[str] = None) -> str:
        """Formata commits em markdown."""
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
            
            for type_key in ['feature', 'improvement', 'fix', 'refactor', 'docs', 'test', 'chore', 'removal', 'other']:
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
        
        return '\n'.join(output)
    

    @staticmethod
    def get_category_name(category_key: str) -> str:
        """Retorna o nome legível da categoria."""
        return UpdateCollector.CATEGORY_NAMES.get(category_key, 'Outras Mudanças')


    @staticmethod
    def get_category_icon(category_key: str) -> str:
        """Retorna o ícone associado à categoria."""
        return UpdateCollector.CATEGORY_ICONS.get(category_key, '📌')
