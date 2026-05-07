"""
Client Library Generation - Issue 128 Advanced FastAPI Features
Auto-generated client libraries for multiple programming languages

This module serves as the main aggregator, delegating to specialized generators.
"""

import os
import tempfile
from typing import Any, Dict, Optional

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
from src.api.fastapi.client_javascript_generator import generate_javascript_client
from src.api.fastapi.client_models import (
    ClientConfig,
    ClientLanguage,
    GeneratedClient,
)
from src.api.fastapi.client_openapi_generator import (
    generate_custom_client,
    generate_openapi_client,
)
from src.api.fastapi.client_python_generator import generate_python_client
from src.api.fastapi.client_typescript_generator import generate_typescript_client
from src.utils.logger import get_logger

logger = get_logger("mvidarr.api.client_generation")


class ClientLibraryGenerator:
    """Generates client libraries from OpenAPI specification"""

    def __init__(self, app: FastAPI, config: Optional[Dict] = None):
        self.app = app
        self.config = config or {}

        # Generator configuration - use secure temp directory
        default_output_dir = os.path.join(tempfile.gettempdir(), "mvidarr_clients")
        self.output_base_dir = self.config.get("output_dir", default_output_dir)
        self.openapi_generator_jar = self.config.get("generator_jar_path")
        self.include_examples = self.config.get("include_examples", True)
        self.generate_docs = self.config.get("generate_docs", True)

        # Default client configurations
        self.default_configs = {
            ClientLanguage.PYTHON: ClientConfig(
                language=ClientLanguage.PYTHON,
                package_name="mvidarr-client",
                version="1.0.0",
                description="Python client library for MVidarr API",
                author="MVidarr Team",
                license="MIT",
                output_dir="python-client",
                additional_properties={
                    "projectName": "mvidarr-client",
                    "packageName": "mvidarr_client",
                    "packageVersion": "1.0.0",
                    "clientPackage": "mvidarr_client",
                    "generateSourceCodeOnly": "false",
                },
            ),
            ClientLanguage.JAVASCRIPT: ClientConfig(
                language=ClientLanguage.JAVASCRIPT,
                package_name="mvidarr-js-client",
                version="1.0.0",
                description="JavaScript client library for MVidarr API",
                author="MVidarr Team",
                license="MIT",
                output_dir="javascript-client",
                additional_properties={
                    "projectName": "mvidarr-js-client",
                    "clientPackage": "mvidarr-client",
                    "npmName": "mvidarr-js-client",
                    "npmVersion": "1.0.0",
                },
            ),
            ClientLanguage.TYPESCRIPT: ClientConfig(
                language=ClientLanguage.TYPESCRIPT,
                package_name="mvidarr-ts-client",
                version="1.0.0",
                description="TypeScript client library for MVidarr API",
                author="MVidarr Team",
                license="MIT",
                output_dir="typescript-client",
                additional_properties={
                    "projectName": "mvidarr-ts-client",
                    "npmName": "mvidarr-ts-client",
                    "npmVersion": "1.0.0",
                    "supportsES6": "true",
                },
            ),
            ClientLanguage.JAVA: ClientConfig(
                language=ClientLanguage.JAVA,
                package_name="mvidarr-java-client",
                version="1.0.0",
                description="Java client library for MVidarr API",
                author="MVidarr Team",
                license="MIT",
                output_dir="java-client",
                additional_properties={
                    "groupId": "com.mvidarr",
                    "artifactId": "mvidarr-client",
                    "artifactVersion": "1.0.0",
                    "clientPackage": "com.mvidarr.client",
                },
            ),
            ClientLanguage.GO: ClientConfig(
                language=ClientLanguage.GO,
                package_name="mvidarr-go-client",
                version="1.0.0",
                description="Go client library for MVidarr API",
                author="MVidarr Team",
                license="MIT",
                output_dir="go-client",
                additional_properties={
                    "packageName": "mvidarr",
                    "clientPackage": "mvidarr",
                },
            ),
        }

    def get_openapi_spec(self) -> Dict[str, Any]:
        """Get OpenAPI specification from FastAPI app"""
        return get_openapi(
            title="MVidarr API",
            version="2.0.0",
            description="Consumer-focused music video collection management API",
            routes=self.app.routes,
            servers=[
                {"url": "http://localhost:5000", "description": "Local development"},
                {"url": "https://api.mvidarr.local", "description": "Local network"},
            ],
        )

    async def generate_client(
        self,
        language: ClientLanguage,
        custom_config: Optional[ClientConfig] = None,
        output_dir: Optional[str] = None,
    ) -> GeneratedClient:
        """Generate client library for specified language"""
        try:
            # Use custom config or default
            config = custom_config or self.default_configs.get(language)
            if not config:
                raise ValueError(f"No configuration available for {language.value}")

            # Set output directory
            if output_dir:
                config.output_dir = output_dir

            full_output_path = os.path.join(self.output_base_dir, config.output_dir)
            os.makedirs(full_output_path, exist_ok=True)

            # Get OpenAPI spec
            spec = self.get_openapi_spec()

            # Generate based on language - delegate to specialized generators
            if language == ClientLanguage.PYTHON:
                return await generate_python_client(
                    spec, config, full_output_path, self.include_examples
                )
            elif language == ClientLanguage.JAVASCRIPT:
                return await generate_javascript_client(
                    spec, config, full_output_path, self.include_examples
                )
            elif language == ClientLanguage.TYPESCRIPT:
                return await generate_typescript_client(
                    spec, config, full_output_path, self.include_examples
                )
            elif language in [ClientLanguage.JAVA, ClientLanguage.GO]:
                return await generate_openapi_client(
                    spec, config, full_output_path, self.openapi_generator_jar
                )
            else:
                return await generate_custom_client(spec, config, full_output_path)

        except Exception as e:
            logger.error(f"Failed to generate {language.value} client: {e}")
            raise

    async def generate_all_clients(self) -> Dict[ClientLanguage, GeneratedClient]:
        """Generate client libraries for all supported languages"""
        results = {}

        for language in [
            ClientLanguage.PYTHON,
            ClientLanguage.JAVASCRIPT,
            ClientLanguage.TYPESCRIPT,
        ]:
            try:
                client = await self.generate_client(language)
                results[language] = client
                logger.info(f"Generated {language.value} client successfully")
            except Exception as e:
                logger.error(f"Failed to generate {language.value} client: {e}")

        return results


# Global generator instance
_client_generator = None


def get_client_generator(
    app: FastAPI, config: Optional[Dict] = None
) -> ClientLibraryGenerator:
    """Get global client generator instance"""
    global _client_generator

    if _client_generator is None:
        _client_generator = ClientLibraryGenerator(app, config)

    return _client_generator
