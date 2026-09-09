Absolutely. We’ll treat this as a **real product build**, not just a hackathon demo.

I’ll also keep your future instruction in mind: **when you later send that prompt, I’ll turn this finalized plan into one comprehensive AI-development prompt, without code, and I’ll strictly respect the technology stack defined by the case study.** For now, I’m **not** creating that prompt.

The case study itself requires a Java/Python application that automatically tests REST APIs, detects incorrect responses, missing validation, inconsistent behavior and basic performance issues, and provides AI-assisted recommendations. It specifically lists Java/Spring Boot or Python/FastAPI/Flask, REST/HTTP libraries, JSON/XML parsers, optional OpenAPI/Postman support, optional AI/LLM API, and SQLite/PostgreSQL.  

# API Testing Platform — Complete Project Plan

## 0. Project Definition

### Working name

**API Sentinel**

### One-line definition

> An automated REST API testing platform that executes configurable functional and negative test cases, validates responses, detects inconsistencies and basic performance problems, tracks recurring failures, and converts test results into actionable developer recommendations.

### Primary users

* Backend developers
* QA engineers
* API developers
* Development teams
* Students/developers testing their own APIs

### Core problem

Normally, a developer has to manually:

1. Open an API client.
2. Enter endpoint details.
3. Send requests.
4. Check status codes.
5. Inspect JSON.
6. Check required fields.
7. Try invalid inputs.
8. Measure response time.
9. Repeat everything after code changes.
10. Figure out why something failed.

Our platform should automate this workflow.

---

# 1. Technology Boundary

This is important because you specifically said you don't want random technologies added later.

The case study permits:

### Backend

**Python + FastAPI**

I recommend choosing this rather than Java/Spring Boot for the implementation because it will allow us to build the MVP faster while remaining completely within the case-study requirements.

### API communication

* HTTP/REST libraries
* `httpx` or equivalent Python REST/HTTP library

### Data formats

* JSON parsing
* XML parsing where applicable

### API specification

Optional:

* OpenAPI
* Postman collection

### AI

Optional:

* AI/LLM API

AI will **not** be responsible for actually determining whether an API passed or failed.

The testing engine determines that.

AI comes afterward to explain results and provide recommendations.

### Database

**SQLite** for the MVP.

The case study explicitly allows SQLite/PostgreSQL. 

### Frontend

The case study doesn't prescribe a frontend technology in the listed stack, so this needs to be handled carefully in the final implementation specification. The core application technology must remain within the permitted Java/Python backend ecosystem rather than introducing an unrelated backend stack.

---

# 2. Overall System Architecture

The system should conceptually operate like this:

```text
                    ┌──────────────────┐
                    │      USER        │
                    └────────┬─────────┘
                             │
                             ▼
                    ┌──────────────────┐
                    │   Web Interface  │
                    └────────┬─────────┘
                             │
                             ▼
                    ┌──────────────────┐
                    │   FastAPI        │
                    │   Application    │
                    └────────┬─────────┘
                             │
             ┌───────────────┼────────────────┐
             ▼               ▼                ▼
      ┌─────────────┐ ┌─────────────┐ ┌──────────────┐
      │ API Manager │ │ Test Engine │ │ Run Manager  │
      └─────────────┘ └──────┬──────┘ └──────────────┘
                             │
                    ┌────────┴────────┐
                    ▼                 ▼
             ┌────────────┐   ┌──────────────┐
             │ Validator  │   │ Performance  │
             │ Engine     │   │ Analyzer     │
             └─────┬──────┘   └──────┬───────┘
                   │                  │
                   └────────┬─────────┘
                            ▼
                    ┌───────────────┐
                    │ Failure       │
                    │ Analyzer      │
                    └───────┬───────┘
                            │
                            ▼
                    ┌───────────────┐
                    │ AI Recommend. │
                    │ Layer         │
                    └───────┬───────┘
                            │
                            ▼
                    ┌───────────────┐
                    │ SQLite        │
                    │ Results       │
                    └───────────────┘
```

The important principle:

> **Testing logic first. AI second.**

---

# 3. Stage 1 — Project Foundation

## Objective

Create the basic application structure and establish the development foundation.

### Features

* Project initialization
* Backend application
* Database connection
* Configuration management
* Environment configuration
* Basic application health check
* Logging
* Error-handling framework
* API routing structure

### Expected result

The application should start successfully and expose the basic backend infrastructure.

### Definition of done

You should be able to:

* Start the application.
* Access the backend.
* Confirm database connectivity.
* Confirm API health.
* See structured logs.
* Handle basic application errors.

---

# 4. Stage 2 — Project / Workspace Management

The user needs somewhere to organize their APIs.

## Objective

Create the concept of a **Project**.

Example:

```text
Project: E-Commerce API

Endpoints:
├── Login
├── Products
├── Product Details
├── Cart
└── Orders
```

### Features

#### Create project

Fields:

* Project name
* Description
* Optional environment information

#### View projects

Display:

* Project name
* Number of endpoints
* Number of test cases
* Last test run
* Pass/fail summary

#### Edit project

Allow:

* Rename
* Description changes

#### Delete project

Delete project and associated test configuration/results after confirmation.

### Definition of done

A user can create and manage separate API testing projects.

---

# 5. Stage 3 — API Endpoint Management

This is where the actual API being tested gets registered.

## Objective

Allow users to define APIs/endpoints.

### Endpoint information

Each endpoint should support:

* Endpoint name
* HTTP method
* URL
* Headers
* Query parameters
* Path parameters
* Request body
* Expected status code
* Expected response format

Supported methods:

* GET
* POST
* PUT
* PATCH
* DELETE

Potentially:

* HEAD
* OPTIONS

but these aren't necessary for the first MVP.

---

## Example

```text
Name:
User Login

Method:
POST

URL:
https://example.com/api/login

Headers:
Content-Type: application/json

Body:
{
    "email": "user@example.com",
    "password": "password123"
}

Expected Status:
200

Expected Format:
JSON
```

### Features

* Add endpoint
* Edit endpoint
* Delete endpoint
* View endpoint
* Duplicate endpoint
* Enable/disable endpoint
* Organize endpoints within project

---

# 6. Stage 4 — Request Configuration Engine

The endpoint information now needs to become an executable request.

## Objective

Create the request-building system.

### Request components

The engine should construct:

```text
HTTP Method
+
URL
+
Headers
+
Query Parameters
+
Path Parameters
+
Request Body
```

### Supported body types

At minimum:

* JSON
* XML
* Empty body

### Validation

Before execution:

* Validate URL
* Validate HTTP method
* Validate JSON
* Validate required configuration
* Detect malformed request configuration

### Definition of done

A configured endpoint can be converted into an actual HTTP request.

---

# 7. Stage 5 — Core API Execution Engine

This is the **heart of the project**.

## Objective

Execute configured API requests automatically.

### Execution process

```text
Load test case
      ↓
Build request
      ↓
Send HTTP request
      ↓
Capture response
      ↓
Record execution metrics
      ↓
Send response to validator
```

### Capture

For every execution:

* Request timestamp
* Response timestamp
* HTTP status code
* Response body
* Response headers
* Response size
* Response time
* Error information
* Execution status

### Network errors

Handle:

* Connection failure
* Timeout
* DNS failure
* Invalid URL
* Connection refused
* Server unavailable

### Definition of done

The platform can reliably send requests and capture complete responses.

---

# 8. Stage 6 — Test Case Management

Now we move from simply executing APIs to **testing them**.

## Objective

Allow multiple test cases per endpoint.

Example:

```text
POST /login

TC-001 Valid Login
TC-002 Wrong Password
TC-003 Missing Password
TC-004 Invalid Email
TC-005 Empty Request
```

---

## Test case structure

Each test should define:

### Identification

* Test name
* Description
* Test ID

### Request

* Method
* URL
* Headers
* Parameters
* Body

### Expectations

* Expected HTTP status
* Expected response format
* Expected fields
* Expected response properties
* Optional response-time threshold

---

# 9. Stage 7 — Functional Validation Engine

This is another **core component**.

The platform must determine whether an API response is correct.

## 9.1 HTTP Status Validation

Example:

```text
Expected: 200
Received: 500

Result: FAIL
```

Another:

```text
Expected: 404
Received: 404

Result: PASS
```

---

# 9.2 Response Format Validation

Determine whether response is:

* JSON
* XML
* Invalid/malformed

Example:

```text
Expected: JSON

Received:
{invalid json...

Result:
FAIL
```

---

# 9.3 Response Structure Validation

Check:

* Required fields
* Missing fields
* Unexpected structure
* Data types
* Nested objects
* Arrays

Example:

Expected:

```json
{
  "id": 123,
  "name": "John",
  "email": "john@example.com"
}
```

Received:

```json
{
  "id": 123,
  "name": "John"
}
```

Result:

```text
FAIL
Missing field: email
```

---

# 9.4 Data-Type Validation

Example:

```text
Expected:
id → integer

Received:
id → string

Result:
FAIL
```

---

# 9.5 Response Content Validation

Allow expected values/conditions.

Examples:

```text
status = "success"
```

or

```text
user.id must exist
```

---

# 10. Stage 8 — Negative / Adversarial Testing

This is where the project becomes significantly more impressive.

Instead of only testing:

> "Does the API work correctly?"

we also test:

> "Does the API behave correctly when users do something wrong?"

## Examples

For:

```text
POST /login
```

Generate/test:

### Test 1

Valid email + valid password

Expected:

```text
200
```

### Test 2

Wrong password

Expected:

```text
401
```

### Test 3

Missing password

Expected:

```text
400
```

### Test 4

Missing email

Expected:

```text
400
```

### Test 5

Invalid email format

Expected:

```text
400
```

### Test 6

Empty request

Expected:

```text
400
```

---

## What we detect

Suppose:

```text
Missing password

Expected:
400

Received:
500
```

The system should identify:

> The API may not be handling invalid input correctly and is returning an internal server error instead of a client validation error.

This directly aligns with the case study's requirement to identify incorrect responses and missing validations. 

---

# 11. Stage 9 — Inconsistent Behavior Detection

The system should detect APIs behaving differently under similar conditions.

## Example

Run the same request five times:

```text
Run 1 → 200
Run 2 → 200
Run 3 → 500
Run 4 → 200
Run 5 → 500
```

The system identifies:

```text
INCONSISTENT BEHAVIOR
```

### Metrics

* Total executions
* Successful executions
* Failed executions
* Failure percentage
* Status-code variation
* Response variation
* Latency variation

---

# 12. Stage 10 — Performance Analysis

The case study explicitly requires response-time measurement and basic performance indicators. 

This should **not** become a full-scale load-testing product.

Keep it focused.

## Metrics

For each API:

* Response time
* Minimum response time
* Maximum response time
* Average response time
* Median response time
* Request count
* Failure count
* Success rate

Potentially:

* p95 latency
* p99 latency

These make the dashboard much stronger.

---

## Performance thresholds

Example:

```text
Expected:
< 500 ms

Actual:
1,240 ms

Result:
PERFORMANCE WARNING
```

### Categories

```text
Good
Warning
Critical
```

Thresholds should be configurable.

---

# 13. Stage 11 — Recurring Failure Detection

The case study specifically calls for identifying recurring failure patterns. 

## Objective

Analyze historical test runs.

Example:

```text
TC-003

Run 1 → FAIL
Run 2 → FAIL
Run 3 → PASS
Run 4 → FAIL
Run 5 → FAIL
```

System:

```text
Recurring Failure Detected
```

### Detect patterns based on

* Endpoint
* Test case
* Status code
* Error type
* Validation failure
* Response-time issue
* Frequency
* Recent history

---

# 14. Stage 12 — Test Run Management

Every execution should become a **Test Run**.

## Structure

```text
Test Run
│
├── Start time
├── End time
├── Total tests
├── Passed
├── Failed
├── Warnings
│
├── Test Result 1
├── Test Result 2
├── Test Result 3
└── ...
```

### Features

* Start test run
* Stop/cancel run where practical
* View run
* View individual results
* Compare runs
* View historical runs

---

# 15. Stage 13 — Regression Testing

This is a major feature.

## Objective

Compare the current API behavior with previous test runs.

Example:

### Previous run

```text
GET /products

Status: 200
Latency: 220 ms
```

### Current run

```text
GET /products

Status: 500
Latency: 910 ms
```

System:

```text
REGRESSION DETECTED
```

---

## Detect changes in

* Status code
* Response structure
* Required fields
* Response time
* Failure frequency
* Error behavior

---

# 16. Stage 14 — OpenAPI Support

The case study explicitly lists OpenAPI/Postman support as optional. 

I recommend implementing **OpenAPI import** as the first major optional feature because it dramatically improves the demo.

## Workflow

```text
Upload OpenAPI file
        ↓
Parse specification
        ↓
Discover endpoints
        ↓
Create endpoint configurations
        ↓
Generate basic test cases
        ↓
User reviews
        ↓
Run tests
```

### Import information

Extract:

* Paths
* Methods
* Parameters
* Request bodies
* Response definitions
* Schemas
* Expected status codes

---

# 17. Stage 15 — Automatic Test Generation

Once OpenAPI import exists, we can automatically create tests.

Example:

```text
POST /users
```

System identifies:

```text
Required:
name
email
password
```

Possible tests:

```text
Valid request
Missing name
Missing email
Missing password
Empty request
Invalid email
```

### Important

Automatically generated tests should be **reviewable before execution**.

Don't silently run potentially destructive requests.

---

# 18. Stage 16 — Safety & Execution Controls

This is important if the platform becomes a real product.

## Features

### Explicit target

User must specify the API being tested.

### Test authorization warning

The interface should clearly communicate:

> Only test APIs you own or have permission to test.

### Dangerous operations

Potentially destructive methods such as:

```text
DELETE
```

should have additional confirmation/configuration.

### Test environment

Allow users to identify environments such as:

```text
Development
Testing
Staging
Production
```

For the MVP, this can simply be metadata/configuration rather than a huge environment-management system.

---

# 19. Stage 17 — Result Classification Engine

Every test result should receive a clear classification.

## PASS

Everything expected happened.

## FAIL

Functional expectation failed.

## WARNING

The API works but something concerning was detected.

Example:

```text
Status correct
Response structure correct
Latency unusually high
```

## ERROR

The test itself could not execute properly.

Example:

```text
Connection timeout
Invalid URL
```

This distinction will make the UI much clearer.

---

# 20. Stage 18 — Failure Analysis Engine

Now take raw failures and turn them into structured information.

Example:

```text
Endpoint:
POST /login

Test:
Missing password

Expected:
400

Received:
500

Response:
Internal Server Error
```

Convert this into:

```text
Failure Type:
Validation Failure

Severity:
High

Evidence:
Missing password produced HTTP 500.

Likely Area:
Request validation / server-side error handling
```

---

# 21. Stage 19 — AI Recommendation Layer

**Only now do we introduce AI.**

This is important.

The AI should not decide whether:

```text
200 == PASS
```

That's deterministic.

Instead:

```text
Testing Engine
      ↓
Structured Evidence
      ↓
AI
      ↓
Explanation
      ↓
Recommendation
```

---

## AI inputs

The AI can receive structured information such as:

* Endpoint
* Method
* Expected status
* Actual status
* Validation failures
* Response structure
* Error messages
* Latency
* Failure history
* Test case description

---

## AI output

### Explanation

Explain what happened.

### Likely cause

Suggest probable reason.

### Recommendation

Suggest what the developer should investigate/fix.

### Severity

Potentially:

```text
Low
Medium
High
Critical
```

---

## Example

Input:

```text
Test:
Missing password

Expected:
400

Actual:
500
```

AI output conceptually:

```text
Issue:
The endpoint returns an internal server error when the password
field is missing.

Recommendation:
Add request validation for the password field and return an
appropriate client-error response instead of allowing the request
to reach an unhandled server-side failure.
```

The case study explicitly requires recommendations for developers. 

---

# 22. Stage 20 — Dashboard

Now combine everything into a usable interface.

## Main dashboard

Show:

```text
Projects
Endpoints
Test Cases
Total Tests
Passed
Failed
Warnings
Recent Runs
Recurring Failures
Performance Issues
```

---

# 23. Project Dashboard

Example:

```text
E-Commerce API

Tests
128

Pass Rate
91%

Failures
11

Warnings
8

Avg Response
284 ms

Last Run
2 minutes ago
```

---

# 24. Endpoint Dashboard

Example:

```text
POST /login

Status:
PASS

Average Latency:
214 ms

Success Rate:
98%

Tests:
12

Failures:
2

Recurring Issues:
1
```

---

# 25. Test Result Page

This needs to be highly detailed.

Example:

```text
TC-003 — Missing Password

━━━━━━━━━━━━━━━━━━━━

Result: FAIL
Severity: HIGH

Request
POST /login

Expected
HTTP 400

Actual
HTTP 500

Response Time
312 ms

Validation
✗ Status code mismatch
✗ Validation failure

Failure Pattern
Recurring

AI Analysis
[Explain Issue]

Recommendation
[View Recommendation]
```

---

# 26. Stage 21 — Run Comparison

Allow:

```text
Run #14
vs
Run #15
```

Comparison:

| Metric       | Previous | Current |
| ------------ | -------: | ------: |
| Tests        |       50 |      50 |
| Passed       |       47 |      43 |
| Failed       |        3 |       7 |
| Avg latency  |    210ms |   290ms |
| Success rate |      94% |     86% |

Then:

```text
4 new failures detected
Average latency increased by X
2 existing tests changed behavior
```

---

# 27. Stage 22 — Reporting

Generate a human-readable test report.

## Report sections

### Summary

* Project
* Test run
* Date/time
* Total tests
* Pass rate

### Functional results

* Passed
* Failed
* Warnings

### Performance

* Average
* Median
* Maximum
* Slow endpoints

### Recurring failures

List repeated problems.

### Regression

List newly introduced issues.

### Recommendations

List developer actions.

---

# 28. Stage 23 — Persistence / Database Design

Core entities should include:

```text
Project
Endpoint
TestCase
TestRun
TestResult
FailurePattern
Recommendation
```

Conceptually:

```text
Project
  │
  ├── Endpoints
  │      │
  │      └── Test Cases
  │
  └── Test Runs
         │
         └── Test Results
                │
                ├── Failures
                └── Recommendations
```

---

# 29. Stage 24 — Error Handling

The platform itself must be reliable.

Handle:

### API errors

* 4xx
* 5xx

### Network errors

* Timeout
* Connection refused
* DNS failure

### Configuration errors

* Invalid URL
* Invalid JSON
* Missing required configuration

### Parser errors

* Malformed JSON
* Malformed XML

### AI errors

If AI isn't available:

```text
Testing still works.
```

AI must be an enhancement, **not a dependency for the core testing engine.**

---

# 30. Stage 25 — Logging & Auditability

Every important action should be traceable.

Record:

* Test execution
* Test result
* Errors
* Run start/end
* Configuration changes where practical

This helps debugging the platform itself.

---

# 31. Stage 26 — Testing the Platform

Don't just test APIs with the platform.

**Test the platform itself.**

### Backend tests

Test:

* Project creation
* Endpoint creation
* Test creation
* Request execution
* Validation
* Result storage
* Failure detection
* Performance calculations
* Regression calculations

### Integration tests

Test:

```text
Configuration
→ execution
→ validation
→ storage
→ dashboard result
```

---

# 32. Stage 27 — Build the Demo API

For the hackathon, we should create our own deliberately imperfect REST API.

This is allowed by the case study, which states that no external dataset is required and teams can create their own sample REST API. 

The demo API should contain intentional problems.

## Example problems

### Endpoint 1

Correct login.

### Endpoint 2

Missing validation.

### Endpoint 3

Incorrect status code.

### Endpoint 4

Slow response.

### Endpoint 5

Intermittent failure.

### Endpoint 6

Malformed response.

This makes the demonstration extremely strong because the judges can see the platform **discover actual problems**.

---

# 33. Stage 28 — Final Demo Workflow

This should become the central presentation.

## Step 1

Open API Sentinel.

## Step 2

Create project:

```text
Demo E-Commerce API
```

## Step 3

Import OpenAPI specification.

## Step 4

Platform discovers:

```text
12 endpoints
```

## Step 5

Automatically generate test cases.

## Step 6

User reviews tests.

## Step 7

Click:

> **Run Test Suite**

## Step 8

System executes everything.

Dashboard:

```text
Tests:       42
Passed:      31
Failed:       7
Warnings:     4
```

## Step 9

Open failed test.

Show:

```text
Expected: 400
Received: 500

Missing input validation detected.
```

## Step 10

Open performance section.

Show:

```text
GET /products
Average: 1.4s
Threshold: 500ms
```

## Step 11

Show recurring failure:

```text
This failure occurred 4/5 times.
```

## Step 12

Click:

> **AI Explain**

AI produces explanation/recommendation.

## Step 13

Run the API again after fixing the demo API.

## Step 14

Show regression comparison:

```text
Before:
7 failures

After:
2 failures
```

That gives you an actual **before → detection → fix → verification** story.

---

# 34. Feature Priority System

Not every feature should be built at the same time.

## 🔴 Tier 1 — Absolutely Core

These must work.

1. Project management
2. Endpoint configuration
3. Test case creation
4. HTTP request execution
5. Response capture
6. Status validation
7. JSON/XML parsing
8. Response structure validation
9. Failure detection
10. Response-time measurement
11. Test result storage
12. Test run history
13. Dashboard
14. Basic reporting

---

## 🟠 Tier 2 — Strong Hackathon Features

Build after Tier 1.

15. Negative testing
16. Inconsistent behavior detection
17. Recurring failure detection
18. Regression testing
19. Performance thresholds
20. Run comparison
21. OpenAPI import
22. Automatic test generation

---

## 🟢 Tier 3 — Differentiators

23. AI explanation
24. AI recommendations
25. Intelligent severity classification
26. Advanced failure grouping
27. Better reports

---

# 35. Features We Should NOT Overbuild

This is equally important.

Don't turn the project into Postman + JMeter + CI/CD + Kubernetes in one hackathon.

Avoid initially:

* Full load testing
* Distributed testing
* Complex authentication systems
* Team collaboration
* Enterprise RBAC
* Cloud deployment platform
* Massive analytics system
* Real-time distributed workers
* Full Postman clone
* Full API monitoring platform

Those can be future versions.

---

# 36. Final Product Feature Map

At completion, the product should conceptually look like:

```text
API SENTINEL
│
├── Projects
│
├── API Management
│   ├── Endpoints
│   ├── Methods
│   ├── Headers
│   ├── Parameters
│   └── Request Bodies
│
├── Test Management
│   ├── Test Cases
│   ├── Expected Results
│   ├── Negative Tests
│   └── Generated Tests
│
├── Execution Engine
│   ├── HTTP Requests
│   ├── Response Capture
│   ├── Timeout Handling
│   └── Error Handling
│
├── Validation Engine
│   ├── Status Validation
│   ├── JSON Validation
│   ├── XML Validation
│   ├── Schema Validation
│   ├── Field Validation
│   └── Content Validation
│
├── Analysis
│   ├── Incorrect Responses
│   ├── Missing Validation
│   ├── Inconsistency Detection
│   ├── Performance Analysis
│   ├── Recurring Failures
│   └── Regression Detection
│
├── AI Layer
│   ├── Failure Explanation
│   ├── Root-Cause Suggestions
│   ├── Severity
│   └── Developer Recommendations
│
├── Analytics
│   ├── Test Runs
│   ├── Historical Results
│   ├── Run Comparison
│   └── Performance Metrics
│
├── Import
│   └── OpenAPI
│
└── Reporting
    ├── Summary
    ├── Failures
    ├── Performance
    ├── Regression
    └── Recommendations
```

---

# 37. Development Order

This is the order I recommend actually building it.

### Phase A — Foundation

1. Project setup
2. FastAPI
3. SQLite
4. Application structure
5. Configuration
6. Logging

### Phase B — Data Layer

7. Database models
8. Projects
9. Endpoints
10. Test cases
11. Test runs
12. Test results

### Phase C — Testing Engine

13. HTTP execution
14. Request builder
15. Response capture
16. Status validation
17. JSON/XML parsing
18. Response validation

### Phase D — Intelligence

19. Negative testing
20. Inconsistency detection
21. Performance analysis
22. Recurring failures
23. Regression detection

### Phase E — Automation

24. OpenAPI import
25. Automatic test generation
26. Test-suite execution

### Phase F — AI

27. Failure data structuring
28. AI explanation
29. AI recommendations
30. Severity recommendations

### Phase G — Interface

31. Dashboard
32. Project page
33. Endpoint page
34. Test page
35. Run results
36. Failure analysis
37. Performance analytics
38. Run comparison

### Phase H — Reporting

39. Test reports
40. Summary
41. Recommendations
42. Export/report presentation

### Phase I — Hardening

43. Error handling
44. Security/safety controls
45. Platform testing
46. Demo API
47. End-to-end testing
48. Final polish

---

# 38. The Definition of "Finished"

I would consider the project genuinely complete when you can perform this entire workflow without manually inspecting the APIs yourself:

```text
Create Project
      ↓
Add / Import APIs
      ↓
Create / Generate Tests
      ↓
Execute Test Suite
      ↓
Capture Responses
      ↓
Validate Responses
      ↓
Detect Failures
      ↓
Detect Inconsistencies
      ↓
Measure Performance
      ↓
Find Recurring Problems
      ↓
Compare Against Previous Run
      ↓
Generate AI Explanation
      ↓
Generate Developer Recommendations
      ↓
View Dashboard
      ↓
Generate Final Report
```

And the most important distinction for the project is:

> **The deterministic engine proves that something is wrong. The AI explains what may be wrong and what the developer should investigate.**

That keeps the project technically credible rather than making it another "AI wrapper."

### What I am keeping fixed for your next instruction

When you later send your exact **“now i will be creating this project…”** instruction, I’ll use this finalized architecture/feature plan as the source and produce the **single comprehensive development prompt** you described. I won't add code, and I’ll explicitly define the stages, functions, features, core logic, additional features, architecture, constraints, and permitted technology stack.