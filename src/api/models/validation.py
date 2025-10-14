"""
Model Validation Utilities for MVidarr FastAPI
Phase 3 Week 32: Pydantic Validation and Models

Provides utilities for testing, validating, and working with Pydantic models.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Type, Union

from pydantic import BaseModel, ValidationError


class ModelValidator:
    """Utility class for validating Pydantic models"""

    @staticmethod
    def validate_model(
        model_class: Type[BaseModel], data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Validate data against a model and return detailed results

        Args:
            model_class: Pydantic model class
            data: Data to validate

        Returns:
            Dict with validation results including success, errors, and parsed data
        """
        result = {
            "success": False,
            "errors": [],
            "warnings": [],
            "parsed_data": None,
            "model_name": model_class.__name__,
        }

        try:
            # Attempt to create model instance
            instance = model_class(**data)
            result["success"] = True
            result["parsed_data"] = instance.dict()

            # Check for potential warnings (optional fields, etc.)
            result["warnings"] = ModelValidator._check_warnings(
                model_class, data, instance
            )

        except ValidationError as e:
            result["errors"] = [
                {
                    "field": ".".join(str(loc) for loc in error["loc"]),
                    "message": error["msg"],
                    "type": error["type"],
                    "input": error.get("input"),
                }
                for error in e.errors()
            ]
        except Exception as e:
            result["errors"] = [{"message": f"Unexpected error: {str(e)}"}]

        return result

    @staticmethod
    def _check_warnings(
        model_class: Type[BaseModel], input_data: Dict, instance: BaseModel
    ) -> List[str]:
        """Check for potential warnings in model validation"""
        warnings = []

        # Check for unused fields (not part of model but provided in input)
        model_fields = set(model_class.__fields__.keys())
        input_fields = set(input_data.keys())
        unused_fields = input_fields - model_fields

        if unused_fields:
            warnings.append(f"Unused fields provided: {', '.join(unused_fields)}")

        # Check for fields that used default values when optional
        for field_name, field_info in model_class.__fields__.items():
            if field_info.default is not ... and field_name not in input_data:
                warnings.append(
                    f"Field '{field_name}' using default value: {field_info.default}"
                )

        return warnings

    @staticmethod
    def validate_json_against_model(
        model_class: Type[BaseModel], json_data: Union[str, Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Validate JSON data against a model

        Args:
            model_class: Pydantic model class
            json_data: JSON string or dictionary

        Returns:
            Validation results
        """
        if isinstance(json_data, str):
            try:
                data = json.loads(json_data)
            except json.JSONDecodeError as e:
                return {
                    "success": False,
                    "errors": [{"message": f"Invalid JSON: {str(e)}"}],
                    "warnings": [],
                    "parsed_data": None,
                    "model_name": model_class.__name__,
                }
        else:
            data = json_data

        return ModelValidator.validate_model(model_class, data)

    @staticmethod
    def generate_example_data(model_class: Type[BaseModel]) -> Dict[str, Any]:
        """
        Generate example data that would pass validation for a model

        Args:
            model_class: Pydantic model class

        Returns:
            Dictionary with example data
        """
        example_data = {}

        for field_name, field_info in model_class.__fields__.items():
            example_value = ModelValidator._generate_example_value(field_info)
            if example_value is not None:
                example_data[field_name] = example_value

        return example_data

    @staticmethod
    def _generate_example_value(field_info) -> Any:
        """Generate example value for a field"""
        field_type = field_info.type_

        # Handle Optional types
        if hasattr(field_type, "__origin__") and field_type.__origin__ is Union:
            # Get first non-None type from Union
            for arg in field_type.__args__:
                if arg is not type(None):
                    field_type = arg
                    break

        # Use default if available
        if field_info.default is not ...:
            return field_info.default

        # Generate based on type
        if field_type == str:
            return "example_string"
        elif field_type == int:
            return 123
        elif field_type == float:
            return 123.45
        elif field_type == bool:
            return True
        elif field_type == datetime:
            return datetime.utcnow()
        elif hasattr(field_type, "__origin__") and field_type.__origin__ is list:
            return []
        elif hasattr(field_type, "__origin__") and field_type.__origin__ is dict:
            return {}
        else:
            return None


class ModelTester:
    """Test suite runner for Pydantic models"""

    def __init__(self):
        self.test_results = []

    def test_model_validation(
        self, model_class: Type[BaseModel], test_cases: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Run validation tests against a model

        Args:
            model_class: Pydantic model class to test
            test_cases: List of test cases with 'data' and expected 'valid' boolean

        Returns:
            Test results summary
        """
        results = {
            "model_name": model_class.__name__,
            "total_tests": len(test_cases),
            "passed": 0,
            "failed": 0,
            "test_details": [],
        }

        for i, test_case in enumerate(test_cases):
            test_data = test_case.get("data", {})
            expected_valid = test_case.get("valid", True)
            description = test_case.get("description", f"Test case {i + 1}")

            validation_result = ModelValidator.validate_model(model_class, test_data)
            test_passed = validation_result["success"] == expected_valid

            test_detail = {
                "description": description,
                "input_data": test_data,
                "expected_valid": expected_valid,
                "actual_valid": validation_result["success"],
                "passed": test_passed,
                "errors": validation_result["errors"],
                "warnings": validation_result["warnings"],
            }

            results["test_details"].append(test_detail)

            if test_passed:
                results["passed"] += 1
            else:
                results["failed"] += 1

        self.test_results.append(results)
        return results

    def run_comprehensive_tests(self) -> Dict[str, Any]:
        """Run comprehensive validation tests on all models"""
        from . import auth, settings, video

        all_results = {
            "summary": {
                "total_models_tested": 0,
                "total_tests_run": 0,
                "total_passed": 0,
                "total_failed": 0,
            },
            "model_results": [],
        }

        # Define test cases for key models
        test_suites = {
            video.VideoCreateRequest: [
                {
                    "description": "Valid video creation",
                    "data": {"title": "Test Video", "artist_id": 1},
                    "valid": True,
                },
                {
                    "description": "Empty title should fail",
                    "data": {"title": "", "artist_id": 1},
                    "valid": False,
                },
                {
                    "description": "Negative artist_id should fail",
                    "data": {"title": "Test", "artist_id": -1},
                    "valid": False,
                },
            ],
            auth.LoginRequest: [
                {
                    "description": "Valid login",
                    "data": {"username": "test@example.com", "password": "password123"},
                    "valid": True,
                },
                {
                    "description": "Short password should fail",
                    "data": {"username": "test", "password": "123"},
                    "valid": False,
                },
            ],
            settings.SettingUpdateRequest: [
                {
                    "description": "Valid string setting",
                    "data": {"value": "test_value"},
                    "valid": True,
                },
                {
                    "description": "Valid numeric setting",
                    "data": {"value": 42},
                    "valid": True,
                },
            ],
        }

        # Run tests for each model
        for model_class, test_cases in test_suites.items():
            results = self.test_model_validation(model_class, test_cases)
            all_results["model_results"].append(results)

            all_results["summary"]["total_models_tested"] += 1
            all_results["summary"]["total_tests_run"] += results["total_tests"]
            all_results["summary"]["total_passed"] += results["passed"]
            all_results["summary"]["total_failed"] += results["failed"]

        return all_results


class ModelDocumenter:
    """Generate documentation for Pydantic models"""

    @staticmethod
    def generate_model_docs(model_class: Type[BaseModel]) -> Dict[str, Any]:
        """Generate documentation for a model"""
        docs = {
            "name": model_class.__name__,
            "description": model_class.__doc__ or "No description available",
            "fields": [],
            "example": ModelValidator.generate_example_data(model_class),
        }

        for field_name, field_info in model_class.__fields__.items():
            field_doc = {
                "name": field_name,
                "type": str(field_info.type_),
                "required": field_info.default is ...,
                "default": (
                    field_info.default if field_info.default is not ... else None
                ),
                "description": field_info.field_info.description or "No description",
                "constraints": ModelDocumenter._extract_constraints(field_info),
            }
            docs["fields"].append(field_doc)

        return docs

    @staticmethod
    def _extract_constraints(field_info) -> Dict[str, Any]:
        """Extract validation constraints from field info"""
        constraints = {}

        if hasattr(field_info, "field_info"):
            field_constraints = field_info.field_info

            # Extract common constraints
            for attr in ["min_length", "max_length", "ge", "le", "gt", "lt", "regex"]:
                if hasattr(field_constraints, attr):
                    value = getattr(field_constraints, attr)
                    if value is not None:
                        constraints[attr] = value

        return constraints


# Utility functions for common validation patterns
def validate_file_path(path: str) -> bool:
    """Validate if a file path is safe and reasonable"""
    try:
        p = Path(path)
        # Check for path traversal attempts
        if ".." in path or path.startswith("/etc") or path.startswith("/root"):
            return False
        # Check length
        if len(path) > 500:
            return False
        return True
    except Exception:
        return False


def validate_url_format(url: str) -> bool:
    """Basic URL format validation"""
    if not url:
        return False
    return url.startswith(("http://", "https://")) and len(url) < 2000


def validate_email_domain(email: str) -> bool:
    """Validate email domain (basic check)"""
    if "@" not in email:
        return False
    domain = email.split("@")[-1]
    return "." in domain and len(domain) > 3


def validate_json_serializable(data: Any) -> bool:
    """Check if data can be JSON serialized"""
    try:
        json.dumps(data)
        return True
    except (TypeError, ValueError):
        return False


def sanitize_user_input(text: str, max_length: int = 1000) -> str:
    """Sanitize user input text"""
    if not text:
        return ""

    # Strip whitespace and limit length
    text = text.strip()[:max_length]

    # Remove null bytes and other control characters
    text = "".join(char for char in text if ord(char) >= 32 or char in "\t\n\r")

    return text


# Export validation utilities
__all__ = [
    "ModelValidator",
    "ModelTester",
    "ModelDocumenter",
    "validate_file_path",
    "validate_url_format",
    "validate_email_domain",
    "validate_json_serializable",
    "sanitize_user_input",
]
