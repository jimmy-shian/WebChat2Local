import os
import re
import subprocess
from typing import Dict, List, Optional

class ContextBudgetManager:
    def __init__(self, workspace_root: str, max_tokens: int = 8000):
        self.workspace_root = workspace_root
        self.max_tokens = max_tokens
        
    def get_git_diff(self) -> str:
        try:
            result = subprocess.run(
                ["git", "status", "--porcelain=v2"],
                cwd=self.workspace_root,
                capture_output=True,
                text=True,
                check=True
            )
            return result.stdout
        except (subprocess.CalledProcessError, FileNotFoundError):
            return "Git repository not found or error retrieving status."

    def get_repo_map(self, max_depth: int = 2) -> str:
        output = []
        for root, dirs, files in os.walk(self.workspace_root):
            rel_path = os.path.relpath(root, self.workspace_root)
            depth = rel_path.count(os.sep) if rel_path != "." else 0
            
            if depth > max_depth:
                dirs.clear()
                continue
                
            dirs[:] = [d for d in dirs if not d.startswith('.') and d != '__pycache__']
            
            indent = "  " * depth
            output.append(f"{indent}{os.path.basename(root) if rel_path != '.' else '.'}/")
            for f in files:
                if not f.startswith('.'):
                    output.append(f"{indent}  {f}")
                    
        return "\n".join(output)

    def resolve_file_references(self, prompt: str) -> List[Dict[str, str]]:
        refs = []
        matches = re.findall(r'@([a-zA-Z0-9_./-]+)', prompt)
        for match in matches:
            filepath = os.path.join(self.workspace_root, match)
            if os.path.exists(filepath) and os.path.isfile(filepath):
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        refs.append({"path": match, "content": f.read()})
                except Exception:
                    pass
        return refs
        
    def assemble_context(self, active_file: str = None, selected_code: str = None, 
                         pinned_files: List[str] = None, custom_rules: str = None, 
                         prompt: str = "") -> dict:
        context = {
            "system_note": custom_rules or "",
            "files": [],
            "git_status": self.get_git_diff(),
            "repo_map": self.get_repo_map(),
            "estimated_tokens": 0
        }
        
        file_refs = self.resolve_file_references(prompt)
        for ref in file_refs:
            context["files"].append(ref)
            
        if pinned_files:
            for pf in pinned_files:
                path = os.path.join(self.workspace_root, pf)
                if os.path.exists(path):
                    with open(path, 'r', encoding='utf-8') as f:
                        context["files"].append({"path": pf, "content": f.read()})
                        
        if active_file:
            path = os.path.join(self.workspace_root, active_file)
            if os.path.exists(path):
                with open(path, 'r', encoding='utf-8') as f:
                    context["files"].append({"path": active_file, "content": f.read(), "selected": selected_code})
                    
        total_chars = len(context["system_note"]) + len(context["git_status"]) + len(context["repo_map"])
        for file in context["files"]:
            total_chars += len(file["content"])
            
        context["estimated_tokens"] = total_chars // 4
        
        if context["estimated_tokens"] > self.max_tokens:
            context["repo_map"] = ""
            
        return context
