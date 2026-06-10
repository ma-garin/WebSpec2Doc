module.exports = {
  testDir: "/home/user/WebSpec2Doc",
  testMatch: "spec.ts",
  timeout: 30000,
  workers: 1,
  outputDir: "/tmp/pytest-of-root/pytest-20/test_default_per_test_timeout_0/out/test-results",
  use: {
    screenshot: 'on',
    trace: 'retain-on-failure',
    actionTimeout: 15000,
    navigationTimeout: 30000,
  },
  reporter: [
    ['json'],
    ['html', { outputFolder: "/tmp/pytest-of-root/pytest-20/test_default_per_test_timeout_0/out/playwright-report", open: 'never' }],
  ],
};
