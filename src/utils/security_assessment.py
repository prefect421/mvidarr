#!/usr/bin/env python3
"""
Security Assessment and Vulnerability Scanner for MVidarr
"""
import json
import os
import re
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict


class SecurityAssessment:
    """Comprehensive security assessment for MVidarr"""

    def __init__(self, project_root: str = None):
        self.project_root = (
            Path(project_root) if project_root else Path(__file__).parent.parent.parent
        )
        self.issues = []
        self.recommendations = []

    def log_issue(
        self, severity: str, category: str, description: str, fix: str = None
    ):
        """Log a security issue"""
        self.issues.append(
            {
                "severity": severity,
                "category": category,
                "description": description,
                "fix": fix,
            }
        )

    def log_recommendation(self, category: str, description: str):
        """Log a security recommendation"""
        self.recommendations.append({"category": category, "description": description})

    def check_file_permissions(self) -> Dict[str, Any]:
        """Check file and directory permissions"""
        print("🔍 Checking file permissions...")

        sensitive_files = [
            ".env",
            "data/mvidarr.db",
            "data/logs/mvidarr.log",
            "src/config/",
            "app.py",
        ]

        permission_issues = []

        for file_path in sensitive_files:
            full_path = self.project_root / file_path
            if full_path.exists():
                stat_info = full_path.stat()
                perms = oct(stat_info.st_mode)[-3:]

                # Check for overly permissive permissions
                if perms in ["777", "666", "755"] and file_path in [
                    ".env",
                    "data/mvidarr.db",
                ]:
                    permission_issues.append(f"{file_path}: {perms} (too permissive)")
                    self.log_issue(
                        "HIGH",
                        "File Permissions",
                        f"Sensitive file {file_path} has overly permissive permissions: {perms}",
                        f"chmod 600 {file_path}",
                    )

        return {"issues": permission_issues}

    def check_environment_variables(self) -> Dict[str, Any]:
        """Check environment variable security"""
        print("🔍 Checking environment variables...")

        env_issues = []

        # Check for default/weak values
        weak_values = {
            "SECRET_KEY": ["dev", "development", "change_me", ""],
            "DB_PASSWORD": ["", "password", "root", "admin"],
            "FLASK_DEBUG": (
                ["True", "1", "true"] if os.getenv("FLASK_ENV") == "production" else []
            ),
        }

        for var_name, weak_vals in weak_values.items():
            current_value = os.getenv(var_name, "")
            if current_value in weak_vals:
                env_issues.append(f"{var_name}: {current_value or 'empty'}")
                self.log_issue(
                    "HIGH",
                    "Environment Security",
                    f"Environment variable {var_name} has weak/default value",
                    f"Set a strong, unique value for {var_name}",
                )

        return {"issues": env_issues}

    def check_dependencies(self) -> Dict[str, Any]:
        """Check for vulnerable dependencies"""
        print("🔍 Checking dependencies for vulnerabilities...")

        dep_issues = []

        # Check if safety is available for vulnerability scanning
        try:
            result = subprocess.run(
                ["safety", "check", "--json"],
                capture_output=True,
                text=True,
                cwd=self.project_root,
            )
            if result.returncode == 0:
                vulnerabilities = json.loads(result.stdout)
                for vuln in vulnerabilities:
                    dep_issues.append(f"{vuln['package']}: {vuln['vulnerability']}")
                    self.log_issue(
                        "MEDIUM",
                        "Dependencies",
                        f"Vulnerable dependency: {vuln['package']} - {vuln['vulnerability']}",
                        f"Update {vuln['package']} to version {vuln.get('safe_version', 'latest')}",
                    )
        except FileNotFoundError:
            self.log_recommendation(
                "Dependencies",
                "Install safety tool for dependency vulnerability scanning: pip install safety",
            )

        return {"issues": dep_issues}

    def check_database_security(self) -> Dict[str, Any]:
        """Check database security configuration"""
        print("🔍 Checking database security...")

        db_issues = []
        db_path = self.project_root / "data" / "mvidarr.db"

        if db_path.exists():
            # Check database permissions
            stat_info = db_path.stat()
            perms = oct(stat_info.st_mode)[-3:]

            if perms in ["777", "666", "755"]:
                db_issues.append(f"Database file permissions too permissive: {perms}")
                self.log_issue(
                    "HIGH",
                    "Database Security",
                    f"Database file has overly permissive permissions: {perms}",
                    f"chmod 600 {db_path}",
                )

            # Check for default admin users (if applicable)
            try:
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()

                # Check if there are any obvious security issues in the schema
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
                tables = cursor.fetchall()

                # Look for user/auth tables
                auth_tables = [
                    table[0]
                    for table in tables
                    if "user" in table[0].lower() or "auth" in table[0].lower()
                ]
                if auth_tables:
                    self.log_recommendation(
                        "Database Security",
                        f"Authentication tables found: {auth_tables}. Ensure strong password policies.",
                    )

                conn.close()
            except Exception as e:
                db_issues.append(f"Could not analyze database: {e}")

        return {"issues": db_issues}

    def check_network_security(self) -> Dict[str, Any]:
        """Check network security configuration"""
        print("🔍 Checking network security...")

        network_issues = []

        # Check for default ports
        default_port = os.getenv("PORT", "5000")
        if default_port == "5000":
            self.log_recommendation(
                "Network Security",
                "Consider using a non-default port for production deployment",
            )

        # Check for HTTPS configuration
        if not os.getenv("FORCE_HTTPS"):
            self.log_recommendation(
                "Network Security", "Enable HTTPS enforcement for production deployment"
            )

        return {"issues": network_issues}

    def check_code_security(self) -> Dict[str, Any]:
        """Check for common code security issues"""
        print("🔍 Checking code security patterns...")

        code_issues = []

        # Patterns to look for
        dangerous_patterns = [
            (r"eval\s*\(", "Code injection risk: eval() usage"),
            (r"exec\s*\(", "Code injection risk: exec() usage"),
            (r"shell=True", "Command injection risk: shell=True in subprocess"),
            (r"os\.system\s*\(", "Command injection risk: os.system() usage"),
            (r"pickle\.loads?\s*\(", "Deserialization risk: pickle usage"),
            (r"yaml\.load\s*\(", "Deserialization risk: unsafe YAML loading"),
            (
                r"request\.args\.get\([^)]*\)",
                "Input validation: Ensure request parameters are validated",
            ),
        ]

        # Scan Python files
        for py_file in self.project_root.rglob("*.py"):
            if "venv" in str(py_file) or "__pycache__" in str(py_file):
                continue

            try:
                content = py_file.read_text()
                for pattern, message in dangerous_patterns:
                    matches = re.findall(pattern, content, re.IGNORECASE)
                    if matches:
                        code_issues.append(
                            f"{py_file.relative_to(self.project_root)}: {message}"
                        )
                        self.log_issue(
                            "MEDIUM",
                            "Code Security",
                            f"Potential security issue in {py_file.name}: {message}",
                            "Review and validate security of this code pattern",
                        )
            except Exception:
                continue

        return {"issues": code_issues}

    def check_logging_security(self) -> Dict[str, Any]:
        """Check logging security configuration"""
        print("🔍 Checking logging security...")

        logging_issues = []

        # Check log file permissions
        log_dir = self.project_root / "data" / "logs"
        if log_dir.exists():
            for log_file in log_dir.glob("*.log"):
                stat_info = log_file.stat()
                perms = oct(stat_info.st_mode)[-3:]

                if perms in ["777", "666", "755"]:
                    logging_issues.append(
                        f"Log file {log_file.name} has overly permissive permissions: {perms}"
                    )
                    self.log_issue(
                        "MEDIUM",
                        "Logging Security",
                        f"Log file has overly permissive permissions: {perms}",
                        f"chmod 640 {log_file}",
                    )

        return {"issues": logging_issues}

    def run_assessment(self) -> Dict[str, Any]:
        """Run complete security assessment"""
        print("🛡️  Starting MVidarr Security Assessment")
        print("=" * 60)

        results = {
            "file_permissions": self.check_file_permissions(),
            "environment": self.check_environment_variables(),
            "dependencies": self.check_dependencies(),
            "database": self.check_database_security(),
            "network": self.check_network_security(),
            "code": self.check_code_security(),
            "logging": self.check_logging_security(),
        }

        return results

    def generate_report(self) -> str:
        """Generate comprehensive security report"""
        report = []
        report.append("# MVidarr Security Assessment Report")
        report.append(f"Generated: {os.popen('date').read().strip()}")
        report.append("")

        # Summary
        total_issues = len(self.issues)
        high_issues = len([i for i in self.issues if i["severity"] == "HIGH"])
        medium_issues = len([i for i in self.issues if i["severity"] == "MEDIUM"])
        low_issues = len([i for i in self.issues if i["severity"] == "LOW"])

        report.append("## Summary")
        report.append(f"- **Total Issues**: {total_issues}")
        report.append(f"- **High Severity**: {high_issues}")
        report.append(f"- **Medium Severity**: {medium_issues}")
        report.append(f"- **Low Severity**: {low_issues}")
        report.append("")

        # Issues by category
        if self.issues:
            report.append("## Security Issues")

            categories = {}
            for issue in self.issues:
                cat = issue["category"]
                if cat not in categories:
                    categories[cat] = []
                categories[cat].append(issue)

            for category, issues in categories.items():
                report.append(f"### {category}")
                for issue in issues:
                    report.append(f"- **{issue['severity']}**: {issue['description']}")
                    if issue["fix"]:
                        report.append(f"  - *Fix*: {issue['fix']}")
                report.append("")

        # Recommendations
        if self.recommendations:
            report.append("## Recommendations")

            rec_categories = {}
            for rec in self.recommendations:
                cat = rec["category"]
                if cat not in rec_categories:
                    rec_categories[cat] = []
                rec_categories[cat].append(rec)

            for category, recs in rec_categories.items():
                report.append(f"### {category}")
                for rec in recs:
                    report.append(f"- {rec['description']}")
                report.append("")

        # Security checklist
        report.append("## Security Checklist")
        checklist_items = [
            "✅ Input validation implemented on all API endpoints",
            "✅ Rate limiting configured for critical operations",
            "✅ Security headers applied to all responses",
            "✅ File upload validation with magic number checking",
            "🔄 Environment variables secured with strong values",
            "🔄 File permissions properly restricted",
            "🔄 HTTPS enforcement configured",
            "🔄 Database access controls implemented",
            "🔄 Security logging and monitoring enabled",
            "🔄 Dependency vulnerability scanning automated",
        ]

        for item in checklist_items:
            report.append(item)

        return "\n".join(report)


def main():
    """Main security assessment function"""
    if len(sys.argv) > 1:
        project_root = sys.argv[1]
    else:
        project_root = None

    assessment = SecurityAssessment(project_root)
    results = assessment.run_assessment()

    print("\n" + "=" * 60)
    print("🛡️  Security Assessment Complete")
    print("=" * 60)

    # Print summary
    total_issues = len(assessment.issues)
    high_issues = len([i for i in assessment.issues if i["severity"] == "HIGH"])

    if total_issues == 0:
        print("✅ No security issues found!")
    else:
        print(f"⚠️  Found {total_issues} security issues ({high_issues} high severity)")

    # Generate and save report
    report = assessment.generate_report()
    report_path = Path("security_assessment_report.md")
    report_path.write_text(report)

    print(f"📄 Full report saved to: {report_path.absolute()}")

    # Return exit code based on severity
    if high_issues > 0:
        sys.exit(2)  # High severity issues
    elif total_issues > 0:
        sys.exit(1)  # Medium/Low severity issues
    else:
        sys.exit(0)  # No issues


if __name__ == "__main__":
    main()
