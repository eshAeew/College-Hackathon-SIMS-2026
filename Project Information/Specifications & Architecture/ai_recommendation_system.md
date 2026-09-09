# API Sentinel — AI Recommendation & Diagnostic System

## 1. How AI Works in API Sentinel
AI is utilized strictly as an **expert diagnostic layer** following deterministic test execution.

```text
[HTTP Execution Engine]
         |
         v
[Failure Detected: POST /login -> 500 Internal Server Error]
         |
         v
[Evidence Aggregator Packages Structured Diagnostic DTO]
         |
         v
[LLM Prompt Synthesizer Formats Context]
         |
         +-----------------------------+
         | (Has API Key)               | (Offline / No Key)
         v                             v
[Google Gemini API Call]     [Rule-Based Heuristics Fallback]
         |                             |
         +--------------+--------------+
                        |
                        v
         [Structured Remediation JSON]
         {
           "likely_cause": "...",
           "severity": "HIGH",
           "suggested_fix": "...",
           "code_snippet": "..."
         }
```

## 2. Prompt Template Structure
```text
System: You are an expert API Reliability & QA Engineer. Analyze the provided REST API failure evidence and output ONLY valid JSON adhering to the specified schema.

User:
EVIDENCE:
- Endpoint: POST /api/auth/login
- Request Payload: {"email": "user@example.com"}
- Expected Status: 400 Bad Request
- Received Status: 500 Internal Server Error
- Response Body: "Internal Server Error: KeyError 'password'"
- Latency: 180 ms
- Failure Classification: Missing Validation / Server Exception Leak
```
