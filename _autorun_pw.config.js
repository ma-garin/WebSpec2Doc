module.exports = {
  testDir: "/Users/fujimagariyuki/Desktop/app/014_WebSpec2Doc",
  testMatch: "spec.ts",
  use: { screenshot: 'on', trace: 'retain-on-failure' },
  reporter: [
    ['json'],
    ['html', { outputFolder: "/private/tmp/claude-501/pytest-of-fujimagariyuki/pytest-88/test_add_log_called0/out/playwright-report", open: 'never' }],
  ],
};
