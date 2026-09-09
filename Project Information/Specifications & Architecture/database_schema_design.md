# API Sentinel — Database Schema Design

## 1. Entity-Relationship Model (SQLite / SQLAlchemy)

```text
+----------------+       +------------------+       +-------------------+
|    Project     | 1   * |     Endpoint     | 1   * |     TestCase      |
|----------------|-------|------------------|-------|-------------------|
| id (PK)        |       | id (PK)          |       | id (PK)           |
| name           |       | project_id (FK)  |       | endpoint_id (FK)  |
| description    |       | name             |       | name              |
| base_url       |       | method           |       | request_headers   |
| created_at     |       | path             |       | request_params    |
| updated_at     |       | headers_schema   |       | request_body      |
+----------------+       | body_schema      |       | expected_status   |
        | 1              | expected_status  |       | expected_schema   |
        |                +------------------+       | max_latency_ms    |
        |                                           | is_negative_test  |
        |                                           +-------------------+
        |                                                     | 1
        | 1                                                   |
        v *                                                   v *
+----------------+       +----------------------------------------------+
|    TestRun     | 1   * |                  TestResult                  |
|----------------|-------|----------------------------------------------|
| id (PK)        |       | id (PK)                                      |
| project_id (FK)|       | run_id (FK)                                  |
| name           |       | test_case_id (FK)                            |
| status         |       | status (PASS/FAIL/WARNING/ERROR)             |
| total_tests    |       | response_code                                |
| passed_tests   |       | response_time_ms                             |
| failed_tests   |       | response_body                                |
| warning_tests  |       | response_headers                             |
| started_at     |       | failure_type                                 |
| finished_at    |       | failure_evidence (JSON)                      |
| duration_ms    |       | ai_recommendation_id (FK)                    |
+----------------+       +----------------------------------------------+
                                       | 1
                                       v 0..1
                         +----------------------------------------------+
                         |              AIRecommendation                |
                         |----------------------------------------------|
                         | id (PK)                                      |
                         | test_result_id (FK)                          |
                         | likely_cause                                 |
                         | severity (LOW/MED/HIGH/CRITICAL)             |
                         | suggested_fix                                |
                         | code_snippet                                 |
                         | created_at                                   |
                         +----------------------------------------------+
```
