# Page snapshot

```yaml
- generic [ref=e2]:
  - heading "MVidarr Login" [level=1] [ref=e3]
  - generic [ref=e4]:
    - generic [ref=e5]:
      - generic [ref=e6]: "Username:"
      - textbox "Username:" [ref=e7]: testuser
    - generic [ref=e8]:
      - generic [ref=e9]: "Password:"
      - textbox "Password:" [ref=e10]: testpass
    - button "Login" [ref=e11] [cursor=pointer]
  - generic [ref=e12]: ❌ Invalid credentials
  - generic [ref=e13]:
    - strong [ref=e14]: ✅ Authentication System Working
    - text: Browser requests are now properly redirected to this login page.
    - text: "Default credentials: admin / mvidarr"
  - generic [ref=e15]:
    - strong [ref=e16]: "⚠️ Security Notice:"
    - text: This page is using HTTP instead of HTTPS. In production, always use HTTPS to encrypt login credentials during transmission.
```