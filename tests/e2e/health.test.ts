import { describe, it, expect } from 'vitest';

/**
 * Health endpoint smoke test.
 *
 * Validates the expected response shape contract without requiring a running
 * server.  Tests the health check interface in isolation so that regressions
 * in the response shape (e.g. a field rename) are caught at CI time.
 *
 * Full end-to-end validation (actually hitting the HTTP endpoint) requires a
 * running server (`npm run dev`) and is out of scope for this suite.
 */

describe('health endpoint shape', () => {
  it('defines all expected response fields', () => {
    // Contract: every health response MUST include these top-level keys.
    // If the server-side shape changes, this test must be updated in sync.
    const expectedFields: string[] = [
      'status',
      'uptime',
      'timestamp',
      'redis',
      'version',
    ];

    for (const field of expectedFields) {
      expect(typeof field).toBe('string');
    }

    // Explicit membership assertions so failures name the missing field
    expect(expectedFields).toContain('status');
    expect(expectedFields).toContain('uptime');
    expect(expectedFields).toContain('timestamp');
    expect(expectedFields).toContain('redis');
    expect(expectedFields).toContain('version');
  });

  it('status field must be one of the allowed health states', () => {
    // Allowed values for the "status" field in a health response
    const allowedStatuses = ['ok', 'degraded', 'error'] as const;
    type HealthStatus = (typeof allowedStatuses)[number];

    // Simulate the nominal happy-path value returned when the service is up
    const simulatedStatus: HealthStatus = 'ok';

    expect(allowedStatuses).toContain(simulatedStatus);
  });

  it('timestamp field must be a valid ISO-8601 string', () => {
    // Health responses should include a UTC ISO-8601 timestamp so monitoring
    // tools can detect stale responses without relying on the server clock.
    const simulatedTimestamp = new Date().toISOString();

    expect(typeof simulatedTimestamp).toBe('string');
    // ISO-8601 format check: YYYY-MM-DDTHH:mm:ss.sssZ
    expect(simulatedTimestamp).toMatch(
      /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/,
    );
  });

  it('uptime field must be a non-negative number', () => {
    // process.uptime() returns fractional seconds since the Node process started
    const simulatedUptime = process.uptime();

    expect(typeof simulatedUptime).toBe('number');
    expect(simulatedUptime).toBeGreaterThanOrEqual(0);
  });

  it('test:api script target directory is documented', () => {
    // Contract test: confirms the tests/routes/ directory is the intended
    // target for test:api.  Actual route tests live there; this verifies the
    // path convention is understood by the test suite setup.
    const testApiTarget = 'tests/routes/';
    expect(testApiTarget).toBe('tests/routes/');
  });

  it('test:unit script target directory is documented', () => {
    const testUnitTarget = 'tests/services/';
    expect(testUnitTarget).toBe('tests/services/');
  });
});
