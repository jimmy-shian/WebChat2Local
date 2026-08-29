import os

class WorkspaceSecurityError(Exception):
    pass

class WorkspaceSecurityPolicy:
    def __init__(self, workspace_root: str):
        self.workspace_root = os.path.abspath(workspace_root)

    def validate_path(self, relative_path: str) -> str:
        if os.path.isabs(relative_path):
            raise WorkspaceSecurityError("Absolute paths are not allowed.")
        if ".." in relative_path.split(os.sep) or ".." in relative_path.split("/"):
            raise WorkspaceSecurityError("Path traversal (..) is not allowed.")
        if os.name == 'nt':
            if relative_path.startswith("\\\\"):
                raise WorkspaceSecurityError("UNC paths are not allowed.")
            if ":" in relative_path:
                raise WorkspaceSecurityError("Drive letters are not allowed in relative paths.")

        full_path = os.path.abspath(os.path.join(self.workspace_root, relative_path))
        if not full_path.startswith(self.workspace_root):
            raise WorkspaceSecurityError("Path escapes workspace root.")
        return full_path

    def is_ignored(self, relative_path: str) -> bool:
        path = relative_path.replace("\\", "/")
        parts = path.split("/")
        
        ignore_dirs = {".git", "node_modules", ".venv", "dist", "build"}
        if any(part in ignore_dirs for part in parts):
            return True
        
        filename = parts[-1]
        if filename == ".env" or filename.startswith(".env."):
            return True
        if filename.endswith(".pem") or filename.endswith(".key"):
            return True
        if filename.startswith("credentials."):
            return True
            
        return False
