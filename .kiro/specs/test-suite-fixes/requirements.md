# Requirements Document: Test Suite Fixes for Xero SDK Migration

## Introduction

The application recently migrated from using httpx directly to using the official Xero Python SDK. This migration has broken many tests that were written to mock HTTP requests. Additionally, there are issues with pytest-httpx compatibility, configuration field changes, and GL code mapping inconsistencies.

## Glossary

- **System**: The Shopify-Xero sync application test suite
- **Xero_SDK**: The official xero-python SDK library
- **pytest-httpx**: A pytest plugin for mocking httpx HTTP requests
- **Mock**: A test double that simulates the behavior of real objects
- **GL_Code**: General Ledger account code used in Xero for categorizing transactions
- **Dry_Run**: A mode where the system simulates operations without making actual changes

## Requirements

### Requirement 1: Fix Xero Client Tests

**User Story:** As a developer, I want the Xero client tests to work with the SDK-based implementation, so that I can verify the Xero integration is working correctly.

#### Acceptance Criteria

1. WHEN testing Xero client initialization, THE System SHALL mock the SDK ApiClient instead of HTTP requests
2. WHEN testing Xero API calls, THE System SHALL mock the AccountingApi methods instead of HTTP responses
3. WHEN testing token refresh, THE System SHALL mock the SDK's token refresh mechanism
4. WHEN testing error handling, THE System SHALL mock SDK exceptions instead of HTTP status codes
5. THE System SHALL remove all httpx_mock usage from Xero client tests
6. THE System SHALL verify that all Xero client test methods pass

### Requirement 2: Fix Shopify Client Tests

**User Story:** As a developer, I want the Shopify client tests to use compatible pytest-httpx syntax, so that HTTP mocking works correctly.

#### Acceptance Criteria

1. WHEN using pytest-httpx for mocking, THE System SHALL use `url` parameter with regex patterns instead of `url__regex`
2. WHEN mocking HTTP responses, THE System SHALL use the pytest-httpx 0.36.0 compatible API
3. THE System SHALL verify that all Shopify client tests pass

### Requirement 3: Fix Configuration Tests

**User Story:** As a developer, I want configuration tests to match the current Settings model, so that configuration validation works correctly.

#### Acceptance Criteria

1. WHEN testing Settings fields, THE System SHALL use the correct field names from the current implementation
2. WHEN testing required fields, THE System SHALL verify all currently required fields
3. THE System SHALL verify that configuration tests pass

### Requirement 4: Fix GL Code Mapping

**User Story:** As a developer, I want GL code mappings to be consistent across the codebase and tests, so that product categorization works correctly.

#### Acceptance Criteria

1. WHEN mapping product categories to GL codes, THE System SHALL use consistent GL codes
2. WHEN testing GL code lookups, THE System SHALL verify the correct codes are returned
3. THE System SHALL include all product categories in the mapping
4. THE System SHALL verify that constants tests pass

### Requirement 5: Fix Sync Engine Dry Run Mode

**User Story:** As a developer, I want the sync engine to respect the dry_run setting, so that test mode doesn't make actual API calls.

#### Acceptance Criteria

1. WHEN dry_run is set to true, THE System SHALL not make actual API calls to Xero
2. WHEN dry_run is set to false, THE System SHALL make actual API calls to Xero
3. WHEN testing sync operations in dry run mode, THE System SHALL verify no API calls are made
4. THE System SHALL verify that sync engine tests pass

### Requirement 6: Fix Integration Tests

**User Story:** As a developer, I want integration tests to work with the SDK-based implementation, so that end-to-end workflows are verified.

#### Acceptance Criteria

1. WHEN testing duplicate detection, THE System SHALL properly mock SDK responses
2. WHEN testing idempotency, THE System SHALL verify operations are idempotent with SDK mocks
3. WHEN testing error scenarios, THE System SHALL mock SDK exceptions appropriately
4. THE System SHALL verify that all integration tests pass

### Requirement 7: Verify Test Coverage

**User Story:** As a developer, I want to ensure adequate test coverage is maintained, so that the codebase remains reliable.

#### Acceptance Criteria

1. WHEN running tests with coverage, THE System SHALL achieve at least 80% code coverage
2. WHEN reviewing coverage reports, THE System SHALL identify any critical untested code paths
3. THE System SHALL verify that all test files execute successfully
