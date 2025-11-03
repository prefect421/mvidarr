"""
Client Library Generation Models - Issue 128 Advanced FastAPI Features
Data models and enums for client library generation
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional


class ClientLanguage(Enum):
    """Supported client library languages"""

    PYTHON = "python"
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"
    JAVA = "java"
    CSHARP = "csharp"
    GO = "go"
    RUST = "rust"
    PHP = "php"
    RUBY = "ruby"
    SWIFT = "swift"


@dataclass
class ClientConfig:
    """Client library configuration"""

    language: ClientLanguage
    package_name: str
    version: str
    description: str
    author: str
    license: str
    output_dir: str
    additional_properties: Dict[str, Any]


@dataclass
class GeneratedClient:
    """Generated client library information"""

    language: ClientLanguage
    package_name: str
    version: str
    output_path: str
    files_generated: List[str]
    examples_included: bool
    documentation_path: Optional[str]
    installation_instructions: str
